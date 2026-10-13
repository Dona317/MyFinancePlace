"""
The rhythm of spending (F20, closes F10c): when the money goes out and what changed.

- calendar: the expenses of each day of a year, as the cells of a GitHub-style heatmap (weeks × weekdays)
- weekdays: the average spending of each weekday
- changes: the categories that moved most last month, against the month before and against the average of the
  twelve before it
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func

from app.models.transaction import Transaction
from app.services import categories, periods
from app.services.totals import LINE_CATEGORY, LINE_VALUE, lines_query

MIN_CHANGE = Decimal(10)  # euro: smaller moves are noise
SHOWN = 5


def daily(start: date, end: date) -> dict[date, Decimal]:
    rows = lines_query(Transaction.date, func.sum(LINE_VALUE)).filter(
        Transaction.type == "expense", Transaction.date >= start, Transaction.date <= end).group_by(Transaction.date)
    return {day: Decimal(str(total or 0)) for day, total in rows}


@dataclass
class Cell:
    day: date | None   # None: a cell before 1 January or after 31 December
    amount: Decimal
    level: int         # 0 (nothing) … 4 (the busiest days)


def calendar(year: int, today: date | None = None) -> dict:
    """Weeks (Monday first) of the year, each with its seven days and their level of spending."""
    today = today or date.today()
    start, end = date(year, 1, 1), min(date(year, 12, 31), today)
    amounts = daily(start, end)
    spent = sorted(v for v in amounts.values() if v > 0)
    bounds = [spent[int(len(spent) * q) - 1] for q in (0.25, 0.5, 0.75)] if spent else []

    def level(value: Decimal) -> int:
        if value <= 0:
            return 0
        return 1 + sum(1 for b in bounds if value > b)

    weeks, day = [], start - timedelta(days=start.weekday())
    while day <= date(year, 12, 31):
        week = []
        for _ in range(7):
            inside = start <= day <= end
            value = amounts.get(day, Decimal(0)) if inside else Decimal(0)
            week.append(Cell(day if inside else None, value, level(value)))
            day += timedelta(days=1)
        weeks.append(week)
    total = sum(amounts.values(), Decimal(0))
    days = (end - start).days + 1 if end >= start else 0
    return {"weeks": weeks, "total": total, "days_with": len(spent), "days": days,
            "busiest": sorted(amounts.items(), key=lambda kv: -kv[1])[:SHOWN]}


def weekdays(start: date, end: date) -> list[Decimal]:
    """Average spending of each weekday (Monday first) over the period."""
    totals, counts = [Decimal(0)] * 7, [0] * 7
    day = start
    while day <= end:
        counts[day.weekday()] += 1
        day += timedelta(days=1)
    for day, value in daily(start, end).items():
        totals[day.weekday()] += value
    return [(t / c).quantize(Decimal("0.01")) if c else Decimal(0) for t, c in zip(totals, counts)]


def _by_category(start: date, end: date) -> dict[str, Decimal]:
    rows = lines_query(LINE_CATEGORY, func.sum(LINE_VALUE)).filter(
        Transaction.type == "expense", Transaction.date >= start, Transaction.date <= end).group_by(LINE_CATEGORY)
    totals = defaultdict(Decimal)
    for name, total in rows:
        totals[categories.main_or(name, categories.FALLBACK)] += Decimal(str(total or 0))
    return totals


@dataclass
class Change:
    category: str
    now: Decimal
    before: Decimal
    average: Decimal

    @property
    def diff(self) -> Decimal:
        return self.now - self.before

    @property
    def vs_average(self) -> Decimal:
        return self.now - self.average


def changes(today: date | None = None) -> dict:
    """Last complete month against the month before and the average of the twelve before it."""
    today = today or date.today()
    last_start = periods.add_months(periods.first_of_month(today), -1)
    last_end = periods.first_of_month(today) - timedelta(days=1)
    prev_start = periods.add_months(last_start, -1)
    year_start = periods.add_months(last_start, -12)
    now, before = _by_category(last_start, last_end), _by_category(prev_start, last_start - timedelta(days=1))
    year = _by_category(year_start, last_start - timedelta(days=1))
    rows = [Change(name, now.get(name, Decimal(0)), before.get(name, Decimal(0)),
                   (year.get(name, Decimal(0)) / 12).quantize(Decimal("0.01")))
            for name in set(now) | set(before)]
    rows = [r for r in rows if abs(r.diff) >= MIN_CHANGE]
    return {"month": last_start, "up": sorted((r for r in rows if r.diff > 0), key=lambda r: -r.diff)[:SHOWN],
            "down": sorted((r for r in rows if r.diff < 0), key=lambda r: r.diff)[:SHOWN],
            "total_now": sum(now.values(), Decimal(0)), "total_before": sum(before.values(), Decimal(0))}
