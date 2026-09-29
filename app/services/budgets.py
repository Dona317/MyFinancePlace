"""
Monthly budgets per category: planned vs spent (in euro), with a warning at 80% and when exceeded.
A budget for one month replaces the every-month budget of that category for that month only.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models.budget import Budget
from app.models.transaction import Transaction
from app.services.periods import month_bounds

WARNING_SHARE = 80  # percent of the budget spent that raises a warning


def month_start(day: date) -> date:
    return date(day.year, day.month, 1)


def budgets_for(month: date) -> dict[str, Budget]:
    """The budget that applies to each category in `month` (the month's own, else the every-month one)."""
    month = month_start(month)
    chosen: dict[str, Budget] = {}
    for budget in Budget.query.filter((Budget.month.is_(None)) | (Budget.month == month)).all():
        if budget.category not in chosen or budget.month is not None:
            chosen[budget.category] = budget
    return chosen


def spent_by_category(month: date) -> dict[str, float]:
    start, end = month_bounds(month.year, month.month)
    rows = (db.session.query(Transaction.category, func.sum(func.abs(Transaction.amount_base)))
            .filter(Transaction.type == "expense", Transaction.date >= start, Transaction.date < end)
            .group_by(Transaction.category).all())
    return {category or "Senza categoria": float(total or 0) for category, total in rows}


def status(month: date, today: date | None = None) -> list[dict]:
    """One line per budgeted category: planned, spent, share, left, and where the month should be by now."""
    today = today or date.today()
    month = month_start(month)
    spent = spent_by_category(month)
    start, end = month_bounds(month.year, month.month)
    days = (end - start).days
    elapsed = days if today >= end else max((today - start).days + 1, 0) if today >= start else 0
    lines = []
    for category, budget in sorted(budgets_for(month).items(), key=lambda item: item[0].casefold()):
        planned = float(budget.amount)
        used = spent.get(category, 0.0)
        share = round(used / planned * 100, 1) if planned else 0.0
        lines.append({
            "category": category, "budget": budget, "planned": planned, "spent": round(used, 2),
            "left": round(planned - used, 2), "share": share,
            "state": "over" if used > planned else "warning" if share >= WARNING_SHARE else "ok",
            "pace": round(elapsed / days * 100, 1) if days else 0.0,  # share of the month gone by
            "only_this_month": budget.month is not None,
        })
    return lines


def alerts(today: date | None = None) -> list[dict]:
    """Budgets of the current month at or past the warning share (for the dashboard and notifications)."""
    today = today or date.today()
    return [line for line in status(today, today) if line["state"] != "ok"]


def save(category: str, amount: Decimal | None, month: date | None) -> None:
    """Set (or with no amount remove) the budget of a category, every month or for one month."""
    month = month_start(month) if month else None
    budget = Budget.query.filter(Budget.category == category,
                                 Budget.month.is_(None) if month is None else Budget.month == month).first()
    if not amount:
        if budget is not None:
            db.session.delete(budget)
        return
    if budget is None:
        db.session.add(Budget(category=category, month=month, amount=amount))
    else:
        budget.amount = amount
