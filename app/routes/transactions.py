from datetime import date
from decimal import Decimal

from flask import render_template, request, redirect, url_for, flash
from apiflask import APIBlueprint, abort
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload
from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction, TransactionSplit
from app.models.wealth import Debt, Document, Holding
from app.routes.helpers import form_choice, form_date, form_decimal, form_ids, form_text, safe_next
from app.services.tags import all_tags, parse_tags  # noqa: F401 - re-exported for older imports
from app.services import accounts, ai_classification, ai_extraction, bank_import, broker, category_rules, currency as currency_service, display, duplicates, merchant, money, splits, undo
from app.services.ai_classification import AI_TAG
from app.services import categories as category_service
from app.services.categories import known_categories
from app.services.parsing import to_decimal, valid_amount
from app.services.periods import month_bounds
from app.schemas.transaction import TransactionIn, TransactionOut, TransactionListOut
from app.schemas.common import DeleteOut
from flask_babel import gettext as _, ngettext

transactions_bp = APIBlueprint(
    "transactions",
    __name__,
    url_prefix="/transactions",
    tag="Transactions"
)


# ── Helpers ────────────────────────────────────────────────────────────────────

RECURRENCES = ("weekly", "monthly", "quarterly", "yearly")


def _tx_from_form(tx: Transaction) -> Transaction:
    """Fill the transaction from the form; a ValueError says which field is wrong (nothing crashes)."""
    tx.date = form_date("date", _("Data"), required=True)
    units, unit_price = _trade_from_form()
    if units is not None and not (request.form.get("amount") or "").strip():  # the amount follows units × price
        gross = money.cents(abs(units) * unit_price)
        amount = -gross if units > 0 else gross
    else:
        amount = form_decimal("amount", _("Importo"), required=True, allow_negative=True)
    if not valid_amount(amount):
        raise ValueError(_("Importo: deve essere diverso da zero."))
    tx.type = _type_from(amount)
    tx.amount = abs(amount)
    tx.description = form_text("description", _("Descrizione"), required=True)
    currency = request.form.get("currency") or "EUR"
    tx.currency = currency if currency in currency_service.CURRENCIES else "EUR"
    tx.category = form_text("category", _("Categoria"))
    tx.tags = parse_tags(request.form.get("tags", ""))
    # the counterparty is now the first tag (kept in its own column for rules, search and the AI)
    tx.counterparty = next((t for t in tx.tags if t != AI_TAG), None)
    tx.is_recurring = "is_recurring" in request.form
    # frequency and end date only mean something for a recurring transaction
    if tx.is_recurring:
        tx.recurrence = form_choice("recurrence", _("Frequenza"), RECURRENCES)
        tx.recurrence_end = form_date("recurrence_end", _("Fine ricorrenza"))
        if tx.recurrence_end and tx.recurrence_end < tx.date:
            raise ValueError(_("Fine ricorrenza: non può essere prima della data."))
    else:
        tx.recurrence = tx.recurrence_end = None
    tx.notes = form_text("notes", _("Note"))
    tx.account_id = _account_id("account_id")
    # a transfer between two own accounts: where the money arrives
    tx.counter_account_id = _account_id("counter_account_id") if tx.type == "transfer" else None
    if tx.counter_account_id and tx.counter_account_id == tx.account_id:
        raise ValueError(_("Verso il conto: deve essere diverso dal conto di partenza."))
    # in another currency than the account's: what the bank charged / credited in the account's currency
    tx.account_amount = _bank_amount("account_amount", _("Importo sul conto"), tx.account_id, tx.currency)
    tx.counter_amount = _bank_amount("counter_amount", _("Importo sul conto d'arrivo"), tx.counter_account_id, tx.currency)
    # what the money is for, in the cash-flow statement: an investment or a debt (one of the two)
    tx.holding_id = _linked_id("holding_id", Holding)
    tx.debt_id = _linked_id("debt_id", Debt) if not tx.holding_id else None
    # units × price only mean something for a trade of a holding
    tx.units, tx.unit_price = (units, unit_price) if tx.holding_id and units is not None else (None, None)
    if tx.units is not None:
        # a trade moves money between the account and the investment: not an expense nor an income (the savings rate
        # stays right); a purchase leaves the account, a sale arrives on it (wealth.cash_balance / accounts.balance)
        tx.type, tx.category = "transfer", tx.category or "Investimenti"
        broker_account = tx.account_id or tx.counter_account_id
        tx.account_id, tx.counter_account_id = (broker_account, None) if tx.units > 0 else (None, broker_account)
        tx.splits = []
    _splits_from_form(tx)
    return tx


def _trade_from_form() -> tuple[Decimal | None, Decimal | None]:
    """Units and price per unit of an investment trade (both or neither); sold units are negative."""
    units = form_decimal("units", _("Quote"))
    price = form_decimal("unit_price", _("Prezzo per quota"))
    if units is None and price is None:
        return None, None
    if units is None or price is None or units <= 0 or price <= 0:
        raise ValueError(_("Operazione: indica quote e prezzo per quota, entrambi maggiori di zero."))
    return (-units if request.form.get("trade_side") == "sell" else units), price


def _after_trade(tx: Transaction) -> list[Transaction]:
    """A new trade entered in units: the confirmed commission as its own expense, and the holding moved by it."""
    created = []
    fee = form_decimal("fee_amount", _("Commissione")) if "record_fee" in request.form else None
    if fee:
        account_id = tx.account_id or tx.counter_account_id
        created.append(broker.fee_transaction(tx, fee, db.session.get(Account, account_id) if account_id else None))
        db.session.add(created[-1])
    if tx.holding_id and tx.units is not None and "update_holding" in request.form:
        holding = db.session.get(Holding, tx.holding_id)
        broker.apply_trade(holding, tx.units, tx.unit_price, fee if fee and tx.units > 0 else Decimal(0), tx.date)
    return created


def _split_rows() -> list[tuple[str, str]]:
    """The (category, amount) rows of the «Suddividi» box as typed, empty rows left out."""
    rows = zip(request.form.getlist("split_category"), request.form.getlist("split_amount"))
    return [(c.strip(), a.strip()) for c, a in rows if c.strip() or a.strip()]


def _splits_from_form(tx: Transaction) -> None:
    """The «Suddividi» rows; one row or none: an ordinary transaction (the box was opened and closed again)."""
    parts = []
    for number, (category, raw) in enumerate(_split_rows(), start=1):
        amount = to_decimal(raw)
        if raw and amount is None:
            raise ValueError(_("Suddivisione, riga %(n)s: «%(raw)s» non è un importo.", n=number, raw=raw))
        parts.append((category, amount))
    splits.apply(tx, parts)


def _type_from(amount) -> str:
    """Minus = expense, no sign = income; the «transfer» box (or an explicit type=transfer) makes it a transfer.
    An explicit type=expense with a positive amount (older forms) stays an expense."""
    if "transfer" in request.form or request.form.get("type") == "transfer":
        return "transfer"
    if amount < 0 or request.form.get("type") == "expense":
        return "expense"
    return "income"


def _linked_id(field: str, model) -> int | None:
    value = request.form.get(field, type=int)
    return value if value and db.session.get(model, value) else None


def _account_id(field: str) -> int | None:
    value = request.form.get(field, type=int)
    return value if value and db.session.get(Account, value) else None


def _bank_amount(field: str, label: str, account_id: int | None, tx_currency: str) -> Decimal | None:
    """The amount typed for the account's currency; nothing when the account is in the transaction's currency."""
    account = db.session.get(Account, account_id) if account_id else None
    if account is None or (account.currency or "EUR") == tx_currency:
        return None
    value = form_decimal(field, label, allow_negative=True)
    return abs(value) if value else None


def _form_values(tx: Transaction | None = None) -> dict:
    """What the form fields show: the stored transaction, what was typed (after an error), or a blank form."""
    if request.method == "POST":
        form = request.form
        return {key: form.get(key, "") for key in (
            "date", "amount", "currency", "description", "category", "tags",
            "recurrence", "recurrence_end", "notes", "account_id", "counter_account_id", "holding_id", "debt_id",
            "account_amount", "counter_amount", "units", "unit_price", "trade_side", "fee_amount")} | {
            "is_recurring": "is_recurring" in form, "transfer": "transfer" in form, "splits": _split_rows(),
            "record_fee": "record_fee" in form, "update_holding": "update_holding" in form}
    if tx is None:
        return {"currency": "EUR", "is_recurring": False, "transfer": False, "splits": [],
                "account_id": request.args.get("account", ""), "trade_side": "buy", "record_fee": True,
                "update_holding": True}
    sign = "-" if tx.type == "expense" else ""
    return {
        "transfer": tx.type == "transfer", "date": tx.date.isoformat() if tx.date else "",
        "amount": sign + f"{abs(tx.amount):.2f}".replace(".", ","), "currency": tx.currency or "EUR",
        "description": tx.description, "category": tx.category or "",
        "tags": ", ".join(tx.tags or []), "is_recurring": bool(tx.is_recurring), "recurrence": tx.recurrence or "",
        "recurrence_end": tx.recurrence_end.isoformat() if tx.recurrence_end else "", "notes": tx.notes or "",
        "account_id": str(tx.account_id or ""), "counter_account_id": str(tx.counter_account_id or ""),
        "holding_id": str(tx.holding_id or ""), "debt_id": str(tx.debt_id or ""),
        "account_amount": _plain(tx.account_amount), "counter_amount": _plain(tx.counter_amount),
        "splits": [(s.category or "", _plain(s.amount)) for s in tx.splits],
        "units": f"{abs(tx.units):f}".rstrip("0").rstrip(".").replace(".", ",") if tx.units is not None else "",
        "unit_price": f"{tx.unit_price:f}".rstrip("0").rstrip(".").replace(".", ",") if tx.unit_price is not None else "",
        "trade_side": "sell" if tx.units is not None and tx.units < 0 else "buy",
    }


def _plain(value) -> str:
    return f"{value:.2f}".replace(".", ",") if value is not None else ""


# ── HTML routes ────────────────────────────────────────────────────────────────

PAGE_SIZE = 100  # rows per page of the list: the whole history at once made pages of megabytes


def _filtered_query(filters: dict):
    """Apply the filter-bar values (q, type, category, month=YYYY-MM, recurring) to the transactions query."""
    query = Transaction.query
    if filters["q"]:
        pattern = f"%{filters['q']}%"
        query = query.filter(or_(
            Transaction.description.ilike(pattern),
            Transaction.counterparty.ilike(pattern),
            func.array_to_string(Transaction.tags, " ").ilike(pattern),
            Transaction.notes.ilike(pattern),
        ))
    if filters["type"]:
        query = query.filter(Transaction.type == filters["type"])
    if filters["category"]:  # a main category shows its subcategories too; a split transaction, any of its parts
        names = category_service.with_children(filters["category"])
        query = query.filter(Transaction.category.in_(names) | Transaction.splits.any(TransactionSplit.category.in_(names)))
    if filters.get("account") == "none":
        query = query.filter(Transaction.account_id.is_(None), Transaction.counter_account_id.is_(None))
    elif (filters.get("account") or "").isdigit():
        account_id = int(filters["account"])
        query = query.filter((Transaction.account_id == account_id) | (Transaction.counter_account_id == account_id))
    if filters.get("tag"):
        query = query.filter(Transaction.tags.any(filters["tag"]))
    if filters.get("recurring"):
        query = query.filter(Transaction.is_recurring.is_(True))
    if filters["month"]:
        try:
            year, month = (int(part) for part in filters["month"].split("-"))
            start, end = month_bounds(year, month)
            query = query.filter(Transaction.date >= start, Transaction.date < end)
        except ValueError:
            pass
    return query


@transactions_bp.route("/")
def index():
    filters = {key: request.args.get(key, "").strip() for key in ("q", "type", "category", "month", "recurring", "account", "tag")}
    query = _filtered_query(filters)
    total = query.count()
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(request.args.get("page", 1, type=int), 1), pages)
    transactions = (query.options(selectinload(Transaction.splits))
                    .order_by(Transaction.date.desc(), Transaction.id.desc())
                    .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all())
    categories = [
        row[0] for row in
        db.session.query(Transaction.category).filter(Transaction.category.isnot(None))
        .distinct().order_by(Transaction.category).all()
    ]
    return render_template(
        "transactions/index.html",
        transactions=transactions,
        total=total, page=page, pages=pages,
        page_url=lambda n: url_for("transactions.index", **(request.args.to_dict() | {"page": n})),
        filters=filters,
        categories=categories,
        all_categories=known_categories(),
        accounts=accounts.active(),
        duplicate_groups=len(duplicates.find_groups()),
        ai_tag=AI_TAG, to_confirm=Transaction.query.filter(Transaction.tags.any(AI_TAG)).count(),
        unclassified=_unclassified_query().count(),
        without_counterparty=Transaction.query.filter(Transaction.counterparty.is_(None), Transaction.type != "transfer").count(),
        undo=undo.available(), today=date.today(),
        **ai_classification.template_context(),
    )


@transactions_bp.route("/add")
def add():
    """Entry point of the sidebar button: single transaction or file import."""
    return render_template("transactions/add.html")


@transactions_bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        try:
            tx = _tx_from_form(Transaction())
            db.session.add(tx)
            db.session.flush()
            extra = _after_trade(tx)
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
            return _render_form(None)
        db.session.commit()
        undo.remember_created([tx, *extra])
        if extra:
            flash(_("Commissione di %(amount)s registrata come spesa.", amount=display.money(extra[0].amount)), "success")
        flash(_("Transazione aggiunta."), "success")
        _learn_from(tx)
        return redirect(url_for("transactions.index"))
    return _render_form(None)


@transactions_bp.route("/quick", methods=["POST"])
def quick_add():
    """The quick-entry row of the list: date, description, signed amount and (optional) category; the category and
    the counterparty, when missing, are guessed as for an imported statement row."""
    try:
        when = form_date("date", _("Data"), required=True)
        description = form_text("description", _("Descrizione"), required=True)
        amount = form_decimal("amount", _("Importo"), required=True, allow_negative=True)
        if not valid_amount(amount):
            raise ValueError(_("Importo: deve essere diverso da zero."))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("transactions.index"))
    kind = _type_from(amount)
    counterparty = merchant.extract(description, None)
    category = form_text("category", _("Categoria")) or (
        None if kind == "transfer" else bank_import.categorize(description, None, None, kind == "income"))
    tx = Transaction(date=when, description=description, amount=abs(amount), currency="EUR", type=kind,
                     category=category, counterparty=counterparty, tags=[counterparty] if counterparty else [],
                     account_id=_account_id("account_id"))
    db.session.add(tx)
    db.session.commit()
    undo.remember_created([tx])
    flash(_("«%(description)s» aggiunta in %(category)s.", description=description, category=category or "—"), "success")
    return redirect(url_for("transactions.index"))


@transactions_bp.route("/undo", methods=["POST"])
def undo_last():
    step = undo.undo()
    if step is None:
        flash(_("Niente da annullare."), "warning")
    elif step["kind"] == "created":
        flash(ngettext("Annullato: tolta la transazione aggiunta.", "Annullato: tolte le %(num)d transazioni aggiunte.",
                       step.get("count", 1)), "success")
    else:
        flash(ngettext("Annullato: rimessa la transazione eliminata.", "Annullato: rimesse le %(num)d transazioni eliminate.",
                       step.get("count", 1)), "success")
    return redirect(safe_next() or url_for("transactions.index"))


@transactions_bp.route("/redo", methods=["POST"])
def redo_last():
    flash(_("Ripetuto.") if undo.redo() else _("Niente da ripetere."), "success")
    return redirect(safe_next() or url_for("transactions.index"))


def _learn_from(tx: Transaction) -> None:
    """"Ricorda" ticked: the category becomes a rule for this counterparty (Settings → Regole)."""
    if "learn_rule" not in request.form:
        return
    rule = category_rules.learn(tx.counterparty, tx.category)
    if rule:
        flash(_("Da ora le transazioni di «%(counterparty)s» andranno in «%(category)s».", counterparty=tx.counterparty, category=tx.category), "success")
    else:
        flash(_("Per ricordare la categoria servono una categoria e una controparte (almeno 3 lettere)."), "warning")


def _render_form(tx: Transaction | None):
    category = request.form.get("category") if request.method == "POST" else (tx.category if tx else None)
    return render_template(
        "transactions/form.html", transaction=tx, action="edit" if tx else "new", v=_form_values(tx),
        categories=known_categories(category), next_url=safe_next(), accounts=accounts.all_accounts(),
        currencies=currency_service.CURRENCIES, tag_pool=all_tags(), fee_rules=broker.rules(accounts.all_accounts()),
        holdings=Holding.query.order_by(Holding.name).all(), debts=Debt.query.order_by(Debt.name).all(),
        documents=Document.query.filter_by(transaction_id=tx.id).order_by(Document.filename).all() if tx else [],
    )


@transactions_bp.route("/<int:tx_id>/edit", methods=["GET", "POST"])
def edit(tx_id):
    tx = db.get_or_404(Transaction, tx_id)
    if request.method == "POST":
        try:
            _tx_from_form(tx)
        except ValueError as exc:
            db.session.rollback()  # discard the half-applied changes
            flash(str(exc), "error")
            return _render_form(db.session.get(Transaction, tx_id))
        db.session.commit()
        flash(_("Transazione aggiornata."), "success")
        _learn_from(tx)
        return redirect(safe_next() or url_for("transactions.index"))
    return _render_form(tx)


@transactions_bp.route("/<int:tx_id>/delete", methods=["POST"])
def delete(tx_id):
    tx = db.get_or_404(Transaction, tx_id)
    undo.remember_deleted([tx])
    db.session.delete(tx)
    db.session.commit()
    flash(_("Transazione «%(description)s» eliminata.", description=tx.description), "success")
    return redirect(safe_next() or url_for("transactions.index"))


@transactions_bp.route("/delete-selected", methods=["POST"])
def delete_selected():
    ids = form_ids()
    if ids:
        undo.remember_deleted(Transaction.query.filter(Transaction.id.in_(ids)).all())
    deleted = Transaction.query.filter(Transaction.id.in_(ids)).delete(synchronize_session=False) if ids else 0
    db.session.commit()
    flash(_("%(deleted)s transazioni eliminate.", deleted=deleted) if deleted else _("Nessuna transazione selezionata."),
          "success" if deleted else "warning")
    return redirect(safe_next() or url_for("transactions.index"))


@transactions_bp.route("/assign-account", methods=["POST"])
def assign_account():
    account_id = request.form.get("account_id", type=int)
    account = db.session.get(Account, account_id) if account_id else None
    changed = accounts.assign(form_ids(), account.id if account else None)
    if not changed:
        flash(_("Nessuna transazione selezionata."), "warning")
    elif account:
        flash(_("%(changed)s transazioni messe sul conto «%(name)s».", changed=changed, name=account.name), "success")
    else:
        flash(_("%(changed)s transazioni messe senza conto.", changed=changed), "success")
    return redirect(safe_next() or url_for("transactions.index"))


@transactions_bp.route("/confirm-ai", methods=["POST"])
def confirm_ai():
    """The AI's category is right: take away the «da confermare (AI)» tag (one transaction or the selected ones)."""
    changed = 0
    for tx in Transaction.query.filter(Transaction.id.in_(form_ids()), Transaction.tags.any(AI_TAG)).all():
        tx.tags = [t for t in tx.tags if t != AI_TAG]
        changed += 1
    db.session.commit()
    if changed:
        flash(ngettext("%(num)d categoria confermata.", "%(num)d categorie confermate.", changed), "success")
    else:
        flash(_("Nessuna transazione da confermare tra quelle selezionate."), "warning")
    return redirect(safe_next() or url_for("transactions.index"))


# ── Duplicate finder ───────────────────────────────────────────────────────────

@transactions_bp.route("/duplicates")
def duplicates_page():
    sensitivity = request.args.get("sensitivity", "normale")
    sensitivity = sensitivity if sensitivity in duplicates.SENSITIVITY else "normale"
    window = request.args.get("window", type=int)
    window = window if window in (0, 1, 3, 7) else duplicates.DEFAULT_WINDOW_DAYS
    groups = duplicates.find_groups(window, duplicates.SENSITIVITY[sensitivity])
    return render_template("transactions/duplicates.html", groups=groups, sensitivity=sensitivity, window=window)


def _group_ids() -> list[int]:
    ids = form_ids()
    return sorted(t.id for t in Transaction.query.filter(Transaction.id.in_(ids))) if ids else []


@transactions_bp.route("/duplicates/dismiss", methods=["POST"])
def duplicates_dismiss():
    ids = _group_ids()
    if len(ids) >= 2:
        duplicates.dismiss(ids)
        flash(_("Segnate come transazioni diverse: non verranno più proposte come duplicati."), "success")
    return redirect(safe_next() or url_for("transactions.duplicates_page"))


@transactions_bp.route("/duplicates/keep", methods=["POST"])
def duplicates_keep():
    """Keep one transaction of a group and delete the others."""
    ids = _group_ids()
    keep = request.form.get("keep", type=int)
    if keep not in ids:
        flash(_("Scegli quale transazione tenere."), "error")
    else:
        others = [i for i in ids if i != keep]
        Transaction.query.filter(Transaction.id.in_(others)).delete(synchronize_session=False)
        db.session.commit()
        flash(_("Tenuta 1 transazione, eliminati %(count)s duplicati.", count=len(others)), "success")
    return redirect(safe_next() or url_for("transactions.duplicates_page"))


# ── REST API routes ────────────────────────────────────────────────────────────

@transactions_bp.get("/api")
@transactions_bp.output(TransactionListOut)
def api_list():
    transactions = Transaction.query.order_by(Transaction.date.desc()).all()
    return {"success": True, "transactions": transactions, "total": len(transactions)}


@transactions_bp.post("/api")
@transactions_bp.input(TransactionIn, arg_name="body")
@transactions_bp.output(TransactionOut, status_code=201)
def api_create(body):
    _check_accounts(body)
    parts = body.pop("splits", None)
    tx = Transaction(**body)
    _api_splits(tx, parts)
    db.session.add(tx)
    db.session.commit()
    return tx


def _api_splits(tx: Transaction, parts: list[dict] | None) -> None:
    """`splits` sent: set them (an empty list makes it an ordinary transaction again); left out: unchanged."""
    if parts is None:
        return
    try:
        splits.apply(tx, [(p.get("category"), Decimal(str(p["amount"]))) for p in parts])
    except ValueError as exc:
        db.session.rollback()
        abort(422, message=str(exc))


def _check_accounts(body: dict) -> None:
    for field in ("account_id", "counter_account_id"):
        if body.get(field) is not None and db.session.get(Account, body[field]) is None:
            abort(422, message=_("%(field)s: il conto %(id)s non esiste.", field=field, id=body[field]))


@transactions_bp.get("/api/<int:tx_id>")
@transactions_bp.output(TransactionOut)
def api_get(tx_id):
    return db.get_or_404(Transaction, tx_id)


@transactions_bp.put("/api/<int:tx_id>")
@transactions_bp.input(TransactionIn, arg_name="body")
@transactions_bp.output(TransactionOut)
def api_update(tx_id, body):
    tx = db.get_or_404(Transaction, tx_id)
    _check_accounts(body)
    parts = body.pop("splits", None)
    for key, value in body.items():
        setattr(tx, key, value)
    _api_splits(tx, parts)
    db.session.commit()
    return tx


@transactions_bp.delete("/api/<int:tx_id>")
@transactions_bp.output(DeleteOut)
def api_delete(tx_id):
    tx = db.get_or_404(Transaction, tx_id)
    db.session.delete(tx)
    db.session.commit()
    return {"success": True, "deleted_id": tx_id}



# ── Counterparties of saved transactions, read from the causale ────────────────

@transactions_bp.route("/fill-counterparties", methods=["POST"])
def fill_counterparties():
    """Give a counterparty (and its first tag) to the transactions without one, from the bank's causale."""
    filled = 0
    for tx in Transaction.query.filter(Transaction.counterparty.is_(None), Transaction.type != "transfer"):
        name = merchant.extract(tx.bank_description or tx.description, None if tx.bank_description else tx.notes)
        if not name:
            continue
        tx.counterparty = name
        if name.casefold() not in {t.casefold() for t in tx.tags or []}:
            tx.tags = [name, *(tx.tags or [])]
        filled += 1
    db.session.commit()
    flash(ngettext("%(num)s transazione ha ora la controparte, letta dalla causale.",
                   "%(num)s transazioni hanno ora la controparte, letta dalla causale.", filled) if filled
          else _("Nessuna controparte da aggiungere: le causali non nominano un esercente."), "success" if filled else "info")
    return redirect(safe_next() or url_for("transactions.index"))


# ── AI classification of saved transactions ──────────────────────────────────

def _unclassified_query():
    return Transaction.query.filter(or_(Transaction.category.is_(None), Transaction.category.in_(["", category_service.FALLBACK])),
                                    ~Transaction.splits.any())


def _classification_text(tx: Transaction) -> str:
    """The bank's causale when available (richest text), else description and notes."""
    return tx.bank_description or " ".join(filter(None, [tx.description, tx.notes]))


@transactions_bp.route("/classify", methods=["POST"])
def classify():
    """Ask the AI for category/counterparty suggestions and show them for review (nothing is saved)."""
    ids = form_ids()
    query = Transaction.query.filter(Transaction.id.in_(ids)) if ids else _unclassified_query()
    transactions = query.order_by(Transaction.date.desc(), Transaction.id.desc()).all()
    if not transactions:
        flash(_("Nessuna transazione da classificare."), "warning")
        return redirect(safe_next() or url_for("transactions.index"))
    items = [
        {"id": tx.id, "text": _classification_text(tx), "amount": tx.signed_amount} for tx in transactions
    ]
    try:
        suggestions = ai_classification.classify(items, known_categories())
    except ai_extraction.AIExtractionError as exc:
        flash(_("Classificazione AI non riuscita: %(exc)s", exc=exc), "error")
        return redirect(safe_next() or url_for("transactions.index"))
    return render_template(
        "transactions/classify.html",
        rows=[(tx, suggestions.get(tx.id)) for tx in transactions],
        model=ai_classification.model_name(),
        categories=known_categories(),
        next_url=safe_next(),
    )


@transactions_bp.route("/classify/apply", methods=["POST"])
def classify_apply():
    """Save the suggestions the user kept (possibly edited)."""
    ids = form_ids("apply")
    updated = 0
    for tx in Transaction.query.filter(Transaction.id.in_(ids)).all() if ids else []:
        category = (request.form.get(f"category-{tx.id}") or "").strip()
        counterparty = (request.form.get(f"counterparty-{tx.id}") or "").strip()
        if not category or tx.splits:  # a split made by hand is not overwritten
            continue
        tx.category = category
        tags = [t for t in (tx.tags or []) if t != AI_TAG]
        if counterparty:
            # the counterparty goes first among the tags (replacing the previous one), as in the form
            tags = [counterparty] + [t for t in tags if t.casefold() not in (counterparty.casefold(), (tx.counterparty or "").casefold())]
            tx.counterparty = counterparty
        if category == request.form.get(f"suggested-{tx.id}"):
            tags.append(AI_TAG)  # accepted as suggested: easy to find and double-check later
        tx.tags = tags
        updated += 1
    db.session.commit()
    flash(_("%(updated)s transazioni aggiornate.", updated=updated) if updated else _("Nessuna modifica applicata."), "success" if updated else "warning")
    return redirect(safe_next() or url_for("transactions.index"))
