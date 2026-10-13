"""The REST API of the transactions (/transactions/api), on the same blueprint as the pages."""
from decimal import Decimal

from apiflask import abort
from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.routes.transactions import transactions_bp
from app.schemas.common import DeleteOut
from app.schemas.transaction import TransactionIn, TransactionListOut, TransactionOut
from app.services import splits

# ── Routes ────────────────────────────────────────────────────────────

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
