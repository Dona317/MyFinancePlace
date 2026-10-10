"""
A giroconto between two of the user's accounts is in both statements: out of one on a day, into the other on the
same day (or the next, by value date) for the same amount. The first statement imported saves it as half a transfer
(only the side it knows); the second must complete that transaction instead of adding another one.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.models.transaction import Transaction

DAYS = 1  # the other bank may book it one day later


def _candidates(day: date, amount: Decimal):
    return (Transaction.query
            .filter(Transaction.type == "transfer", Transaction.amount == abs(amount),
                    Transaction.date.between(day - timedelta(days=DAYS), day + timedelta(days=DAYS)))
            .order_by(Transaction.id))


def _closest(found: list[Transaction], day: date) -> Transaction | None:
    return min(found, key=lambda tx: abs((tx.date - day).days), default=None)


def other_half(day: date, amount: Decimal, outgoing: bool, account_id: int | None = None,
               exclude: set[int] = frozenset()) -> Transaction | None:
    """The saved half of this giroconto: for money going out, a transfer that only knows where it arrived (and
    vice versa), on another account than `account_id`."""
    found = []
    for tx in _candidates(day, amount):
        known, missing = (tx.counter_account_id, tx.account_id) if outgoing else (tx.account_id, tx.counter_account_id)
        if tx.id not in exclude and missing is None and known is not None and known != account_id:
            found.append(tx)
    return _closest(found, day)


def already_complete(day: date, amount: Decimal, outgoing: bool, account_id: int) -> bool:
    """The giroconto is already saved with both accounts, `account_id` on this row's side (a statement imported
    again after the two halves were joined)."""
    for tx in _candidates(day, amount):
        mine, other = (tx.account_id, tx.counter_account_id) if outgoing else (tx.counter_account_id, tx.account_id)
        if mine == account_id and other is not None:
            return True
    return False


def complete(tx: Transaction, outgoing: bool, account_id: int) -> None:
    """Fill the side of the transfer this statement row knows."""
    if outgoing:
        tx.account_id = account_id
    else:
        tx.counter_account_id = account_id


def flag_pairs(rows) -> None:
    """Mark the preview's giroconti whose other half is already saved: they will be joined to it, not added."""
    taken: set[int] = set()
    for row in rows:
        if row.type != "transfer" or row.duplicate:
            continue
        tx = other_half(row.date, row.amount, row.amount < 0, exclude=taken)
        if tx is not None:
            taken.add(tx.id)
            row.pairs_with = f"{tx.date:%d/%m/%Y} · {tx.description[:60]}"
