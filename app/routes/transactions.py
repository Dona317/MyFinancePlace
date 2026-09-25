from datetime import date as date_type
from flask import render_template, request, redirect, url_for
from apiflask import APIBlueprint
from sqlalchemy import or_
from app.extensions import db
from app.models.transaction import Transaction
from app.services.analytics import month_bounds
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
    tx.amount        = float(request.form["amount"])
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
    )


@transactions_bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        tx = _tx_from_form(Transaction())
        db.session.add(tx)
        db.session.commit()
        return redirect(url_for("transactions.index"))
    return render_template("transactions/form.html", transaction=None, action="new")


@transactions_bp.route("/<int:tx_id>/edit", methods=["GET", "POST"])
def edit(tx_id):
    tx = db.get_or_404(Transaction, tx_id)
    if request.method == "POST":
        _tx_from_form(tx)
        db.session.commit()
        return redirect(url_for("transactions.index"))
    return render_template("transactions/form.html", transaction=tx, action="edit")


@transactions_bp.route("/<int:tx_id>/delete", methods=["POST"])
def delete(tx_id):
    tx = db.get_or_404(Transaction, tx_id)
    db.session.delete(tx)
    db.session.commit()
    return redirect(url_for("transactions.index"))


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
