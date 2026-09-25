"""
Financial analytics computed from transactions.

Amounts are stored as positive numbers; the direction comes from `type`
("income" | "expense" | "transfer").
"""
from collections import defaultdict
from datetime import date

from sqlalchemy import extract, func

from app.extensions import db
from app.models.transaction import Transaction
from app.services.periods import MONTH_LABELS, month_bounds, month_index, month_label, shift_month, year_bounds

UNCATEGORIZED = "Senza categoria"

# Categories considered non-essential when computing the discretionary share
DISCRETIONARY_CATEGORIES = {"Svago", "Abbonamenti", "Ristoranti", "Viaggi", "Shopping", "Hobby"}

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
    total = (
        db.session.query(func.coalesce(func.sum(func.abs(Transaction.amount)), 0))
        .filter(Transaction.type == tx_type, Transaction.date >= start, Transaction.date < end)
        .scalar()
    )
    return float(total)


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
    """Totals per category, sorted by amount descending, with share of total (%)."""
    rows = (
        db.session.query(Transaction.category, func.sum(func.abs(Transaction.amount)))
        .filter(Transaction.type == tx_type, Transaction.date >= start, Transaction.date < end)
        .group_by(Transaction.category)
        .all()
    )
    grand_total = sum(float(amount) for _, amount in rows)
    items = [
        {
            "category": category or UNCATEGORIZED,
            "amount": float(amount),
            "share": round(float(amount) / grand_total * 100, 1) if grand_total else 0.0,
        }
        for category, amount in rows
    ]
    return sorted(items, key=lambda i: i["amount"], reverse=True)


def monthly_series(year: int) -> dict:
    """Income / expenses / net for each month of `year`."""
    rows = (
        db.session.query(
            extract("month", Transaction.date),
            Transaction.type,
            func.sum(func.abs(Transaction.amount)),
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
    return {"labels": MONTH_LABELS, "income": income, "expenses": expenses, "net": net}


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


def monthly_category_trend(year: int, top_n: int = 5) -> dict:
    """Monthly expense series for the top `top_n` expense categories of `year`."""
    top = category_breakdown(*year_bounds(year))[:top_n]
    names = [item["category"] for item in top]
    series = {name: [0.0] * 12 for name in names}
    rows = (
        db.session.query(
            extract("month", Transaction.date),
            Transaction.category,
            func.sum(func.abs(Transaction.amount)),
        )
        .filter(extract("year", Transaction.date) == year, Transaction.type == "expense")
        .group_by(extract("month", Transaction.date), Transaction.category)
        .all()
    )
    for month, category, amount in rows:
        name = category or UNCATEGORIZED
        if name in series:
            series[name][int(month) - 1] = float(amount)
    return {"labels": MONTH_LABELS, "datasets": [{"label": n, "data": series[n]} for n in names]}


# ── Page-level reports ─────────────────────────────────────────────────────────

def dashboard_kpis(today: date | None = None) -> dict:
    today = today or date.today()
    month_start, month_end = month_bounds(today.year, today.month)
    month = totals(month_start, month_end)

    # Net worth approximation: all-time cash balance from transactions
    all_time = totals(date.min, date.max)

    # Emergency fund: months of average expenses covered by the cash balance
    trailing = last_12_months(today)
    avg_expenses = sum(trailing["expenses"]) / 12
    emergency_months = round(all_time["net"] / avg_expenses, 1) if avg_expenses > 0 else 0.0

    return {
        "net_worth": all_time["net"],
        "monthly_income": month["income"],
        "monthly_expenses": month["expenses"],
        "savings_rate": max(month["savings_rate"], 0.0),
        "total_investments": 0,  # TODO: sum portfolio holdings once the model exists
        "total_debt": 0,         # TODO: sum outstanding debts once the model exists
        "emergency_months": max(emergency_months, 0.0),
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


def cash_flow(year: int) -> dict:
    """
    Simplified cash-flow statement:
      A. Operating  = income − expenses
      B. Investing  = transfers into investment categories (outflows)
      C. Financing  = transfers into loan/mortgage categories (outflows)
    """
    start, end = year_bounds(year)
    operating = totals(start, end)["net"]

    investing = financing = 0.0
    transfers = defaultdict(float)
    rows = (
        db.session.query(extract("month", Transaction.date), Transaction.category, func.abs(Transaction.amount))
        .filter(Transaction.type == "transfer", Transaction.date >= start, Transaction.date < end)
        .all()
    )
    for month, category, amount in rows:
        bucket = _classify_transfer(category)
        if bucket == "investing":
            investing -= float(amount)
        elif bucket == "financing":
            financing -= float(amount)
        else:
            continue
        transfers[int(month)] += float(amount)

    monthly = monthly_series(year)
    net_monthly = [round(n - transfers[i + 1], 2) for i, n in enumerate(monthly["net"])]
    cumulative, running = [], 0.0
    for value in net_monthly:
        running += value
        cumulative.append(round(running, 2))

    return {
        "year": year,
        "operating": operating,
        "investing": investing,
        "financing": financing,
        "net_change": operating + investing + financing,
        "labels": MONTH_LABELS,
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
    discretionary = sum(i["amount"] for i in breakdown if i["category"] in DISCRETIONARY_CATEGORIES)

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
        "reference_month": MONTH_LABELS[ref_month - 1],
        "trend": monthly_category_trend(year),
    }
