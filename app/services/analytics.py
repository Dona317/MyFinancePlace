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
from app.services.i18n import N_
from app.services.periods import month_bounds, month_index, month_label, month_labels, shift_month, year_bounds
from app.services.totals import value_total

UNCATEGORIZED = N_("Senza categoria")
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
    """Totals per main category (subcategories added to theirs), sorted by amount descending, with share (%)."""
    rows = (
        db.session.query(Transaction.category, func.sum(func.abs(Transaction.amount_base)))
        .filter(Transaction.type == tx_type, Transaction.date >= start, Transaction.date < end)
        .group_by(Transaction.category)
        .all()
    )
    totals_by_main: dict[str, float] = {}
    for category, amount in rows:
        main = categories.top(category) or UNCATEGORIZED
        totals_by_main[main] = totals_by_main.get(main, 0.0) + float(amount)
    grand_total = sum(totals_by_main.values())
    items = [
        {"category": name, "amount": amount, "share": round(amount / grand_total * 100, 1) if grand_total else 0.0}
        for name, amount in totals_by_main.items()
    ]
    return sorted(items, key=lambda i: i["amount"], reverse=True)


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
        db.session.query(
            extract("month", Transaction.date),
            Transaction.category,
            func.sum(func.abs(Transaction.amount_base)),
        )
        .filter(extract("year", Transaction.date) == year, Transaction.type == tx_type)
        .group_by(extract("month", Transaction.date), Transaction.category)
        .all()
    )
    for month, category, amount in rows:
        index = int(month) - 1
        if index >= months:
            continue
        name = categories.top(category) or UNCATEGORIZED
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

    # Emergency fund: months of average expenses covered by cash and savings accounts
    trailing = last_12_months(today)
    avg_expenses = sum(trailing["expenses"]) / 12
    liquid = sum(sheet["current_assets"].values())
    emergency_months = round(liquid / avg_expenses, 1) if avg_expenses > 0 else 0.0
    income = wealth.monthly_average_income(today)
    installments = wealth.monthly_installments(today)

    return {
        "net_worth": sheet["net_worth"],
        "monthly_income": month["income"],
        "monthly_expenses": month["expenses"],
        "savings_rate": max(month["savings_rate"], 0.0),
        "total_investments": sheet["investments"],
        "total_debt": sheet["total_liabilities"],
        "emergency_months": max(emergency_months, 0.0),
        "debt_to_income": round(installments / income * 100, 1) if income else None,
    }


def income_statement(year: int) -> dict:
    start, end = year_bounds(year)
    summary = totals(start, end)
    income_lines = category_breakdown(start, end, "income")
    expense_lines = category_breakdown(start, end, "expense")
    for line in income_lines + expense_lines:
        line["share_of_income"] = (
            round(line["amount"] / summary["income"] * 100, 1) if summary["income"] else None
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

    names = sorted(set(this_month) | set(last_month), key=lambda n: this_month.get(n, 0), reverse=True)
    this_total = sum(this_month.values())
    rows = []
    for name in names:
        current, previous = this_month.get(name, 0.0), last_month.get(name, 0.0)
        rows.append({
            "category": name,
            "this_month": current,
            "last_month": previous,
            "change": round((current - previous) / previous * 100, 1) if previous else None,
            "share": round(current / this_total * 100, 1) if this_total else 0.0,
        })

    months_elapsed = ref_month
    non_essential = categories.discretionary()  # marked in Settings → Categorie
    discretionary = sum(i["amount"] for i in breakdown if i["category"] in non_essential)

    return {
        "year": year,
        "total_expenses": total_expenses,
        "monthly_average": total_expenses / months_elapsed if months_elapsed else 0.0,
        "top_category": breakdown[0]["category"] if breakdown else None,
        "discretionary_share": round(discretionary / total_expenses * 100, 1) if total_expenses else 0.0,
        "breakdown": breakdown,
        "rows": rows,
        "this_month_total": this_total,
        "last_month_total": sum(last_month.values()),
        "reference_month": month_labels()[ref_month - 1],
        "trend": monthly_category_trend(year),
    }


# ── Where the money goes: a Sankey diagram (income categories → total → expenses and savings) ─────────

SANKEY_SIDE = 7                   # categories shown on each side; the rest add up in "Altre"
SAVINGS = N_("Risparmio")
FROM_SAVINGS = N_("Dai risparmi")  # spent more than earned: the gap is taken from savings
SANKEY_WIDTH, SANKEY_HEIGHT, NODE, GAP = 1000, 420, 14, 10


def _sankey_side(items: list[dict]) -> list[tuple[str, float]]:
    shown = [(i["category"], i["amount"]) for i in items[:SANKEY_SIDE] if i["amount"] > 0]
    rest = sum(i["amount"] for i in items[SANKEY_SIDE:])
    return shown + ([(OTHER, rest)] if rest > 0 else [])


def _band(x0: float, y0: float, x1: float, y1: float, thickness: float) -> str:
    """An SVG path: a band of `thickness` from (x0, y0) to (x1, y1) (top edges), curved in the middle."""
    middle = (x0 + x1) / 2
    return (f"M{x0:.1f},{y0:.1f} C{middle:.1f},{y0:.1f} {middle:.1f},{y1:.1f} {x1:.1f},{y1:.1f} "
            f"L{x1:.1f},{y1 + thickness:.1f} C{middle:.1f},{y1 + thickness:.1f} {middle:.1f},{y0 + thickness:.1f} "
            f"{x0:.1f},{y0 + thickness:.1f} Z")


def sankey(start: date, end: date) -> dict | None:
    """
    Nodes and bands of the money flow in [start, end): income categories (left) → the total (middle) →
    expense categories and savings (right). Sizes are proportional to amounts; None when nothing moved.
    """
    incomes = _sankey_side(category_breakdown(start, end, "income"))
    expenses = _sankey_side(category_breakdown(start, end, "expense"))
    total_in, total_out = sum(a for _, a in incomes), sum(a for _, a in expenses)
    if not total_in and not total_out:
        return None
    if total_in > total_out:
        expenses.append((SAVINGS, total_in - total_out))
    elif total_out > total_in:
        incomes.append((FROM_SAVINGS, total_out - total_in))
    total = max(total_in, total_out)
    rows = max(len(incomes), len(expenses))
    scale = (SANKEY_HEIGHT - GAP * (rows - 1)) / total

    def column(items, x, kind):
        height = sum(a for _, a in items) * scale + GAP * (len(items) - 1)
        y, nodes = (SANKEY_HEIGHT - height) / 2, []
        for index, (name, amount) in enumerate(items):
            special = name in (SAVINGS, FROM_SAVINGS)
            nodes.append({"label": name, "amount": round(amount, 2), "x": x, "y": round(y, 1),
                          "h": round(max(amount * scale, 1), 1), "kind": kind, "special": special,
                          "color": "positive" if special else f"chart-{index % 8 + 1}"})
            y += amount * scale + GAP
        return nodes

    left = column(incomes, 0, "income")
    right = column(expenses, SANKEY_WIDTH - NODE, "expense")
    centre_x = (SANKEY_WIDTH - NODE) / 2
    centre = {"label": N_("Entrate"), "amount": round(total_in, 2), "x": centre_x,
              "y": round((SANKEY_HEIGHT - total * scale) / 2, 1), "h": round(total * scale, 1), "kind": "total",
              "special": False, "color": "primary"}
    bands, y_in, y_out = [], centre["y"], centre["y"]
    for node in left:   # each income flows into the middle, stacked
        bands.append({"d": _band(NODE, node["y"], centre_x, y_in, node["h"]), "color": node["color"],
                      "label": node["label"], "amount": node["amount"], "to": centre["label"]})
        y_in += node["h"]
    for node in right:  # the middle flows out to each expense, stacked
        bands.append({"d": _band(centre_x + NODE, y_out, node["x"], node["y"], node["h"]), "color": node["color"],
                      "label": centre["label"], "amount": node["amount"], "to": node["label"]})
        y_out += node["h"]
    return {"nodes": [*left, centre, *right], "bands": bands, "width": SANKEY_WIDTH, "height": SANKEY_HEIGHT,
            "node_width": NODE, "total_in": round(total_in, 2), "total_out": round(total_out, 2)}
