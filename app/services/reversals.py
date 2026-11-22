"""
Reversals (storni, F108): a payment that went out and came back (or money that came in and went back out) — an
expense and an income of the **same amount**, on the same account. Both stay recorded and in the account's balance
(they cancel each other there), but once linked neither counts in the analyses: reports, budgets, dashboard, savings
rate (services.totals.analysed). Each keeps its own category.

Finding them, like the giroconti between two accounts:
  • `candidates()` — every unlinked pair of opposite movements with the same amount and currency, on the same account,
    within WINDOW_DAYS of each other, closest first; the user links them or says «non è uno storno» (remembered);
  • `auto_link()` — after an import (file or PSD2): the pairs whose causale says so («storno», «stornato»,
    «annullamento», «reversal»…) are linked straight away; the others are only proposed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta

from flask_babel import gettext as _
from sqlalchemy import and_, or_
from sqlalchemy.orm import aliased

from app.extensions import db
from app.models.transaction import Transaction
from app.services import settings_store
from app.services.parsing import normalize

WINDOW_DAYS = 90          # the furthest apart the two halves are looked for (refunds can take weeks)
DISMISSED_SETTING = "reversals.dismissed"
KEEP_DISMISSED = 1000
DIRECTIONS = ("income", "expense")
_SIGNAL = re.compile(r"\b(storno|stornato|stornata|storni|annullamento|annullato|annullata|revoca|revocato|"
                     r"reversal|reversed|chargeback|charge back|refund)\b")


@dataclass
class Pair:
    first: Transaction      # the earlier one
    second: Transaction
    signal: bool            # a causale says it is a reversal

    @property
    def key(self) -> str:
        low, high = sorted((self.first.id, self.second.id))
        return f"{low}-{high}"

    @property
    def days(self) -> int:
        return (self.second.date - self.first.date).days


def says_reversal(*texts: str | None) -> bool:
    """A causale that names a reversal («STORNO PAGAMENTO POS…»)."""
    return bool(_SIGNAL.search(f" {normalize(' '.join(t for t in texts if t))} "))


def _text(tx: Transaction) -> str:
    return " ".join(t for t in (tx.description, tx.bank_description, tx.notes) if t)


def check(first: Transaction, second: Transaction) -> None:
    """ValueError (Italian message) when the two cannot be a reversal of each other."""
    if first.id == second.id:
        raise ValueError(_("Scegli due movimenti diversi."))
    if {first.type, second.type} != set(DIRECTIONS):
        raise ValueError(_("Uno storno è un'uscita e un'entrata: i due movimenti devono avere direzioni opposte."))
    if abs(first.amount) != abs(second.amount) or (first.currency or "EUR") != (second.currency or "EUR"):
        raise ValueError(_("Uno storno ha lo stesso importo, nella stessa valuta, nei due movimenti."))
    if first.reversal_id or second.reversal_id:
        raise ValueError(_("Uno dei due movimenti è già collegato a un altro storno."))


def link(first: Transaction, second: Transaction) -> None:
    """Make the two one reversal (both kept, both out of the analyses). ValueError when they cannot be."""
    check(first, second)
    first.reversal_id, second.reversal_id = second.id, first.id
    db.session.flush()


def unlink(tx: Transaction) -> Transaction | None:
    """The reversal undone: both movements count again. Returns the other half (None when there was none)."""
    other = db.session.get(Transaction, tx.reversal_id) if tx.reversal_id else None
    tx.reversal_id = None
    if other is not None and other.reversal_id == tx.id:
        other.reversal_id = None
    db.session.flush()
    return other


def dismissed() -> set[str]:
    return set(settings_store.get_json(DISMISSED_SETTING, [], expect=list))


def dismiss(first_id: int, second_id: int) -> None:
    """«Non è uno storno»: the pair is not proposed again."""
    low, high = sorted((first_id, second_id))
    kept = [k for k in settings_store.get_json(DISMISSED_SETTING, [], expect=list) if k != f"{low}-{high}"]
    settings_store.set_json(DISMISSED_SETTING, (kept + [f"{low}-{high}"])[-KEEP_DISMISSED:])


def _pairs_query(ids: list[int] | None, window_days: int):
    """Unlinked expense/income pairs with the same amount, currency and account, within the window (SQL)."""
    out, back = aliased(Transaction), aliased(Transaction)
    query = (db.session.query(out, back)
             .filter(out.type == "expense", back.type == "income",
                     out.reversal_id.is_(None), back.reversal_id.is_(None),
                     out.amount == back.amount,
                     db.func.coalesce(out.currency, "EUR") == db.func.coalesce(back.currency, "EUR"),
                     or_(out.account_id == back.account_id, and_(out.account_id.is_(None), back.account_id.is_(None))),
                     out.date.between(back.date - timedelta(days=window_days), back.date + timedelta(days=window_days))))
    if ids is not None:
        query = query.filter(or_(out.id.in_(ids), back.id.in_(ids)))
    return query


def candidates(window_days: int = WINDOW_DAYS, ids: list[int] | None = None) -> list[Pair]:
    """The possible reversals, each movement in one pair at most: the pairs a causale names first, then the closest in
    time; the pairs dismissed are left out."""
    hidden = dismissed()
    found = []
    for out, back in _pairs_query(ids, window_days):
        first, second = sorted((out, back), key=lambda t: (t.date, t.id))
        pair = Pair(first, second, says_reversal(_text(out), _text(back)))
        if pair.key not in hidden:
            found.append(pair)
    found.sort(key=lambda p: (not p.signal, p.days, p.first.date, p.first.id))
    taken: set[int] = set()
    chosen = []
    for pair in found:
        if pair.first.id in taken or pair.second.id in taken:
            continue
        taken |= {pair.first.id, pair.second.id}
        chosen.append(pair)
    chosen.sort(key=lambda p: (p.second.date, p.second.id), reverse=True)
    return chosen


def auto_link(ids: list[int] | None = None) -> int:
    """Link the pairs a causale names as a reversal (after an import: `ids`, the movements just saved). Returns how
    many reversals were linked; the caller commits."""
    linked = 0
    for pair in candidates(ids=ids):
        if pair.signal:
            link(pair.first, pair.second)
            linked += 1
    return linked


def linked_pairs(limit: int = 200) -> list[tuple[Transaction, Transaction]]:
    """The reversals already linked, newest first (each pair once)."""
    other = aliased(Transaction)
    rows = (db.session.query(Transaction, other).join(other, Transaction.reversal_id == other.id)
            .filter(Transaction.id < other.id).order_by(db.func.greatest(Transaction.date, other.date).desc())
            .limit(limit).all())
    return [tuple(sorted(pair, key=lambda t: (t.date, t.id))) for pair in rows]


def partners_for(tx: Transaction, window_days: int = 365) -> list[Transaction]:
    """The movements `tx` could be linked to by hand: opposite direction, same amount and currency, not linked yet
    (any account, within a year), closest in time first."""
    if tx.type not in DIRECTIONS or tx.reversal_id:
        return []
    opposite = "income" if tx.type == "expense" else "expense"
    rows = (Transaction.query
            .filter(Transaction.type == opposite, Transaction.reversal_id.is_(None), Transaction.id != tx.id,
                    Transaction.amount == tx.amount,
                    db.func.coalesce(Transaction.currency, "EUR") == (tx.currency or "EUR"),
                    Transaction.date.between(tx.date - timedelta(days=window_days), tx.date + timedelta(days=window_days)))
            .all())
    return sorted(rows, key=lambda t: (t.account_id != tx.account_id, abs((t.date - tx.date).days)))[:20]
