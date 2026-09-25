from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from flask import render_template, request, redirect, url_for, flash
from apiflask import APIBlueprint
from sqlalchemy import or_
from app.extensions import db
from app.models.transaction import Transaction
from app.services import ai_classification, ai_extraction, duplicates
from app.services.analytics import month_bounds
from app.services.bank_import import valid_amount
from app.services.categories import known_categories
from app.schemas.transaction import TransactionIn, TransactionOut, TransactionListOut
from app.schemas.common import DeleteOut

transactions_bp = APIBlueprint(
    "transactions",
    __name__,
    url_prefix="/transactions",
    tag="Transactions"
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tx_from_form(tx: Transaction) -> Transaction:
    """Populate a Transaction object with values from request.form."""
    tx.date          = date_type.fromisoformat(request.form["date"])
    tx.description   = request.form["description"]
    tx.amount        = abs(Decimal(request.form["amount"].replace(",", ".")))
    if not valid_amount(tx.amount) or not tx.description.strip() or request.form["type"] not in ("income", "expense", "transfer"):
        raise ValueError("invalid transaction")
    tx.currency      = request.form.get("currency", "EUR")
    tx.type          = request.form["type"]
    tx.category      = request.form.get("category") or None
    tx.counterparty  = request.form.get("counterparty") or None
    tx.tags          = [t.strip() for t in request.form.get("tags", "").split(",") if t.strip()]
    tx.is_recurring  = "is_recurring" in request.form
    tx.recurrence    = request.form.get("recurrence") or None
    tx.recurrence_end = (
        date_type.fromisoformat(request.form["recurrence_end"])
        if request.form.get("recurrence_end") else None
    )
    tx.notes = request.form.get("notes") or None
    return tx


# ── HTML routes ────────────────────────────────────────────────────────────────

def _filtered_query(filters: dict):
    """Apply the filter-bar values (q, type, category, month=YYYY-MM) to the transactions query."""
    query = Transaction.query
    if filters["q"]:
        pattern = f"%{filters['q']}%"
        query = query.filter(or_(
            Transaction.description.ilike(pattern),
            Transaction.counterparty.ilike(pattern),
            Transaction.notes.ilike(pattern),
        ))
    if filters["type"]:
        query = query.filter(Transaction.type == filters["type"])
    if filters["category"]:
        query = query.filter(Transaction.category == filters["category"])
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
    filters = {key: request.args.get(key, "").strip() for key in ("q", "type", "category", "month")}
    transactions = _filtered_query(filters).order_by(Transaction.date.desc(), Transaction.id.desc()).all()
    categories = [
        row[0] for row in
        db.session.query(Transaction.category).filter(Transaction.category.isnot(None))
        .distinct().order_by(Transaction.category).all()
    ]
    return render_template(
        "transactions/index.html",
        transactions=transactions,
        filters=filters,
        categories=categories,
        all_categories=known_categories(),
        duplicate_groups=len(duplicates.find_groups()),
        unclassified=_unclassified_query().count(),
        ai_classifier=ai_classification.describe(),
        ai_cloud=ai_extraction.provider() == "anthropic",
    )


@transactions_bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        try:
            tx = _tx_from_form(Transaction())
        except (KeyError, ValueError, InvalidOperation):
            flash("Controlla i dati: data, descrizione, importo e tipo sono obbligatori.", "error")
            return render_template("transactions/form.html", transaction=None, action="new", categories=known_categories())
        db.session.add(tx)
        db.session.commit()
        flash("Transazione aggiunta.", "success")
        return redirect(url_for("transactions.index"))
    return render_template("transactions/form.html", transaction=None, action="new", categories=known_categories())


@transactions_bp.route("/<int:tx_id>/edit", methods=["GET", "POST"])
def edit(tx_id):
    tx = db.get_or_404(Transaction, tx_id)
    if request.method == "POST":
        try:
            _tx_from_form(tx)
        except (KeyError, ValueError, InvalidOperation):
            db.session.rollback()  # discard the half-applied changes
            flash("Controlla i dati: data, descrizione, importo e tipo sono obbligatori.", "error")
            return redirect(url_for("transactions.edit", tx_id=tx_id, next=_safe_next()))
        db.session.commit()
        flash("Transazione aggiornata.", "success")
        return redirect(_safe_next() or url_for("transactions.index"))
    return render_template(
        "transactions/form.html", transaction=tx, action="edit",
        categories=known_categories(tx.category), next_url=_safe_next(),
    )


def _safe_next() -> str | None:
    """Local path to go back to after an action (never an external URL)."""
    target = request.values.get("next") or ""
    return target if target.startswith("/") and not target.startswith("//") and "\\" not in target else None


@transactions_bp.route("/<int:tx_id>/delete", methods=["POST"])
def delete(tx_id):
    tx = db.get_or_404(Transaction, tx_id)
    db.session.delete(tx)
    db.session.commit()
    flash(f"Transazione «{tx.description}» eliminata.", "success")
    return redirect(_safe_next() or url_for("transactions.index"))


@transactions_bp.route("/delete-selected", methods=["POST"])
def delete_selected():
    ids = {int(i) for i in request.form.getlist("ids") if i.isdigit()}
    deleted = Transaction.query.filter(Transaction.id.in_(ids)).delete(synchronize_session=False) if ids else 0
    db.session.commit()
    flash(f"{deleted} transazioni eliminate." if deleted else "Nessuna transazione selezionata.",
          "success" if deleted else "warning")
    return redirect(_safe_next() or url_for("transactions.index"))


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
    ids = sorted({int(i) for i in request.form.getlist("ids") if i.isdigit()})
    return [t.id for t in Transaction.query.filter(Transaction.id.in_(ids))] if ids else []


@transactions_bp.route("/duplicates/dismiss", methods=["POST"])
def duplicates_dismiss():
    ids = _group_ids()
    if len(ids) >= 2:
        duplicates.dismiss(ids)
        flash("Segnate come transazioni diverse: non verranno più proposte come duplicati.", "success")
    return redirect(_safe_next() or url_for("transactions.duplicates_page"))


@transactions_bp.route("/duplicates/keep", methods=["POST"])
def duplicates_keep():
    """Keep one transaction of a group and delete the others."""
    ids = _group_ids()
    keep = request.form.get("keep", type=int)
    if keep not in ids:
        flash("Scegli quale transazione tenere.", "error")
    else:
        others = [i for i in ids if i != keep]
        Transaction.query.filter(Transaction.id.in_(others)).delete(synchronize_session=False)
        db.session.commit()
        flash(f"Tenuta 1 transazione, eliminati {len(others)} duplicati.", "success")
    return redirect(_safe_next() or url_for("transactions.duplicates_page"))


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
    tx = Transaction(**body)
    db.session.add(tx)
    db.session.commit()
    return tx


@transactions_bp.get("/api/<int:tx_id>")
@transactions_bp.output(TransactionOut)
def api_get(tx_id):
    return db.get_or_404(Transaction, tx_id)


@transactions_bp.put("/api/<int:tx_id>")
@transactions_bp.input(TransactionIn, arg_name="body")
@transactions_bp.output(TransactionOut)
def api_update(tx_id, body):
    tx = db.get_or_404(Transaction, tx_id)
    for key, value in body.items():
        setattr(tx, key, value)
    db.session.commit()
    return tx


@transactions_bp.delete("/api/<int:tx_id>")
@transactions_bp.output(DeleteOut)
def api_delete(tx_id):
    tx = db.get_or_404(Transaction, tx_id)
    db.session.delete(tx)
    db.session.commit()
    return {"success": True, "deleted_id": tx_id}



# ── AI classification of saved transactions ──────────────────────────────────

MAX_TO_CLASSIFY = 300


def _unclassified_query():
    return Transaction.query.filter(or_(Transaction.category.is_(None), Transaction.category.in_(["", "Altro"])))


def _classification_text(tx: Transaction) -> str:
    """The bank's causale when available (richest text), else description and notes."""
    return tx.bank_description or " ".join(filter(None, [tx.description, tx.notes]))


@transactions_bp.route("/classify", methods=["POST"])
def classify():
    """Ask the AI for category/counterparty suggestions and show them for review (nothing is saved)."""
    ids = {int(i) for i in request.form.getlist("ids") if i.isdigit()}
    query = Transaction.query.filter(Transaction.id.in_(ids)) if ids else _unclassified_query()
    transactions = query.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(MAX_TO_CLASSIFY).all()
    if not transactions:
        flash("Nessuna transazione da classificare.", "warning")
        return redirect(_safe_next() or url_for("transactions.index"))
    items = [
        {"id": tx.id, "text": _classification_text(tx), "amount": -float(tx.amount) if tx.type == "expense" else float(tx.amount)}
        for tx in transactions
    ]
    try:
        suggestions = ai_classification.classify(items, known_categories())
    except ai_extraction.AIExtractionError as exc:
        flash(f"Classificazione AI non riuscita: {exc}", "error")
        return redirect(_safe_next() or url_for("transactions.index"))
    return render_template(
        "transactions/classify.html",
        rows=[(tx, suggestions.get(tx.id)) for tx in transactions],
        model=ai_classification.model_name(),
        categories=known_categories(),
        next_url=_safe_next(),
    )


@transactions_bp.route("/classify/apply", methods=["POST"])
def classify_apply():
    """Save the suggestions the user kept (possibly edited)."""
    ids = {int(i) for i in request.form.getlist("apply") if i.isdigit()}
    updated = 0
    for tx in Transaction.query.filter(Transaction.id.in_(ids)).all() if ids else []:
        category = (request.form.get(f"category-{tx.id}") or "").strip()[:100]
        counterparty = (request.form.get(f"counterparty-{tx.id}") or "").strip()[:255]
        if not category:
            continue
        tx.category = category
        if counterparty:
            tx.counterparty = counterparty
        tags = [t for t in (tx.tags or []) if t != "categoria-ai"]
        if category == request.form.get(f"suggested-{tx.id}"):
            tags.append("categoria-ai")  # accepted as suggested: easy to find and double-check later
        tx.tags = tags
        updated += 1
    db.session.commit()
    flash(f"{updated} transazioni aggiornate." if updated else "Nessuna modifica applicata.", "success" if updated else "warning")
    return redirect(_safe_next() or url_for("transactions.index"))
