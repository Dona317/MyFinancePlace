"""
Possible duplicate transactions: same type and amount, dates close together, similar descriptions.

Typical causes: the same statement imported twice in different formats (Excel and PDF), overlapping
statements from two exports, or a movement typed by hand and then imported.
Used by the duplicate finder page and to warn in the import preview.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from itertools import combinations

from app.extensions import db
from app.models.duplicate import DuplicateDismissal
from app.models.transaction import Transaction

DEFAULT_WINDOW_DAYS = 3
SENSITIVITY = {"alta": 0.4, "normale": 0.6, "bassa": 0.85}   # minimum description similarity

# Words banks add around the merchant name: ignored when comparing descriptions
NOISE_WORDS = {
    "pagamento", "pagam", "pag", "pos", "carta", "card", "visa", "debit", "mastercard", "maestro", "bancomat",
    "contactless", "bonifico", "sepa", "sct", "istantaneo", "addebito", "sdd", "diretto", "presso", "tramite",
    "operazione", "acquisto", "commissione", "da", "a", "di", "del", "della", "dei", "per", "il", "la", "lo",
    "le", "e", "in", "su", "con", "fav", "favore", "vostro", "ns", "rif", "cro", "trn", "eur", "euro",
}


def meaningful_words(text: str | None) -> set[str]:
    """Words of a description without the bank's boilerplate (\"Pagamento POS\", \"carta\", numbers)."""
    words = re.findall(r"[a-z]+|\d+", (text or "").lower())
    return {w for w in words if w not in NOISE_WORDS and not w.isdigit() and len(w) > 1}


def similarity(first: str | None, second: str | None) -> float:
    """0..1: shared meaningful words (merchant names), falling back to character similarity."""
    a, b = meaningful_words(first), meaningful_words(second)
    if a and b:
        shared = len(a & b)
        return max(shared / len(a | b), 0.9 * shared / min(len(a), len(b)))
    return SequenceMatcher(None, (first or "").lower(), (second or "").lower()).ratio()


def _signed_key(tx_type: str, amount) -> tuple[str, Decimal]:
    return tx_type, abs(Decimal(str(amount))).quantize(Decimal("0.01"))


# ── Duplicate finder ───────────────────────────────────────────────────────────

@dataclass
class DuplicateGroup:
    transactions: list[Transaction]
    identical: bool          # same date and same meaningful description

    @property
    def ids(self) -> list[int]:
        return [t.id for t in self.transactions]

    @property
    def latest(self) -> date:
        return max(t.date for t in self.transactions)


def _dismissed_pairs() -> set[tuple[int, int]]:
    return {(d.first_id, d.second_id) for d in DuplicateDismissal.query.all()}


def find_groups(window_days: int = DEFAULT_WINDOW_DAYS, threshold: float = SENSITIVITY["normale"]) -> list[DuplicateGroup]:
    buckets: dict[tuple, list[Transaction]] = {}
    for tx in Transaction.query.order_by(Transaction.date, Transaction.id).all():
        buckets.setdefault(_signed_key(tx.type, tx.amount), []).append(tx)
    dismissed = _dismissed_pairs()

    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    by_id: dict[int, Transaction] = {}
    for bucket in buckets.values():
        for i, first in enumerate(bucket):
            for second in bucket[i + 1:]:
                if (second.date - first.date).days > window_days:
                    break  # bucket is sorted by date
                pair = (min(first.id, second.id), max(first.id, second.id))
                if pair in dismissed or similarity(first.description, second.description) < threshold:
                    continue
                by_id[first.id], by_id[second.id] = first, second
                parent[find(first.id)] = find(second.id)

    members: dict[int, list[Transaction]] = {}
    for tx_id, tx in by_id.items():
        members.setdefault(find(tx_id), []).append(tx)
    groups = []
    for txs in members.values():
        txs.sort(key=lambda t: (t.date, t.id))
        identical = len({t.date for t in txs}) == 1 and len({frozenset(meaningful_words(t.description)) for t in txs}) == 1
        groups.append(DuplicateGroup(txs, identical))
    return sorted(groups, key=lambda g: (not g.identical, -g.latest.toordinal()))


def dismiss(ids: list[int]) -> int:
    """Remember that these transactions are not duplicates of each other."""
    existing = _dismissed_pairs()
    added = 0
    for first, second in combinations(sorted(set(ids)), 2):
        if (first, second) not in existing:
            db.session.add(DuplicateDismissal(first_id=first, second_id=second))
            added += 1
    db.session.commit()
    return added


# ── Import preview ─────────────────────────────────────────────────────────────

def flag_similar_rows(rows, window_days: int = DEFAULT_WINDOW_DAYS, threshold: float = SENSITIVITY["normale"]) -> None:
    """Set row.similar_to on statement rows that look like a transaction already saved."""
    if not rows:
        return
    amounts = {abs(r.amount) for r in rows}
    start = min(r.date for r in rows) - timedelta(days=window_days)
    end = max(r.date for r in rows) + timedelta(days=window_days)
    candidates: dict[tuple, list[Transaction]] = {}
    query = Transaction.query.filter(Transaction.amount.in_(amounts), Transaction.date.between(start, end))
    for tx in query.all():
        candidates.setdefault(_signed_key(tx.type, tx.amount), []).append(tx)

    for row in rows:
        for tx in candidates.get(_signed_key(row.type, row.amount), []):
            if abs((tx.date - row.date).days) <= window_days and similarity(row.description, tx.description) >= threshold:
                row.similar_to = f"{tx.date:%d/%m/%Y} · {tx.description[:60]}"
                break
