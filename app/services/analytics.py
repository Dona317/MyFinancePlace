"""
Financial analytics computed from transactions.

Amounts are stored as positive numbers; the direction comes from `type`
("income" | "expense" | "transfer").
"""
from datetime import date
from itertools import accumulate

from sqlalchemy import extract, func

from app.extensions import db
from app.models.transaction import Transaction
from app.services import categories, wealth
from app.services.categories import UNCATEGORIZED  # noqa: F401 - used by reports, forecast and their routes
from app.services.financial_health import autonomy, income_stability, nature_split  # noqa: F401 - older imports
from app.services.i18n import N_
from app.services.money import share
from app.services.periods import (month_bounds, month_index, month_label,
                                  month_labels, shift_month, year_bounds)
from app.services.totals import LINE_CATEGORY, LINE_VALUE, lines_query, value_total, with_lines

OTHER = N_("Altre")  # the categories past the top ones, added up in one series


# Keywords used to classify "transfer" transactions in the cash-flow statement
INVESTING_KEYWORDS  = ("invest", "portafoglio", "etf", "azion", "crypto", "obbligaz")
FINANCING_KEYWORDS  = ("prestit", "mutuo", "debit", "finanziament", "loan", "rata")


# ── Date helpers ───────────────────────────────────────────────────────────────

def available_years() -> list[int]:
    """Years that contain at least one transaction (newest first); current year if none."""
    rows = db.session.query(extract("year", Transaction.date)).distinct().all()
    years = sorted({int(r[0]) for r in rows if r[0] is not None}, reverse=True)
    return years or [date.today().year]


# ── Aggregations ───────────────────────────────────────────────────────────────

def _sum(tx_type: str, start: date, end: date) -> float:
    return value_total(Transaction.type == tx_type, Transaction.date >= start, Transaction.date < end)


def totals(start: date, end: date) -> dict:
    income = _sum("income", start, end)
    expenses = _sum("expense", start, end)
    net = income - expenses
    return {
        "income": income,
        "expenses": expenses,
        "net": net,
        "savings_rate": savings_rate(income, expenses),
    }


def savings_rate(income: float, expenses: float) -> float:
    if income <= 0:
        return 0.0
    return round((income - expenses) / income * 100, 1)


def category_breakdown(start: date, end: date, tx_type: str = "expense") -> list[dict]:
    """Totals per main category of the period (subcategories added to theirs), biggest first, with share (%)."""
    return breakdown(Transaction.query.filter(Transaction.date >= start, Transaction.date < end), tx_type)


def breakdown(query, tx_type: str, within: str | None = None) -> list[dict]:
    """Total per main category of one type (subcategories added to theirs), biggest first, with its share (%).
    `within` a main category: its own split, by subcategory."""
    query = with_lines(query.filter(Transaction.type == tx_type))
    if within:
        query = query.filter(LINE_CATEGORY.in_(categories.with_children(within)))
    rows = query.with_entities(LINE_CATEGORY, func.sum(LINE_VALUE), func.count()).group_by(LINE_CATEGORY).all()
    grouped: dict[str, list] = {}
    for category, amount, count in rows:
        key = category if within else categories.top(category)
        entry = grouped.setdefault(key or UNCATEGORIZED, [0.0, 0])
        entry[0] += float(amount or 0)
        entry[1] += count
    total = sum(amount for amount, _ in grouped.values())
    items = [{"category": name, "amount": amount, "count": count, "share": share(amount, total)}
             for name, (amount, count) in grouped.items()]
    return sorted(items, key=lambda item: item["amount"], reverse=True)


def monthly_series(year: int) -> dict:
    """Income / expenses / net for each month of `year`."""
    rows = (
        db.session.query(
            extract("month", Transaction.date),
            Transaction.type,
            func.sum(func.abs(Transaction.amount_base)),
        )
        .filter(extract("year", Transaction.date) == year, Transaction.type.in_(["income", "expense"]))
        .group_by(extract("month", Transaction.date), Transaction.type)
        .all()
    )
    income = [0.0] * 12
    expenses = [0.0] * 12
    for month, tx_type, amount in rows:
        target = income if tx_type == "income" else expenses
        target[int(month) - 1] = float(amount)
    net = [round(i - e, 2) for i, e in zip(income, expenses)]
    return {"labels": month_labels(), "income": income, "expenses": expenses, "net": net}


def savings_rates_by_year(today: date | None = None) -> dict:
    """
    The savings rate of each month, one line per year with income (newest first), to compare any years: None where
    a month had no income (a gap, not a misleading 0%) and for the months still to come. `rate`: the whole year's
    (so far, for the current year).
    """
    today = today or date.today()
    years = []
    for year in available_years():
        series = monthly_series(year)
        months = months_to_show(year, today)
        income, expenses = series["income"][:months], series["expenses"][:months]
        if sum(income) <= 0:
            continue
        rates = [savings_rate(i, e) if i > 0 else None for i, e in zip(income, expenses)]
        years.append({"year": year, "rates": rates + [None] * (12 - months),
                      "rate": savings_rate(sum(income), sum(expenses))})
    return {"labels": month_labels(), "years": years}


def _by_month_and_category(year: int) -> list[tuple[int, str, str | None, float]]:
    """(month 0-11, type, category, value) of the income and expenses of `year`."""
    rows = (
        lines_query(extract("month", Transaction.date), Transaction.type, LINE_CATEGORY, func.sum(LINE_VALUE))
        .filter(extract("year", Transaction.date) == year, Transaction.type.in_(["income", "expense"]))
        .group_by(extract("month", Transaction.date), Transaction.type, LINE_CATEGORY)
        .all()
    )
    return [(int(month) - 1, tx_type, category, float(amount or 0)) for month, tx_type, category, amount in rows]


def _change(current: float, previous: float) -> float | None:
    """Change on the year before in %; None when the year before had nothing to compare with."""
    return round((current - previous) / previous * 100, 1) if previous else None


def _previous_totals(year: int, months: int) -> dict[tuple[str, str], float]:
    """{(type, category): total of the first `months` months of `year`}, for main categories and subcategories."""
    totals: dict[tuple[str, str], float] = {}
    for month, tx_type, category, amount in _by_month_and_category(year):
        if month < months:
            for name in {categories.main_or(category, UNCATEGORIZED), category or UNCATEGORIZED}:
                totals[(tx_type, name)] = totals.get((tx_type, name), 0.0) + amount
    return totals


def summary_table(year: int, months: int = 12) -> dict:
    """
    The year as a category × month table (the spreadsheet inside the app): for income and expenses, one row per
    main category (subcategories added to it, and listed as child rows), the month columns, total, monthly average
    and change on the same months of the year before; then net and savings rate per month. `months`: the
    columns shown (the months so far, for the current year).
    """
    previous_totals = _previous_totals(year - 1, months)

    def row(tx_type: str, name: str) -> dict:
        return {"name": name, "months": [0.0] * months, "children": {}, "type": tx_type}

    sections = {"income": {}, "expense": {}}
    for month, tx_type, category, amount in _by_month_and_category(year):
        if month >= months:
            continue
        main = categories.main_or(category, UNCATEGORIZED)
        parent = sections[tx_type].setdefault(main, row(tx_type, main))
        parent["months"][month] += amount
        if category and category != main:
            child = parent["children"].setdefault(category, row(tx_type, category))
            child["months"][month] += amount

    def finish(item: dict) -> dict:
        item["months"] = [round(v, 2) for v in item["months"]]
        item["total"] = round(sum(item["months"]), 2)
        item["average"] = round(item["total"] / months, 2) if months else 0.0
        item["max"] = max(item["months"], default=0.0)
        item["previous"] = round(previous_totals.get((item["type"], item["name"]), 0.0), 2)
        item["change"] = _change(item["total"], item["previous"])
        item["children"] = sorted((finish(c) for c in item["children"].values()), key=lambda c: -c["total"])
        return item

    blocks = {}
    for tx_type, rows in sections.items():
        items = sorted((finish(item) for item in rows.values()), key=lambda r: (-r["total"], r["name"]))
        total = finish({**row(tx_type, ""), "months": [sum(r["months"][m] for r in items) for m in range(months)]})
        total["previous"] = round(sum(v for (t, name), v in previous_totals.items()
                                      if t == tx_type and categories.top(name) in (None, name)), 2)
        total["change"] = _change(total["total"], total["previous"])
        blocks[tx_type] = {"rows": items, "total": total}
    income, expenses = blocks["income"]["total"], blocks["expense"]["total"]
    net = [round(i - e, 2) for i, e in zip(income["months"], expenses["months"])]
    return {
        "year": year, "labels": month_labels()[:months], "months": months,
        "income": blocks["income"], "expense": blocks["expense"],
        "net": {"months": net, "total": round(income["total"] - expenses["total"], 2),
                "average": round((income["total"] - expenses["total"]) / months, 2) if months else 0.0},
        "savings": {"months": [savings_rate(i, e) if i > 0 else None for i, e in zip(income["months"], expenses["months"])],
                    "total": savings_rate(income["total"], expenses["total"]) if income["total"] > 0 else None},
    }


def last_12_months(today: date | None = None) -> dict:
    """Income / expenses for the 12 months ending with the month of `today`."""
    today = today or date.today()
    labels, income, expenses = [], [], []
    for delta in range(-11, 1):
        y, m = shift_month(today.year, today.month, delta)
        start, end = month_bounds(y, m)
        labels.append(month_label(month_index(start)))
        income.append(_sum("income", start, end))
        expenses.append(_sum("expense", start, end))
    return {"labels": labels, "income": income, "expenses": expenses}


def monthly_category_trend(year: int, top_n: int = 5, tx_type: str = "expense", months: int = 12,
                           other: bool = False) -> dict:
    """
    Monthly series of the top `top_n` categories of `tx_type` in `year` (first `months` months); with `other`,
    one more series "Altre" adds up the remaining categories, so the lines account for the whole total.
    """
    breakdown = category_breakdown(*year_bounds(year), tx_type=tx_type)
    names = [item["category"] for item in breakdown[:top_n]]
    series = {name: [0.0] * months for name in names}
    rest = [0.0] * months
    rows = (
        lines_query(extract("month", Transaction.date), LINE_CATEGORY, func.sum(LINE_VALUE))
        .filter(extract("year", Transaction.date) == year, Transaction.type == tx_type)
        .group_by(extract("month", Transaction.date), LINE_CATEGORY)
        .all()
    )
    for month, category, amount in rows:
        index = int(month) - 1
        if index >= months:
            continue
        name = categories.main_or(category, UNCATEGORIZED)
        target = series.get(name)
        if target is not None:
            target[index] = round(target[index] + float(amount), 2)
        else:
            rest[index] = round(rest[index] + float(amount), 2)
    datasets = [{"label": n, "data": series[n]} for n in names]
    if other and len(breakdown) > top_n:
        datasets.append({"label": OTHER, "data": rest, "other": True})
    return {"labels": month_labels()[:months], "datasets": datasets}


def cumulative_series(year: int, months: int = 12) -> dict:
    """Income and expenses month by month and their running totals since January (first `months` months)."""
    series = monthly_series(year)
    income, expenses = series["income"][:months], series["expenses"][:months]
    return {
        "labels": series["labels"][:months],
        "income": income, "expenses": expenses,
        "income_cumulative": [round(v, 2) for v in accumulate(income)],
        "expenses_cumulative": [round(v, 2) for v in accumulate(expenses)],
        "total_income": sum(income), "total_expenses": sum(expenses),
    }


def months_to_show(year: int, today: date | None = None) -> int:
    """12 for a past year; for the current year only the months so far (no flat future months)."""
    today = today or date.today()
    return today.month if year == today.year else 12


# ── Page-level reports ─────────────────────────────────────────────────────────

def dashboard_kpis(today: date | None = None) -> dict:
    today = today or date.today()
    month_start, month_end = month_bounds(today.year, today.month)
    month = totals(month_start, month_end)
    sheet = wealth.balance_sheet(today)
    runway = autonomy(today, sheet)
    income = wealth.monthly_average_income(today)
    installments = wealth.monthly_installments(today)

    return {
        "net_worth": sheet["net_worth"],
        "monthly_income": month["income"],
        "monthly_expenses": month["expenses"],
        "savings_rate": max(month["savings_rate"], 0.0),
        "total_investments": sheet["investments"],
        "total_debt": sheet["total_liabilities"],
        "autonomy": runway,
        "debt_to_income": share(installments, income) if income else None,
    }


def income_statement(year: int) -> dict:
    start, end = year_bounds(year)
    summary = totals(start, end)
    income_lines = category_breakdown(start, end, "income")
    expense_lines = category_breakdown(start, end, "expense")
    for line in income_lines + expense_lines:
        line["share_of_income"] = (
            share(line["amount"], summary["income"]) if summary["income"] else None
        )
    return {
        "year": year,
        "summary": summary,
        "income_lines": income_lines,
        "expense_lines": expense_lines,
        "monthly": monthly_series(year),
    }


def _classify_transfer(category: str | None) -> str | None:
    name = (category or "").lower()
    if any(k in name for k in INVESTING_KEYWORDS):
        return "investing"
    if any(k in name for k in FINANCING_KEYWORDS):
        return "financing"
    return None


def cash_flow_bucket(tx_type: str, category: str | None, holding_id: int | None, debt_id: int | None) -> str:
    """
    Where a transaction goes in the cash-flow statement: linked to an investment → investing, to a debt →
    financing; otherwise income/expenses are operating and transfers are classified by category name
    (kept as a fallback for transactions not linked yet), or left out (money between own accounts).
    """
    if holding_id:
        return "investing"
    if debt_id:
        return "financing"
    if tx_type == "transfer":
        return _classify_transfer(category) or "internal"
    return "operating"


def cash_flow(year: int) -> dict:
    """
    Cash-flow statement:
      A. Operating  = income − expenses not linked to an investment or a debt
      B. Investing  = money into (−) and out of (+) investments: linked transactions, or transfers
                      to investment categories
      C. Financing  = loans received (+) and repaid (−): linked transactions, or transfers to loan categories
    """
    start, end = year_bounds(year)
    buckets = {"operating": 0.0, "investing": 0.0, "financing": 0.0}
    monthly_net = [0.0] * 12
    linked = 0
    rows = (
        db.session.query(extract("month", Transaction.date), Transaction.type, Transaction.category,
                         Transaction.holding_id, Transaction.debt_id, func.abs(Transaction.amount_base))
        .filter(Transaction.date >= start, Transaction.date < end)
        .all()
    )
    for month, tx_type, category, holding_id, debt_id, amount in rows:
        bucket = cash_flow_bucket(tx_type, category, holding_id, debt_id)
        if bucket == "internal":
            continue
        signed = float(amount or 0) * (1 if tx_type == "income" else -1)
        buckets[bucket] += signed
        monthly_net[int(month) - 1] += signed
        linked += bool(holding_id or debt_id)

    net_monthly = [round(v, 2) for v in monthly_net]
    cumulative, running = [], 0.0
    for value in net_monthly:
        running += value
        cumulative.append(round(running, 2))

    return {
        "year": year,
        "operating": round(buckets["operating"], 2),
        "investing": round(buckets["investing"], 2),
        "financing": round(buckets["financing"], 2),
        "net_change": round(sum(buckets.values()), 2),
        "linked": linked,
        "labels": month_labels(),
        "net_monthly": net_monthly,
        "cumulative": cumulative,
    }


def lifestyle_report(year: int, today: date | None = None) -> dict:
    today = today or date.today()
    start, end = year_bounds(year)
    breakdown = category_breakdown(start, end)
    total_expenses = sum(item["amount"] for item in breakdown)

    # Month-over-month comparison: latest month of the selected year that is not in the future
    ref_month = today.month if year == today.year else 12
    this_start, this_end = month_bounds(year, ref_month)
    prev_start, prev_end = month_bounds(*shift_month(year, ref_month, -1))
    this_month = {i["category"]: i["amount"] for i in category_breakdown(this_start, this_end)}
    last_month = {i["category"]: i["amount"] for i in category_breakdown(prev_start, prev_end)}

    # biggest this month first; ties (often nothing yet this month) by last month, then by name: a stable order
    names = sorted(set(this_month) | set(last_month), key=lambda n: (-this_month.get(n, 0), -last_month.get(n, 0), n))
    this_total = sum(this_month.values())
    rows = []
    for name in names:
        current, previous = this_month.get(name, 0.0), last_month.get(name, 0.0)
        rows.append({
            "category": name,
            "this_month": current,
            "last_month": previous,
            "change": _change(current, previous),
            "share": share(current, this_total),
        })

    months_elapsed = ref_month
    non_essential = categories.discretionary()  # marked in Settings → Categorie
    discretionary = sum(i["amount"] for i in breakdown if i["category"] in non_essential)

    return {
        "year": year,
        "total_expenses": total_expenses,
        "monthly_average": total_expenses / months_elapsed if months_elapsed else 0.0,
        "top_category": breakdown[0]["category"] if breakdown else None,
        "discretionary_share": share(discretionary, total_expenses),
        "breakdown": breakdown,
        "rows": rows,
        "this_month_total": this_total,
        "last_month_total": sum(last_month.values()),
        "reference_month": month_labels()[ref_month - 1],
        "trend": monthly_category_trend(year),
        "natures": nature_split(start, end),
        "months_elapsed": months_elapsed,
    }
