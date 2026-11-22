"""
The figures of the dashboard's new blocks (UI-18, 18 Nov 2026), one function per block:
- «Questo mese»: the spending pace (all the month's expenses, day by day, against the month before and the
  budgets), the month's bridge (income, then the spending of each group, then what is left), the next 30 days of the
  liquid money (today's cash plus the deadlines of the Scadenzario) and the budgets closest to their limit;
- «Come sto»: what needs fixing (deadlines of the week, AI suggestions to confirm, transactions without a category,
  accounts to reconcile), each with the page where it is fixed;
- «Futuro»: the balance of the next 12 months (the forecast, with the range of its methods) and the big expenses
  of the next 12 months, month by month.
"""
from __future__ import annotations

from datetime import date, timedelta

from flask import url_for
from flask_babel import gettext as _
from sqlalchemy import func

from app.extensions import db
from app.models.transaction import Transaction
from app.services import analytics_clusters, budgets, clusters, data_health, deadlines, forecast, wealth
from app.services.ai_classification import AI_TAG
from app.services.periods import add_months, first_of_month, month_bounds, month_index, month_label
from app.services.totals import analysed, value_total

SIZE = func.abs(func.coalesce(Transaction.amount_base, Transaction.amount))
NEXT_DAYS = 30
TOP_BUDGETS = 5
BIG_EXPENSE = 300  # a deadline of at least this much is a «big expense» of the year
WEEK = 7


def _by_day(kind: str, start: date, end: date) -> dict[int, float]:
    rows = (db.session.query(Transaction.date, func.sum(SIZE))
            .filter(Transaction.type == kind, Transaction.date >= start, Transaction.date < end, analysed())
            .group_by(Transaction.date).all())
    return {day.day: float(total or 0) for day, total in rows}


def _running(by_day: dict[int, float], days: int) -> list[float]:
    out, total = [], 0.0
    for day in range(1, days + 1):
        total += by_day.get(day, 0.0)
        out.append(round(total, 2))
    return out


def spending_pace(today: date) -> dict:
    """Every expense of the month up to each day (nothing past today), the same days of the month before, and the
    straight line to the month's budgets when there are any."""
    month = first_of_month(today)
    start, end = month_bounds(month.year, month.month)
    days, elapsed = (end - start).days, (today - start).days + 1
    actual = _running(_by_day("expense", start, end), days)
    before = add_months(month, -1)
    previous = _running(_by_day("expense", before, start), (start - before).days)
    previous += [previous[-1] if previous else 0.0] * (days - len(previous))
    planned = round(sum(line["available"] for line in budgets.status(month, today)), 2)
    spent = actual[elapsed - 1]
    return {
        "labels": [str(day) for day in range(1, days + 1)],
        "actual": actual[:elapsed] + [None] * (days - elapsed),
        "previous": previous[:days],
        "ideal": [round(planned * day / days, 2) for day in range(1, days + 1)] if planned else None,
        "spent": spent, "planned": planned or None,
        "previous_same_day": previous[elapsed - 1],
        "projected": round(spent / elapsed * days, 2) if elapsed < days else None,
        "month": month_label(month_index(month)),
    }


def month_bridge(today: date, month: date | None = None) -> dict:
    """The month as a bridge: what came in, what each spending group took, what is left. `month` (its first day):
    the month to show, the one of the shared period on the dashboard; the current one when not given.
    Only real income and spending: the giroconti between own accounts and the cash taken out at the ATM move money
    that stays the user's, and the categories left out of the analyses (a reconciliation) are neither — so what
    they move is part of what is left."""
    month = month or today.replace(day=1)
    start, end = month_bounds(month.year, month.month)
    in_month = (Transaction.date >= start, Transaction.date < end)
    income = value_total(Transaction.type == "income", *in_month)
    # each group with the one the rules give a transaction that has none (as on the Uscite page)
    grouped = analytics_clusters.cluster_breakdown(start, end)
    order = list(clusters.CLUSTERS)
    groups = [(g["label"], g["amount"], g["cluster"]) for g in sorted(grouped, key=lambda g: order.index(g["cluster"]))]
    expenses = value_total(Transaction.type == "expense", *in_month)
    unset = round(expenses - sum(amount for _name, amount, _key in groups), 2)
    if unset > 0:
        groups.append((_("Senza gruppo"), unset, None))
    spent = sum(amount for _name, amount, _key in groups)
    # a month that spent more than came in took the rest from the savings: that is money in too, shown grey on top of
    # the income, so the bridge always goes down — never a red column rising from under zero (21 Nov)
    drawn = round(max(0.0, spent - income), 2)
    steps = [{"label": _("Entrate"), "low": 0.0, "high": round(income, 2), "kind": "income"}]
    if drawn:
        steps.append({"label": _("Presi dai risparmi"), "low": round(income, 2), "high": round(income + drawn, 2),
                      "kind": "drawn"})
    level = income + drawn
    for name, amount, key in groups:
        if amount:  # the money put aside or invested is blue (UI-08), the spending red
            steps.append({"label": name, "low": round(max(0.0, level - amount), 2), "high": round(level, 2),
                          "kind": "saving" if key == clusters.SAVING else "expense"})
            level -= amount
    left = round(income - spent, 2)
    if left > 0:  # what was not spent: the month's savings (giroconti and cash taken out are in here)
        steps.append({"label": _("Risparmi"), "low": 0.0, "high": left, "kind": "left"})
    return {"steps": steps, "left": left, "income": round(income, 2),
            "month": month_label(month_index(start)), "current": start <= today < end}


def next_days(today: date, days: int = NEXT_DAYS) -> dict:
    """Today's liquid money, then each deadline of the Scadenzario taken from it or added to it, day by day."""
    cash = float(wealth.balance_sheet(today)["cash"])
    due = deadlines.between(today + timedelta(days=1), today + timedelta(days=days))
    change: dict[date, float] = {}
    marks = []
    for d in due:
        if d.amount is None:
            continue
        value = float(d.amount) * (-1 if d.outgoing else 1)
        change[d.day] = change.get(d.day, 0.0) + value
        if abs(value) >= BIG_EXPENSE:
            marks.append({"day": d.day.isoformat(), "title": d.title, "amount": round(value, 2)})
    labels, balance, level = [], [], cash
    for offset in range(days + 1):
        day = today + timedelta(days=offset)
        level += change.get(day, 0.0) if offset else 0.0
        labels.append(day.strftime("%d/%m"))
        balance.append(round(level, 2))
    return {"labels": labels, "balance": balance, "start": round(cash, 2), "end": balance[-1],
            "lowest": min(balance), "marks": marks[:6], "count": len(due)}


def budgets_near_limit(today: date) -> list[dict]:
    lines = budgets.status(first_of_month(today), today)
    keys = ("category", "spent", "available", "share", "state", "pace")
    return [{key: line[key] for key in keys} for line in sorted(lines, key=lambda line: -line["share"])[:TOP_BUDGETS]]


def to_fix(today: date) -> list[dict]:
    """What needs a look, each with how many and where it is fixed (the ones at zero left out)."""
    week = deadlines.upcoming(today, WEEK)
    items = [
        {"key": "deadlines", "icon": "calendar-event", "count": len(week), "label": _("Scadenze nei prossimi 7 giorni"),
         "url": url_for("deadlines.index")},
        {"key": "ai", "icon": "stars", "count": Transaction.query.filter(Transaction.tags.any(AI_TAG)).count(),
         "label": _("Categorie proposte dall'AI da confermare"), "url": url_for("transactions.index", tag=AI_TAG)},
    ]
    for check in data_health.run(today, (data_health._uncategorized, data_health._unreconciled)):
        items.append({"key": check.key, "icon": "tag" if check.key == "uncategorized" else "bank",
                      "count": check.count, "label": check.title, "url": check.url or url_for("health.index")})
    return [item for item in items if item["count"]]


def future_balance(today: date) -> dict | None:
    """The liquid money at the end of each of the next 12 months, as the forecast sees it, with the range of its
    methods around it. None without enough history."""
    prefs = forecast.preferences()
    fc = forecast.load(prefs["method"], prefs["window"], 12, prefs["recurring"], today=today)
    if fc.history_months < 3 or not fc.months:
        return None
    low, high, gap_low, gap_high = [], [], 0.0, 0.0
    for row in fc.months:
        gap_low += row["net"] - row.get("low", row["net"])
        gap_high += row.get("high", row["net"]) - row["net"]
        low.append(round(row["balance"] - gap_low, 2))
        high.append(round(row["balance"] + gap_high, 2))
    return {"labels": [row["label"] for row in fc.months], "balance": [row["balance"] for row in fc.months],
            "low": low, "high": high, "end": fc.months[-1]["balance"]}


def big_expenses(today: date) -> dict:
    """The deadlines of the next 12 months of at least BIG_EXPENSE, added up month by month."""
    first = first_of_month(today)
    months = [add_months(first, n) for n in range(12)]
    totals = {m: 0.0 for m in months}
    biggest: list[tuple[float, str, date]] = []
    for d in deadlines.between(today, add_months(first, 12) - timedelta(days=1)):
        if d.amount is None or not d.outgoing or float(d.amount) < BIG_EXPENSE:
            continue
        totals[first_of_month(d.day)] = totals.get(first_of_month(d.day), 0.0) + float(d.amount)
        biggest.append((float(d.amount), d.title, d.day))
    biggest.sort(reverse=True)
    return {"labels": [month_label(month_index(m)) for m in months], "amounts": [round(totals[m], 2) for m in months],
            "total": round(sum(totals.values()), 2),
            "top": [{"amount": a, "title": t, "day": d} for a, t, d in biggest[:3]]}


SPARK_MONTHS = 6


def net_worth_spark(today: date) -> dict:
    """The net worth at the end of each of the last months and today (the little line of the card), and how much it
    changed since the end of last month."""
    first = first_of_month(today)
    ends = [add_months(first, -n) - timedelta(days=1) for n in range(SPARK_MONTHS - 1, -1, -1)] + [today]
    values = [round(float(wealth.balance_sheet(day)["net_worth"]), 2) for day in ends]
    return {"values": values, "change": round(values[-1] - values[-2], 2)}


def month_saving(today: date, last_12: dict) -> dict:
    """The share of this month's income that is left, and the same over the last 12 months."""
    start, end = month_bounds(today.year, today.month)
    # without the categories left out of the analyses (Riconciliazione…) and the reversals: they are not savings
    income = float(db.session.query(func.sum(SIZE)).filter(
        Transaction.type == "income", Transaction.date >= start, Transaction.date < end, analysed()).scalar() or 0)
    expenses = float(db.session.query(func.sum(SIZE)).filter(
        Transaction.type == "expense", Transaction.date >= start, Transaction.date < end, analysed()).scalar() or 0)
    year_in, year_out = sum(last_12.get("income", [])), sum(last_12.get("expenses", []))
    return {"rate": round((income - expenses) / income * 100, 1) if income else None,
            "average": round((year_in - year_out) / year_in * 100, 1) if year_in else None,
            "saved": round(income - expenses, 2)}
