"""
Spending events (F20): what a trip, a wedding or a renovation cost, across categories, against its own budget.

An event's cost is its expenses minus its refunds (income in the event, e.g. a deposit returned); transfers do not
count. Movements are assigned by hand, in bulk from the transactions list, or from the event's suggestions: the
expenses in its dates not yet in an event.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from flask_babel import gettext as _
from sqlalchemy import func

from app.extensions import db
from app.models.event import SpendingEvent
from app.models.transaction import Transaction
from app.services import categories

SUGGESTIONS = 200


class EventError(ValueError):
    """The event cannot be saved as it is; the message is shown to the user."""


@dataclass
class Summary:
    event: SpendingEvent
    spent: Decimal
    refunds: Decimal
    count: int
    by_category: list[tuple[str, Decimal]]

    @property
    def net(self) -> Decimal:
        return self.spent - self.refunds

    @property
    def days(self) -> int:
        return ((self.event.end or self.event.start) - self.event.start).days + 1

    @property
    def per_day(self) -> Decimal:
        return (self.net / self.days).quantize(Decimal("0.01"))

    @property
    def left(self) -> Decimal | None:
        return None if self.event.budget is None else Decimal(self.event.budget) - self.net

    @property
    def used_pct(self) -> float | None:
        return float(self.net / Decimal(self.event.budget) * 100) if self.event.budget else None


def validate(name: str, start: date | None, end: date | None, budget: Decimal | None) -> None:
    if not name.strip():
        raise EventError(_("Dai un nome all'evento."))
    if start is None:
        raise EventError(_("Indica la data di inizio."))
    if end is not None and end < start:
        raise EventError(_("La fine viene prima dell'inizio."))
    if budget is not None and budget < 0:
        raise EventError(_("Il budget non può essere negativo."))


def movements(event: SpendingEvent) -> list[Transaction]:
    return Transaction.query.filter_by(event_id=event.id).order_by(Transaction.date, Transaction.id).all()


def _value(tx: Transaction) -> Decimal:
    return abs(Decimal(tx.amount_base if tx.amount_base is not None else tx.amount))


def summary(event: SpendingEvent, rows: list[Transaction] | None = None) -> Summary:
    rows = movements(event) if rows is None else rows
    spent, refunds, by_category = Decimal(0), Decimal(0), defaultdict(Decimal)
    for tx in rows:
        if tx.type == "expense":
            spent += _value(tx)
            by_category[categories.main_or(tx.category, categories.FALLBACK)] += _value(tx)
        elif tx.type == "income":
            refunds += _value(tx)
    return Summary(event, spent, refunds, len(rows), sorted(by_category.items(), key=lambda kv: -kv[1]))


def all_summaries() -> list[Summary]:
    events = SpendingEvent.query.order_by(SpendingEvent.start.desc(), SpendingEvent.id.desc()).all()
    rows = defaultdict(list)
    for tx in Transaction.query.filter(Transaction.event_id.isnot(None)).all():
        rows[tx.event_id].append(tx)
    return [summary(event, rows[event.id]) for event in events]


def suggestions(event: SpendingEvent) -> list[Transaction]:
    """Expenses and refunds in the event's dates that are in no event yet."""
    return (Transaction.query
            .filter(Transaction.event_id.is_(None), Transaction.type.in_(("expense", "income")),
                    Transaction.date >= event.start, Transaction.date <= (event.end or event.start))
            .order_by(Transaction.date, Transaction.id).limit(SUGGESTIONS).all())


def assign(ids: list[int], event: SpendingEvent | None) -> int:
    """Put the movements in the event (None: take them out of any event)."""
    if not ids:
        return 0
    return Transaction.query.filter(Transaction.id.in_(ids)).update(
        {"event_id": event.id if event else None}, synchronize_session=False)


def _expenses(start: date, end: date, in_events: bool) -> Decimal:
    event = Transaction.event_id.isnot(None) if in_events else Transaction.event_id.is_(None)
    total = db.session.query(func.sum(func.abs(func.coalesce(Transaction.amount_base, Transaction.amount)))).filter(
        Transaction.type == "expense", event, Transaction.date >= start, Transaction.date <= end).scalar()
    return Decimal(total or 0)


def spent_outside_events(start: date, end: date) -> Decimal:
    """Expenses in the period that belong to no event: the ordinary spending."""
    return _expenses(start, end, False)


def spent_in_events(start: date, end: date) -> Decimal:
    """Expenses in the period that belong to an event: the extraordinary spending."""
    return _expenses(start, end, True)
