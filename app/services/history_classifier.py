"""
Category suggestions learned from the user's own history, without any model to download.

Every categorized transaction teaches which category its merchant words lead to ("esselunga" → Alimentari).
A new causale is scored by its words, rarer words counting more (a merchant name says more than "milano");
a suggestion is given only when the history clearly agrees. It runs before the AI, which then gets only
the causali the history cannot place.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from flask import has_app_context
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.transaction import Transaction
from app.services import request_cache
from app.services.duplicates import meaningful_words

MIN_EXAMPLES = 2       # a word seen once is an anecdote, not a habit
MIN_SHARE = 0.75       # the winning category must hold three quarters of the evidence
SURE_SHARE = 0.95
TOO_COMMON = 0.25      # words in more than a quarter of the history ("pagamento", a city) carry no signal…
COMMON_FROM = 20       # …once there is enough history to tell
IGNORED = ("", "Altro")


@dataclass
class Guess:
    category: str
    counterparty: str
    confidence: str      # "alta" | "media"


class _Index:
    def __init__(self, rows):
        self.size: Counter = Counter()                                    # transactions per kind
        self.seen: dict[tuple, Counter] = defaultdict(Counter)            # (kind, word) → categories
        self.names: dict[tuple, Counter] = defaultdict(Counter)           # (kind, word, category) → counterparties
        for description, counterparty, causale, category, kind in rows:
            self.size[kind] += 1
            for word in meaningful_words(" ".join(filter(None, (description, counterparty, causale)))):
                self.seen[kind, word][category] += 1
                if counterparty:
                    self.names[kind, word, category][counterparty] += 1

    def guess(self, text: str, kind: str) -> Guess | None:
        total = self.size[kind]
        scores: Counter = Counter()
        support: Counter = Counter()
        for word in meaningful_words(text):
            votes = self.seen.get((kind, word))
            if not votes:
                continue
            count = sum(votes.values())
            if count < MIN_EXAMPLES or (total >= COMMON_FROM and count > TOO_COMMON * total):
                continue
            weight = math.log(1 + total / count)  # rarer words weigh more; never zero
            for category, n in votes.items():
                scores[category] += weight * n / count
                support[category] += n
        if not scores:
            return None
        category, best = scores.most_common(1)[0]
        share = best / sum(scores.values())
        if share < MIN_SHARE:
            return None
        names = Counter()
        for word in meaningful_words(text):
            names.update(self.names.get((kind, word, category), {}))
        counterparty = names.most_common(1)[0][0] if names else ""
        return Guess(category, counterparty, "alta" if share >= SURE_SHARE and support[category] >= 3 else "media")


def index() -> _Index | None:
    """The history, read once per request (build it once and pass it around when classifying many rows)."""
    if not has_app_context():
        return None
    store = request_cache.cache()
    if "history_index" not in store:
        rows = (db.session.query(Transaction.description, Transaction.counterparty, Transaction.bank_description,
                                 Transaction.category, Transaction.type)
                .filter(Transaction.type.in_(("income", "expense")), Transaction.category.isnot(None),
                        Transaction.category.notin_(IGNORED))
                .all())
        store["history_index"] = _Index(rows)
    return store["history_index"]


def guess(text: str | None, income: bool, history: _Index | None = None) -> Guess | None:
    """What the user's history says about this causale; None when it does not clearly agree (or outside the app)."""
    if not text:
        return None
    try:
        history = history or index()
    except SQLAlchemyError:
        db.session.rollback()
        return None
    return history.guess(text, "income" if income else "expense") if history else None
