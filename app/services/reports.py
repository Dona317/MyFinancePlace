"""
Reports: spending, income and cash flow over a chosen period, optionally for one account, with the split by
category, the transactions grouped by day and a summary. Amounts are in the base currency (`amount_base`).
"""
from datetime import date, timedelta

from sqlalchemy import func

from app.models.transaction import Transaction
from app.services.analytics import UNCATEGORIZED
from app.services.i18n import _l
from app.services.periods import add_months, month_index, month_label, month_start, year_bounds

TABS = {"spending": _l("Spese"), "income": _l("Entrate"), "cashflow": _l("Flusso di cassa")}
TAB_TYPE = {"spending": "expense", "income": "income"}
PERIODS = {
    "this_month": _l("Questo mese"), "last_month": _l("Mese scorso"), "last_3": _l("Ultimi 3 mesi"),
    "last_6": _l("Ultimi 6 mesi"), "last_12": _l("Ultimi 12 mesi"), "this_year": _l("Quest'anno"),
    "last_year": _l("Anno scorso"), "custom": _l("Personalizzato"),
}
SORTS = {"date": _l("Data (recenti prima)"), "amount": _l("Importo (più alti prima)")}
DEFAULT_PERIOD = "this_month"


def period_range(period: str, start: date | None = None, end: date | None = None,
                 today: date | None = None) -> tuple[date, date]:
    """[first day, day after the last) of a period keyword; `custom` uses start/end (inclusive end)."""
    today = today or date.today()
    this_month = month_index(today)
    if period == "custom" and start and end:
        first, last = min(start, end), max(start, end)
        return first, last + timedelta(days=1)
    if period == "last_month":
        return month_start(this_month - 1), month_start(this_month)
    if period in ("last_3", "last_6", "last_12"):
        months = int(period.split("_")[1])
        return month_start(this_month - months + 1), month_start(this_month + 1)
    if period == "this_year":
        return year_bounds(today.year)
    if period == "last_year":
        return year_bounds(today.year - 1)
    return month_start(this_month), month_start(this_month + 1)


def base_query(start: date, end: date, account: str = ""):
    """Transactions of the period; `account` = an id, "none" (without account) or "" (all)."""
    query = Transaction.query.filter(Transaction.date >= start, Transaction.date < end)
    if account == "none":
        query = query.filter(Transaction.account_id.is_(None), Transaction.counter_account_id.is_(None))
    elif account.isdigit():
        query = query.filter((Transaction.account_id == int(account)) | (Transaction.counter_account_id == int(account)))
    return query


def breakdown(query, tx_type: str) -> list[dict]:
    """Total per category of one type, biggest first, with its share (%) of the total."""
    rows = (query.filter(Transaction.type == tx_type)
            .with_entities(Transaction.category, func.sum(func.abs(Transaction.amount_base)), func.count())
            .group_by(Transaction.category).all())
    total = sum(float(amount or 0) for _, amount, _ in rows)
    items = [{"category": category or UNCATEGORIZED, "amount": float(amount or 0), "count": count,
              "share": round(float(amount or 0) / total * 100, 1) if total else 0.0} for category, amount, count in rows]
    return sorted(items, key=lambda item: item["amount"], reverse=True)


def signed(tx: Transaction) -> float:
    """Value with its direction: income positive, expense negative, transfer counted as zero."""
    return {"income": 1, "expense": -1}.get(tx.type, 0) * tx.magnitude


def transactions(query, tx_type: str | None, category: str | None, sort: str = "date") -> list[Transaction]:
    if tx_type:
        query = query.filter(Transaction.type == tx_type)
    else:
        query = query.filter(Transaction.type.in_(("income", "expense")))
    if category:
        query = query.filter(Transaction.category.is_(None) if category == UNCATEGORIZED else Transaction.category == category)
    if sort == "amount":
        return query.order_by(func.abs(Transaction.amount_base).desc(), Transaction.date.desc()).all()
    return query.order_by(Transaction.date.desc(), Transaction.id.desc()).all()


def by_day(rows: list[Transaction]) -> list[dict]:
    """The transactions grouped by day (in the order given), each day with its net total."""
    days: dict[date, dict] = {}
    for tx in rows:
        day = days.setdefault(tx.date, {"day": tx.date, "total": 0.0, "rows": []})
        day["rows"].append(tx)
        day["total"] += signed(tx)
    return list(days.values())


def summary(rows: list[Transaction]) -> dict:
    """Count, largest, average and total of the transactions (magnitudes: they are all of one kind)."""
    values = [tx.magnitude for tx in rows]
    largest = max(rows, key=lambda tx: tx.magnitude) if rows else None
    return {"count": len(rows), "largest": largest, "average": sum(values) / len(values) if values else 0.0,
            "total": sum(values)}


def cash_flow(query, start: date, end: date) -> dict:
    """Income, expenses and net for each month of the period, with the totals and the savings rate."""
    first, last = month_index(start), month_index(end - timedelta(days=1))
    months = {index: {"income": 0.0, "expenses": 0.0} for index in range(first, last + 1)}
    for tx in query.filter(Transaction.type.in_(("income", "expense"))).all():
        month = months.get(month_index(tx.date))
        if month is not None:
            month["income" if tx.type == "income" else "expenses"] += tx.magnitude
    income = sum(m["income"] for m in months.values())
    expenses = sum(m["expenses"] for m in months.values())
    return {
        "labels": [month_label(index) for index in months],
        "income": [round(m["income"], 2) for m in months.values()],
        "expenses": [round(m["expenses"], 2) for m in months.values()],
        "net": [round(m["income"] - m["expenses"], 2) for m in months.values()],
        "total_income": income, "total_expenses": expenses, "net_total": income - expenses,
        "savings_rate": (income - expenses) / income * 100 if income else None,
    }


def month_count(start: date, end: date) -> int:
    return month_index(end - timedelta(days=1)) - month_index(start) + 1


def previous_range(start: date, end: date) -> tuple[date, date]:
    """The period of the same length just before (for whole months, the same number of months)."""
    if start.day == 1 and end.day == 1:
        months = month_count(start, end)
        return add_months(start, -months), start
    return start - (end - start), start


def total(query, tx_type: str) -> float:
    return float(query.filter(Transaction.type == tx_type).with_entities(func.coalesce(func.sum(func.abs(Transaction.amount_base)), 0)).scalar())
