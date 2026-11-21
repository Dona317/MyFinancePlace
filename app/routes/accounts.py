from datetime import date

from apiflask import APIBlueprint
from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.routes.helpers import delete_and_redirect, form_choice, form_date, form_decimal, form_text, safe_next, save_form
from app.services import accounts, cash, deadlines, display, family, owners, periods, securities, wealth
from app.services import cards as card_service
from app.services import currency as currency_service
from app.services.parsing import to_decimal
from app.services.tax_rules import REGIMES as TAX_REGIMES

accounts_bp = APIBlueprint(
    "accounts",
    __name__,
    url_prefix="/accounts",
    tag="Accounts"
)

CURRENCIES = list(currency_service.CURRENCIES)
# F96: the kinds of account a securities account can settle on (not a card, the cash or the debts)
DOSSIER_KINDS = ("current", "savings", "other")


def _foreign_from_form(account: Account) -> dict | None:
    """The cash in other currencies at the start: pairs of currency and amount (a currency once, its own left out)."""
    out = {}
    for code, raw in zip(request.form.getlist("foreign_code"), request.form.getlist("foreign_amount"), strict=False):
        code = (code or "").upper()
        if code not in CURRENCIES or code == account.currency or not (raw or "").strip():
            continue
        value = to_decimal(raw)
        if value is None:
            raise ValueError(_("Importo non valido per %(code)s.", code=code))
        out[code] = str(value)
    return out or None


def _account_from_form(account: Account) -> Account:
    if account.fixed is None:
        account.name = form_text("name", _("Nome"), required=True)
        account.kind = form_choice("kind", _("Tipo"), accounts.KINDS)
    currency = (request.form.get("currency") or "EUR").upper()
    account.currency = currency if currency in CURRENCIES else "EUR"
    account.opening_balance = form_decimal("opening_balance", _("Saldo iniziale"), allow_negative=True) or 0
    account.iban_tail = (form_text("iban_tail", _("Ultime cifre IBAN / carta")) or "")[-10:] or None
    owners.set_iban(account, request.form.get("iban"))
    account.bank = form_text("bank", _("Banca"))
    account.account_number = (form_text("account_number", _("Numero conto")) or "").replace(" ", "") or None
    account.notes = form_text("notes", _("Note"))
    account.owner = family.from_form()
    account.active = "active" in request.form
    account.abroad = "abroad" in request.form  # the account's own: IVAFE instead of the stamp duty
    if account.kind == "cash":
        account.opening_foreign = _foreign_from_form(account)
    if account.fixed:
        account.active = True  # a fixed account is never closed: it can stay at zero
    duplicate = Account.query.filter(Account.name == account.name, Account.id != account.id).first()
    if duplicate:
        raise ValueError(_("Esiste già un conto chiamato «%(name)s».", name=account.name))
    # F96: «Ha anche un conto titoli» — the securities account linked to this one, with its regime and commissions
    wanted = "has_dossier" in request.form and account.kind in DOSSIER_KINDS
    dossier = {}
    if wanted:
        dossier = {"name": form_text("dossier_name", _("Nome del conto titoli")),
                   "tax_regime": form_choice("tax_regime", _("Regime delle plusvalenze"), TAX_REGIMES)
                   if request.form.get("tax_regime") else "amministrato",
                   "fee_fixed": form_decimal("fee_fixed", _("Commissione fissa")),
                   "fee_percent": form_decimal("fee_percent", _("Commissione percentuale")),
                   "fee_min": form_decimal("fee_min", _("Commissione minima")),
                   "fee_max": form_decimal("fee_max", _("Commissione massima"))}
        if dossier["fee_min"] is not None and dossier["fee_max"] is not None and dossier["fee_min"] > dossier["fee_max"]:
            raise ValueError(_("Commissioni: il minimo non può superare il massimo."))
    db.session.add(account)
    db.session.flush()  # a new account needs its id before its securities account
    securities.link_dossier(account, wanted, dossier)
    return account


def _render_form(account, values):
    return render_template("accounts/form.html", tax_regimes=TAX_REGIMES, account=account, kinds=accounts.KINDS, currencies=CURRENCIES,
                           dossier=securities.dossier_of(account), dossier_kinds=DOSSIER_KINDS,
                           values=values, foreign=accounts.foreign_openings(account) if account else {}, card_kinds=card_service.KINDS, card_icons=card_service.ICONS, networks=card_service.NETWORKS)


@accounts_bp.route("/")
def index():
    # the banks and cards in the table; Contanti and «Debiti totali» (the debts of the Debiti section plus the Debiti
    # account) as two cards on top, at a glance (F30)
    rows = accounts.summary()
    cash = next((r for r in rows if r["account"].fixed == "cash"), None)
    debt = next((r for r in rows if r["account"].fixed == "debt"), None)
    rows = [r for r in rows if not r["account"].fixed]
    # UI-21: the page in tabs — the overview by kind, the accounts, the cards, the reconciliations
    tab = request.args.get("tab", "overview")
    tab = tab if tab in ACCOUNT_TABS else "overview"
    today = date.today()
    active_rows = [r for r in rows if r["account"].active]
    by_kind: dict[str, float] = {}
    for r in active_rows:
        by_kind[r["account"].kind] = by_kind.get(r["account"].kind, 0.0) + float(r["balance_base"])
    reconcile = sorted(active_rows, key=lambda r: r["account"].reconciled_on or date.min)
    for r in reconcile:
        r["days"] = (today - r["account"].reconciled_on).days if r["account"].reconciled_on else None
    from app.routes.cards import account_cards  # the cards of each account with the month's spending
    card_rows = [dict(item, account=r["account"]) for r in active_rows for item in account_cards(r["account"])] \
        if tab == "cards" else []
    return render_template(
        "accounts/index.html", rows=rows, kinds=accounts.KINDS, icons=accounts.ICONS, cash=cash, debt_account=debt,
        tab=tab, by_kind=sorted(by_kind.items(), key=lambda item: -abs(item[1])), reconcile=reconcile,
        card_rows=card_rows, stale_days=RECONCILE_STALE_DAYS,
        currencies=accounts.by_currency(cash["account"]) if cash else {},
        debts=wealth.debt_picture(),
        total=sum(r["balance_base"] for r in rows if r["account"].active and r["account"].kind != "debt")
        + (cash["balance_base"] if cash else 0),
        unassigned=accounts.unassigned_count(),
        dossiers_of={aid: [(d, securities.value(d)) for d in ds] for aid, ds in securities.dossiers_by_account().items()},
    )


ACCOUNT_TABS = ("overview", "accounts", "cards", "reconcile")
RECONCILE_STALE_DAYS = 90  # as Salute dei dati: an account not reconciled for longer is flagged


@accounts_bp.route("/<int:account_id>")
def detail(account_id):
    account = db.get_or_404(Account, account_id)
    recent = (Transaction.query
              .filter((Transaction.account_id == account.id) | (Transaction.counter_account_id == account.id))
              .order_by(Transaction.date.desc(), Transaction.id.desc()).limit(50).all())
    return _render_detail(account, recent, None)


HISTORY_MONTHS = (3, 6, 12, 24, 36, 60)


def _history_months() -> int:
    """F101: the range of the balance chart of an account, in the one period box (the last 12 months by default)."""
    value = request.args.get("months", 12, type=int)
    return value if value in HISTORY_MONTHS else 12


def _render_detail(account: Account, recent: list[Transaction], result: dict | None):
    balance = accounts.balance(account)
    # the balance after each movement listed (not after a reconciliation, which lists only the ones going out)
    running = accounts.running_balances(account, recent, balance) if result is None else None
    return render_template("accounts/detail.html", account=account, balance=balance, running=running,
                           history=accounts.balance_history(account, _history_months()), history_months=_history_months(),
                           debts=wealth.debt_picture() if account.fixed == "debt" else None,
                           currencies=accounts.by_currency(account) if account.kind == "cash" else {},
                           tracking=cash.tracking(account, date.today().year) if account.kind == "cash" else None,
                           recent=recent, kinds=accounts.KINDS, today=date.today(), result=result,
                           reconciliations=accounts.reconciliations(account),
                           reconcile_reminder=deadlines.reconcile_reminder(account),
                           remind_default=periods.add_months(date.today(), 1),
                           symbol=currency_service.symbol(account.currency), estimated=accounts.estimated(account),
                           in_account=lambda tx: accounts.amount_in(tx, account),
                           dossiers=[(d, securities.value(d)) for d in securities.dossiers_by_account().get(account.id, [])],
                           regimes=TAX_REGIMES,
                           cards=_cards.account_cards(account), card_kinds=card_service.KINDS,
                           card_icons=card_service.ICONS, networks=card_service.NETWORKS)


@accounts_bp.route("/<int:account_id>/reconcile", methods=["POST"])
def reconcile(account_id):
    account = db.get_or_404(Account, account_id)
    try:
        on = form_date("on", _("Data dell'estratto"), required=True)
        statement = form_decimal("statement_balance", _("Saldo dell'estratto"), required=True, allow_negative=True)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("accounts.detail", account_id=account.id))
    result = accounts.reconcile(account, on, statement)
    deadlines.reconciled(account, on)  # T11: the reminders that asked for this reconciliation are done
    db.session.commit()
    if result["difference"] == 0:
        flash(_("Conto riconciliato al %(on)s: il saldo coincide con quello del conto.", on=display.day(on)), "success")
    else:  # F104: the difference recorded on its own, out of the analyses
        flash(_("Conto riconciliato al %(on)s: registrata una «Riconciliazione» di %(amount)s.", on=display.day(on),
                amount=display.money(abs(result["difference"]))), "success")
    recent = (Transaction.query.filter(Transaction.account_id == account.id, Transaction.date <= on)
              .order_by(Transaction.date.desc(), Transaction.id.desc()).limit(50).all())
    return _render_detail(account, recent, result)


@accounts_bp.route("/<int:account_id>/reconcile/reminder", methods=["POST"])
def reconcile_reminder(account_id):
    """T11: «remind me to reconcile in…» — the window shown after a reconciliation: one month, three, a year or a
    date; the reminder goes to the Scadenzario and opens this account."""
    account = db.get_or_404(Account, account_id)
    months = deadlines.RECONCILE_AGAIN.get(request.form.get("when", ""))
    try:
        due = periods.add_months(date.today(), months) if months else form_date("on", _("Data del promemoria"), required=True)
        if due <= date.today():
            raise ValueError(_("Data del promemoria: scegli un giorno dopo oggi."))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("accounts.detail", account_id=account.id) + "#reconcile")
    deadlines.remind_to_reconcile(account, due)
    flash(_("Promemoria creato: riconcilia «%(name)s» il %(day)s.", name=account.name, day=display.day(due)), "success")
    return redirect(url_for("accounts.detail", account_id=account.id) + "#reconcile")


@accounts_bp.route("/<int:account_id>/count", methods=["POST"])
def count_cash(account_id):
    """The cash wallet counted (F22): the difference with the balance is recorded."""
    account = db.get_or_404(Account, account_id)
    try:
        counted = form_decimal("counted", _("Contanti che hai ora"), required=True)
        tx = cash.count(account, counted)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("accounts.detail", account_id=account.id))
    db.session.commit()
    if tx is None:
        flash(_("Tutto torna: nel portafoglio c'è quanto dice l'app."), "success")
    else:
        flash(_("Registrato «%(category)s» per %(amount)s.", category=tx.category, amount=display.money(tx.amount)), "success")
    return redirect(url_for("accounts.detail", account_id=account.id))


@accounts_bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        return save_form(Account(), _account_from_form, _render_form,
                         lambda a: _("Conto «%(name)s» aggiunto.", name=a.name), lambda a: safe_next() or url_for("accounts.index"))
    return _render_form(None, {})


@accounts_bp.route("/<int:account_id>/edit", methods=["GET", "POST"])
def edit(account_id):
    account = db.get_or_404(Account, account_id)
    if request.method == "POST":
        return save_form(account, _account_from_form, _render_form,
                         lambda a: _("Conto «%(name)s» aggiornato.", name=a.name),
                         lambda a: safe_next() or url_for("accounts.detail", account_id=a.id))
    return _render_form(account, {})


@accounts_bp.route("/<int:account_id>/favorite", methods=["POST"])
def favorite(account_id):
    """The star: this account becomes the favourite one (proposed when importing a statement); again, none is."""
    account = db.get_or_404(Account, account_id)
    accounts.set_favorite(None if account.favorite else account)
    db.session.commit()
    return redirect(request.form.get("next") or url_for("accounts.index"))


@accounts_bp.route("/<int:account_id>/delete", methods=["POST"])
def delete(account_id):
    account = db.get_or_404(Account, account_id)
    if account.fixed:
        flash(_("«%(name)s» c'è sempre: può restare a zero, ma non si elimina.", name=account.name), "warning")
        return redirect(url_for("accounts.index"))
    dossier = securities.dossier_of(account)
    if dossier is not None and securities.in_use(dossier):
        # F96: the securities of its securities account would lose their liquidity — closing it keeps both
        flash(_("«%(name)s» ha un conto titoli con operazioni («%(dossier)s»): non si elimina. Toglile la spunta "
                "«Conto attivo» per chiuderlo.", name=account.name, dossier=dossier.name), "warning")
        return redirect(url_for("accounts.detail", account_id=account.id))
    if dossier is not None:
        db.session.delete(dossier)  # an unused securities account goes with its account
    return delete_and_redirect(account, _("Conto «%(name)s» eliminato: le sue transazioni restano, senza conto.",
                                          name=account.name), url_for("accounts.index"))


from app.routes import cards as _cards  # noqa: E402,F401  (the payment cards' routes, F41, on this blueprint)
