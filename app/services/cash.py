"""
Banca ↔ Contanti: a cash withdrawal from a bank account is a transfer into the cash account («Contanti»), and a
cash deposit the reverse. The money spent from the cash account is then an ordinary expense of that account, so
it is counted once, when it is spent, not again when it was withdrawn (transfers do not count in the totals).
"""
import re

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.services.parsing import normalize

CASH_NAME = "Contanti"
WITHDRAWAL = ("prelievo", "bancomat", "atm")   # money leaves the bank account
DEPOSIT = ("versamento",)                      # money goes back into the bank account


def cash_account(create: bool = True) -> Account | None:
    """The cash account: the one of kind «cash», else one named «Contanti», else (when `create`) a new one."""
    account = Account.query.filter_by(kind="cash").order_by(Account.id).first()
    if account is None:
        account = Account.query.filter_by(name=CASH_NAME).first()
    if account is None and create:
        account = Account(name=CASH_NAME, kind="cash", currency="EUR")
        db.session.add(account)
        db.session.flush()
    return account


def _mentions(tx: Transaction, words: tuple[str, ...]) -> bool:
    text = f" {normalize(' '.join(t for t in (tx.description, tx.bank_description, tx.counterparty) if t))} "
    return any(re.search(rf"\b{word}\b", text) for word in words)


def withdrawal_or_deposit(tx: Transaction) -> str | None:
    """"withdrawal", "deposit" or None: what the description says, for a bank movement that is an expense
    (withdrawal) or an income (deposit)."""
    if tx.type == "expense" and _mentions(tx, WITHDRAWAL):
        return "withdrawal"
    if tx.type == "income" and _mentions(tx, DEPOSIT):
        return "deposit"
    return None


def to_transfer(tx: Transaction, cash: Account) -> bool:
    """Turn a bank withdrawal/deposit into a transfer with the cash account. False when it is not one,
    or when the bank account and the cash account do not share the currency (left to the user)."""
    kind = withdrawal_or_deposit(tx)
    bank = db.session.get(Account, tx.account_id) if tx.account_id else None
    if kind is None or bank is None or bank.kind == "cash" or bank.id == cash.id:
        return False
    if (bank.currency or "EUR") != (tx.currency or "EUR") or (cash.currency or "EUR") != (tx.currency or "EUR"):
        return False
    tx.type = "transfer"
    if kind == "withdrawal":
        tx.account_id, tx.counter_account_id = bank.id, cash.id
    else:
        tx.account_id, tx.counter_account_id = cash.id, bank.id
    return True


def recognise_all() -> int:
    """Every bank withdrawal and deposit not yet a transfer becomes a transfer with the cash account."""
    candidates = [tx for tx in Transaction.query.filter(Transaction.type.in_(["income", "expense"]),
                                                        Transaction.account_id.isnot(None)).all()
                  if withdrawal_or_deposit(tx)]
    if not candidates:
        return 0
    cash = cash_account()
    changed = sum(1 for tx in candidates if to_transfer(tx, cash))
    db.session.commit()
    return changed
