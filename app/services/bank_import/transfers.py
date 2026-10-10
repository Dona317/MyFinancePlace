"""
Money moved between two of the user's accounts is in both statements: out of one, into the other up to 15 days
later (a bank transfer is not always instant), for the same amount. It is a giroconto even when the banks call it
a plain bonifico ("Bonifico a MARIO ROSSI").

The first statement imported saves its side: half a transfer (only the account it knows), or an expense / income
when the bank wrote just "bonifico". Importing the second statement on the other account joins the row to that
transaction, which becomes one transfer with both accounts, instead of adding a second movement.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

from app.models.transaction import Transaction

from .categorize import search_text

DAYS = 15  # the longest a transfer between banks takes to arrive: usually 0-3 working days, sometimes two weeks
_BANK_TRANSFER = re.compile(r" (bonifico|bonif|sepa|giroconto|girofondi|trasferimento|ricarica|sct) ")


def is_bank_transfer(*texts: str | None) -> bool:
    """A bonifico or a giroconto (as opposed to a card payment, a direct debit, a salary…)."""
    return bool(_BANK_TRANSFER.search(search_text(*texts)))


def _candidates(day: date, amount: Decimal, types: tuple[str, ...]):
    return (Transaction.query
            .filter(Transaction.type.in_(types), Transaction.amount == abs(amount),
                    Transaction.date.between(day - timedelta(days=DAYS), day + timedelta(days=DAYS)))
            .order_by(Transaction.id))


def _matches(tx: Transaction, day: date, outgoing: bool, account_id: int | None) -> bool:
    """`tx` is the other side of a row moving money out of (outgoing) or into `account_id` on `day`."""
    if outgoing and tx.date < day or not outgoing and tx.date > day:
        return False  # the money arrives after it left, never before
    if tx.type == "transfer":
        known, missing = (tx.counter_account_id, tx.account_id) if outgoing else (tx.account_id, tx.counter_account_id)
    else:  # a bonifico saved as income (it arrived there) or expense (it left from there)
        if tx.type != ("income" if outgoing else "expense") or not is_bank_transfer(tx.description, tx.bank_description):
            return False
        known, missing = tx.account_id, None
    return missing is None and known is not None and known != account_id


def other_side(day: date, amount: Decimal, outgoing: bool, account_id: int | None = None,
               exclude: set[int] = frozenset()) -> Transaction | None:
    """The saved side of this movement between own accounts, on another account than `account_id`: the closest
    in time when there are several."""
    found = [tx for tx in _candidates(day, amount, ("transfer", "income" if outgoing else "expense"))
             if tx.id not in exclude and _matches(tx, day, outgoing, account_id)]
    return min(found, key=lambda tx: abs((tx.date - day).days), default=None)


def join(tx: Transaction, outgoing: bool, account_id: int, import_ref: str | None) -> None:
    """Make `tx` one transfer between its account and `account_id`, remembering this statement row too."""
    if tx.type != "transfer":
        other = tx.account_id
        tx.type, tx.category = "transfer", "Giroconto"
        tx.account_id, tx.counter_account_id = (account_id, other) if outgoing else (other, account_id)
    elif outgoing:
        tx.account_id = account_id
    else:
        tx.counter_account_id = account_id
    tx.counter_import_ref = import_ref


def flag_pairs(rows) -> None:
    """Mark the preview's rows whose other side is already saved: importing them joins them to it."""
    taken: set[int] = set()
    for row in rows:
        if row.duplicate or (row.type != "transfer" and not is_bank_transfer(row.description, row.details)):
            continue
        tx = other_side(row.date, row.amount, row.amount < 0, exclude=taken)
        if tx is not None:
            taken.add(tx.id)
            row.pairs_with = f"{tx.date:%d/%m/%Y} · {tx.description[:60]}"
