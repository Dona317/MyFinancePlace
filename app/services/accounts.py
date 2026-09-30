"""
Bank accounts, cards and cash: the balance of each one and its reconciliation with a bank statement.

Balance of an account on a date = opening balance + income − expenses − transfers going out
+ transfers coming in (transactions whose counter_account is this account).
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import case, func

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.services.i18n import _l

KINDS = {"current": _l("Conto corrente"), "card": _l("Carta di credito"), "prepaid": _l("Carta prepagata"),
         "savings": _l("Conto deposito"), "cash": _l("Contanti"), "other": _l("Altro")}
ICONS = {"current": "bank", "card": "credit-card", "prepaid": "credit-card-2-front", "savings": "piggy-bank",
         "cash": "cash-coin", "other": "wallet2"}


def active() -> list[Account]:
    return Account.query.filter_by(active=True).order_by(Account.name).all()


def all_accounts() -> list[Account]:
    return Account.query.order_by(Account.active.desc(), Account.name).all()


def balance(account: Account, on: date | None = None) -> float:
    amount = func.abs(Transaction.amount)
    outgoing = case((Transaction.type == "income", amount), else_=-amount)  # expenses and transfers leave
    query = db.session.query(func.coalesce(func.sum(outgoing), 0)).filter(Transaction.account_id == account.id)
    incoming = db.session.query(func.coalesce(func.sum(amount), 0)).filter(
        Transaction.counter_account_id == account.id, Transaction.type == "transfer")
    if on is not None:
        query = query.filter(Transaction.date <= on)
        incoming = incoming.filter(Transaction.date <= on)
    total = Decimal(account.opening_balance or 0) + Decimal(query.scalar()) + Decimal(incoming.scalar())
    return round(float(total), 2)


def summary(on: date | None = None) -> list[dict]:
    counts = dict(db.session.query(Transaction.account_id, func.count()).group_by(Transaction.account_id).all())
    return [{"account": a, "balance": balance(a, on), "count": counts.get(a.id, 0)} for a in all_accounts()]


def unassigned_count() -> int:
    return Transaction.query.filter(Transaction.account_id.is_(None), Transaction.counter_account_id.is_(None)).count()


def reconcile(account: Account, on: date, statement_balance: Decimal) -> dict:
    """Compare the statement's balance with the app's on the same day; remember it when they match."""
    app_balance = balance(account, on)
    difference = round(float(statement_balance) - app_balance, 2)
    if difference == 0:
        account.reconciled_on, account.reconciled_balance = on, statement_balance
        db.session.commit()
    later = (Transaction.query.filter(Transaction.account_id == account.id, Transaction.date > on).count())
    return {"app_balance": app_balance, "statement_balance": float(statement_balance),
            "difference": difference, "on": on, "later": later}


def assign(transaction_ids: set[int], account_id: int | None) -> int:
    """Put transactions on an account (bulk action on the transactions list)."""
    if not transaction_ids:
        return 0
    changed = Transaction.query.filter(Transaction.id.in_(transaction_ids)).update(
        {"account_id": account_id}, synchronize_session=False)
    db.session.commit()
    return changed


def opening_total() -> float:
    return float(db.session.query(func.coalesce(func.sum(Account.opening_balance), 0)).scalar())
