"""
Bank accounts, cards and cash: the balance of each one and its reconciliation with a bank statement.

Balance of an account on a date = opening balance + income − expenses − transfers going out
+ transfers coming in (transactions whose counter_account is this account), all in the account's currency:
a transaction in another currency counts with the amount the bank charged (`account_amount`, or
`counter_amount` on the arriving side of a transfer) or, until that is entered, with the day's exchange rate.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import case, func

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.services import currency
from app.services.i18n import _l

KINDS = {"current": _l("Conto corrente"), "card": _l("Carta di credito"), "prepaid": _l("Carta prepagata"),
         "savings": _l("Conto deposito"), "cash": _l("Contanti"), "other": _l("Altro")}
ICONS = {"current": "bank", "card": "credit-card", "prepaid": "credit-card-2-front", "savings": "piggy-bank",
         "cash": "cash-coin", "other": "wallet2"}


def active() -> list[Account]:
    return Account.query.filter_by(active=True).order_by(Account.name).all()


def all_accounts() -> list[Account]:
    return Account.query.order_by(Account.active.desc(), Account.name).all()


def amount_in(tx: Transaction, account: Account) -> Decimal:
    """What `tx` moves on `account`, as a positive number in the account's currency."""
    own = account.currency or currency.BASE
    if (tx.currency or currency.BASE) == own:
        return abs(Decimal(tx.amount))
    entered = tx.account_amount if tx.account_id == account.id else tx.counter_amount
    if entered is not None:
        return abs(Decimal(entered))
    return currency.to_base(abs(Decimal(tx.amount)), tx.currency, tx.date, target=own)


def _foreign(account: Account):
    return func.coalesce(Transaction.currency, currency.BASE) != (account.currency or currency.BASE)


def balance(account: Account, on: date | None = None) -> float:
    amount = func.abs(Transaction.amount)
    outgoing = case((Transaction.type == "income", amount), else_=-amount)  # expenses and transfers leave
    leaving = Transaction.account_id == account.id
    arriving = (Transaction.counter_account_id == account.id) & (Transaction.type == "transfer")
    dated = [Transaction.date <= on] if on is not None else []
    # in the account's currency: summed by the database
    total = Decimal(account.opening_balance or 0)
    total += db.session.query(func.coalesce(func.sum(outgoing), 0)).filter(leaving, ~_foreign(account), *dated).scalar()
    total += db.session.query(func.coalesce(func.sum(amount), 0)).filter(arriving, ~_foreign(account), *dated).scalar()
    # in another currency (few): one by one, with the bank's amount or the exchange rate
    for tx in Transaction.query.filter(leaving | arriving, _foreign(account), *dated):
        value = amount_in(tx, account)
        total += value if tx.type == "income" or (tx.counter_account_id == account.id and tx.account_id != account.id) else -value
    return round(float(total), 2)


def estimated(account: Account) -> int:
    """Transactions in another currency counted with the exchange rate: the bank's amount is still missing."""
    return Transaction.query.filter(_foreign(account), (
        (Transaction.account_id == account.id) & Transaction.account_amount.is_(None)) | (
        (Transaction.counter_account_id == account.id) & (Transaction.type == "transfer")
        & Transaction.counter_amount.is_(None))).count()


def summary(on: date | None = None) -> list[dict]:
    """Each account's balance in its own currency, and in the base currency (to add them up)."""
    counts = dict(db.session.query(Transaction.account_id, func.count()).group_by(Transaction.account_id).all())
    target, day = currency.base(), on or date.today()
    rows = []
    for a in all_accounts():
        own = balance(a, on)
        rows.append({"account": a, "balance": own, "count": counts.get(a.id, 0), "symbol": currency.symbol(a.currency),
                     "balance_base": float(currency.to_base(own, a.currency, day, target=target))})
    return rows


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
    """The accounts' opening balances in the base currency (each converted on its account's first day)."""
    first = dict(db.session.query(Transaction.account_id, func.min(Transaction.date)).group_by(Transaction.account_id).all())
    target = currency.base()
    return float(sum(currency.to_base(a.opening_balance or 0, a.currency, first.get(a.id) or date.today(), target=target)
                     for a in Account.query.all()))
