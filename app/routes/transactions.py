from flask import render_template, request, redirect, url_for
from apiflask import APIBlueprint
from app.schemas.transaction import TransactionIn, TransactionOut, TransactionListOut
from app.schemas.common import DeleteOut

transactions_bp = APIBlueprint(
    "transactions",
    __name__,
    url_prefix="/transactions",
    tag="Transactions"
)


# ── HTML routes ────────────────────────────────────────────────────────────────

@transactions_bp.route("/")
def index():
    transactions = []
    return render_template("transactions/index.html", transactions=transactions)


@transactions_bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        return redirect(url_for("transactions.index"))
    return render_template("transactions/form.html", transaction=None, action="new")


@transactions_bp.route("/<int:tx_id>/edit", methods=["GET", "POST"])
def edit(tx_id):
    transaction = None
    if request.method == "POST":
        return redirect(url_for("transactions.index"))
    return render_template("transactions/form.html", transaction=transaction, action="edit")


@transactions_bp.route("/<int:tx_id>/delete", methods=["POST"])
def delete(tx_id):
    return redirect(url_for("transactions.index"))


# ── REST API routes ────────────────────────────────────────────────────────────

@transactions_bp.get("/api")
@transactions_bp.output(TransactionListOut)
def api_list():
    # TODO: fetch from DB
    transactions = []
    return {"success": True, "transactions": transactions, "total": len(transactions)}


@transactions_bp.post("/api")
@transactions_bp.input(TransactionIn, arg_name="body")
@transactions_bp.output(TransactionOut, status_code=201)
def api_create(body):
    # TODO: save to DB and return the created object
    new_tx = {"id": 1, **body}
    return new_tx


@transactions_bp.get("/api/<int:tx_id>")
@transactions_bp.output(TransactionOut)
def api_get(tx_id):
    # TODO: fetch from DB by id
    transaction = {"id": tx_id, "title": "Example", "amount": 0.0,
                   "date": "2026-06-15", "category": "", "type": "expense", "notes": ""}
    return transaction


@transactions_bp.put("/api/<int:tx_id>")
@transactions_bp.input(TransactionIn, arg_name="body")
@transactions_bp.output(TransactionOut)
def api_update(tx_id, body):
    # TODO: update in DB
    updated_tx = {"id": tx_id, **body}
    return updated_tx


@transactions_bp.delete("/api/<int:tx_id>")
@transactions_bp.output(DeleteOut)
def api_delete(tx_id):
    # TODO: delete from DB
    return {"success": True, "deleted_id": tx_id}
