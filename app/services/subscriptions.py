"""
Subscriptions (F9): the recurring series in one list — the ones flagged "Transazione ricorrente" and the ones that
only look recurring (detected by the forecast) — with what each costs a month and a year, the next charge, the last
payment and any price change. "Non più attivo" ends a series on its last payment, so the forecast stops projecting it.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from app.models.transaction import Transaction
from app.services import forecast

UPCOMING_DAYS = 30
CHANGE_MIN = 0.01


@dataclass
class Subscription:
    template: Transaction        # latest transaction of the series
    frequency: str
    amount: float                # latest amount
    previous: float | None       # the payment before it, to spot a price change
    count: int                   # payments so far
    next_date: date | None       # next charge (None: ended)
    confirmed: bool              # flagged recurring (False: only detected)
    ended: bool = False

    @property
    def monthly(self) -> float:
        return self.amount * forecast.FREQUENCIES[self.frequency][3]

    @property
    def yearly(self) -> float:
        return self.monthly * 12

    @property
    def change(self) -> float | None:
        if self.previous is None or abs(self.amount - self.previous) < CHANGE_MIN:
            return None
        return round(self.amount - self.previous, 2)

    @property
    def frequency_label(self) -> str:
        return str(forecast.FREQUENCIES[self.frequency][0])


def _series(transactions) -> dict:
    groups = defaultdict(list)
    for tx in transactions:
        groups[forecast.series_key(tx)].append(tx)
    for txs in groups.values():
        txs.sort(key=lambda t: (t.date, t.id or 0))
    return groups


def _previous(txs: list, latest: Transaction) -> float | None:
    earlier = [t for t in txs if t.date < latest.date]
    return earlier[-1].magnitude if earlier else None


def _next_charge(template, today: date) -> date | None:
    if template.recurrence_end and template.recurrence_end < today:
        return None
    dates = forecast.occurrences(template, today, today + timedelta(days=400))
    return dates[0] if dates else None


def overview(kind: str = "expense", today: date | None = None) -> dict:
    """The series of one kind ("expense": subscriptions and bills, "income": salary, rents…), active ones first."""
    today = today or date.today()
    transactions = Transaction.query.filter(Transaction.type.in_(("income", "expense"))).all()
    groups = _series(transactions)

    active, ended = [], []
    for template in forecast.scheduled_templates(transactions):
        if template.type != kind:
            continue
        txs = groups[forecast.series_key(template)]
        frequency = template.recurrence if template.recurrence in forecast.FREQUENCIES else "monthly"
        next_date = _next_charge(template, today)
        item = Subscription(template, frequency, template.magnitude, _previous(txs, template), len(txs), next_date,
                            confirmed=True, ended=next_date is None)
        (ended if item.ended else active).append(item)
    for candidate in forecast.detect_candidates(transactions, today):
        template = candidate.template
        if template.type != kind:
            continue
        txs = groups[forecast.series_key(template)]
        active.append(Subscription(template, candidate.frequency, template.magnitude, _previous(txs, template),
                                   candidate.count, candidate.next_date, confirmed=False))

    active.sort(key=lambda s: (-s.monthly, s.template.description.lower()))
    ended.sort(key=lambda s: s.template.date, reverse=True)
    horizon = today + timedelta(days=UPCOMING_DAYS)
    upcoming = sum(s.amount * len(forecast.occurrences(s.template, today, horizon)) if s.confirmed
                   else (s.amount if s.next_date and today <= s.next_date < horizon else 0.0)
                   for s in active)
    monthly = sum(s.monthly for s in active)
    return {"kind": kind, "series": active, "ended": ended, "monthly": monthly, "yearly": monthly * 12,
            "count": len(active), "to_confirm": sum(not s.confirmed for s in active), "upcoming": upcoming,
            "upcoming_days": UPCOMING_DAYS, "increases": sum(1 for s in active if (s.change or 0) > 0)}


def stop(template: Transaction) -> None:
    """The series ends with its latest payment: no more charges in the forecast or here (it moves to «Terminati»)."""
    template.recurrence_end = template.date


def resume(template: Transaction) -> None:
    template.recurrence_end = None
