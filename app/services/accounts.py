"""
Bank accounts, cards and cash: the balance of each one and its reconciliation with a bank statement.

Every archive has two fixed accounts (F30): «Contanti», the cash, which can hold several currencies (what is in the
wallet in each one, and its value in the base currency), and «Debiti», what is owed to no bank in particular (bought
now and paid later): its balance below zero is a liability. Both are there from the start, can stay at zero and are
listed only once they are used; their name and kind do not change and they are not deleted.

Balance of an account on a date = opening balance + income − expenses − transfers going out
+ transfers coming in (transactions whose counter_account is this account), all in the account's currency:
a transaction in another currency counts with the amount the bank charged (`account_amount`, or
`counter_amount` on the arriving side of a transfer) or, until that is entered, with the day's exchange rate.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, func

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.services import currency
from app.services.i18n import _l

KINDS = {"current": _l("Conto corrente"), "card": _l("Carta di credito"), "prepaid": _l("Carta prepagata"),
         "savings": _l("Conto deposito"), "cash": _l("Contanti"), "debt": _l("Debiti"), "other": _l("Altro")}
ICONS = {"current": "bank", "card": "credit-card", "prepaid": "credit-card-2-front", "savings": "piggy-bank",
         "cash": "cash-coin", "debt": "receipt", "other": "wallet2"}
# the fixed accounts: role → (name, kind)
FIXED = {"cash": ("Contanti", "cash"), "debt": ("Debiti", "debt")}


def ensure_fixed() -> bool:
    """Contanti and Debiti exist (made the first time; an earlier cash account becomes the fixed one). True when
    something was made or marked."""
    changed = False
    for role, (name, kind) in FIXED.items():
        if Account.query.filter_by(fixed=role).first() is not None:
            continue
        account = Account.query.filter_by(kind=kind, fixed=None).order_by(Account.active.desc(), Account.id).first()
        if account is None:
            unique, number = name, 2
            while Account.query.filter_by(name=unique).first() is not None:
                unique, number = f"{name} {number}", number + 1
            account = Account(name=unique, kind=kind, currency=currency.base())
            db.session.add(account)
        account.fixed, account.kind, account.active = role, kind, True
        changed = True
    if changed:
        db.session.commit()
    return changed


def fixed(role: str) -> Account | None:
    return Account.query.filter_by(fixed=role).first()


def used(account: Account) -> bool:
    """A fixed account is listed once it is used: an opening amount, or a transaction on it."""
    if account.fixed is None or account.opening_balance or any((account.opening_foreign or {}).values()):
        return True
    return Transaction.query.filter((Transaction.account_id == account.id)
                                    | (Transaction.counter_account_id == account.id)).first() is not None


def debt_ids() -> list[int]:
    return [a.id for a in Account.query.filter_by(kind="debt")]


def foreign_openings(account: Account) -> dict[str, Decimal]:
    """The opening amounts of the cash in currencies other than its own, cleaned."""
    out = {}
    for code, amount in (account.opening_foreign or {}).items():
        try:
            value = Decimal(str(amount))
        except ArithmeticError:
            continue
        if code in currency.CURRENCIES and code != account.currency and value:
            out[code] = value
    return out


def by_currency(account: Account, on: date | None = None) -> dict[str, float]:
    """What the cash holds in each currency (opening + what came in − what went out, each in its own currency)."""
    totals = defaultdict(Decimal)
    totals[account.currency or currency.BASE] += Decimal(account.opening_balance or 0)
    for code, value in foreign_openings(account).items():
        totals[code] += value
    touching = (Transaction.account_id == account.id) | (
        (Transaction.counter_account_id == account.id) & (Transaction.type == "transfer"))
    query = Transaction.query.filter(touching)
    if on is not None:
        query = query.filter(Transaction.date <= on)
    for tx in query:
        if tx.type == "transfer" and tx.account_id == tx.counter_account_id:
            continue
        value = abs(Decimal(tx.amount))
        arriving = tx.counter_account_id == account.id and tx.account_id != account.id
        totals[tx.currency or currency.BASE] += value if tx.type == "income" or arriving else -value
    return {code: round(float(value), 2) for code, value in sorted(totals.items()) if value}


def active() -> list[Account]:
    return Account.query.filter_by(active=True).order_by(Account.name).all()


def all_accounts() -> list[Account]:
    return Account.query.order_by(Account.active.desc(), Account.name).all()


def favorite() -> Account | None:
    """The favourite account (the star), if it is still active: proposed for every imported statement."""
    return Account.query.filter_by(favorite=True, active=True).first()


def set_favorite(account: Account | None) -> None:
    """One favourite at most: the star moves to `account` (None: no favourite)."""
    Account.query.filter(Account.favorite.is_(True)).update({"favorite": False}, synchronize_session=False)
    if account is not None:
        account.favorite = True


def masked(number: str | None) -> str:
    """«•••• 3456»: the last four characters of an IBAN or account number, the rest hidden."""
    clean = (number or "").replace(" ", "")
    return f"•••• {clean[-4:]}" if clean else ""


def found_in(text: str) -> Account | None:
    """The active account whose IBAN or account number appears in a statement's text (spaces ignored), if one."""
    plain = text.replace(" ", "").upper()
    if not plain:
        return None
    hits = [a for a in active() for code in (a.iban, a.account_number)
            if code and len(code.replace(" ", "")) >= 6 and code.replace(" ", "").upper() in plain]
    unique = {a.id: a for a in hits}
    return next(iter(unique.values())) if len(unique) == 1 else None


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
        total += change(tx, account)
    # the cash's opening amounts in other currencies, at the day's exchange rate
    for code, value in foreign_openings(account).items():
        total += Decimal(str(currency.to_base(value, code, on or date.today(), target=account.currency or currency.BASE)))
    return round(float(total), 2)


def owed(on: date | None = None) -> float:
    """What the Debiti accounts owe (in the base currency): their balance below zero."""
    target, day = currency.base(), on or date.today()
    return round(sum(max(0.0, -float(currency.to_base(balance(a, on), a.currency, day, target=target)))
                     for a in Account.query.filter_by(kind="debt")), 2)


def change(tx: Transaction, account: Account) -> Decimal:
    """How `tx` moves the balance of `account` (positive: money in), in the account's currency."""
    if tx.type == "transfer" and tx.account_id == tx.counter_account_id == account.id:
        return Decimal(0)  # from the account to itself
    value = amount_in(tx, account)
    arriving = tx.counter_account_id == account.id and tx.account_id != account.id
    return value if tx.type == "income" or arriving else -value


def average_balance(account: Account, start: date, end: date) -> float:
    """The average of the balance at the end of each day from `start` to `end` (the stamp duty's giacenza media)."""
    days = (end - start).days + 1
    if days <= 0:
        return 0.0
    running = Decimal(str(balance(account, start - timedelta(days=1))))
    moves = defaultdict(Decimal)
    touching = (Transaction.account_id == account.id) | (
        (Transaction.counter_account_id == account.id) & (Transaction.type == "transfer"))
    for tx in Transaction.query.filter(touching, Transaction.date >= start, Transaction.date <= end):
        moves[tx.date] += change(tx, account)
    total = Decimal(0)
    for offset in range(days):
        running += moves.get(start + timedelta(days=offset), Decimal(0))
        total += running
    return round(float(total / days), 2)


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
    total = 0.0
    for a in Account.query.filter(Account.kind != "debt"):  # a debt's opening is owed, not cash
        day = first.get(a.id) or date.today()
        total += float(currency.to_base(a.opening_balance or 0, a.currency, day, target=target))
        total += sum(float(currency.to_base(v, code, day, target=target)) for code, v in foreign_openings(a).items())
    return total
