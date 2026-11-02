"""
How solid the finances are: months of autonomy (F8), expenses by the nature of their category, and how reliable each
source of income is (F10b).
"""
from datetime import date

from sqlalchemy import func

from app.extensions import db
from app.models.transaction import Transaction
from app.services import categories, wealth
from app.services.categories import UNCATEGORIZED
from app.services.i18n import N_
from app.services.money import share
from app.services.periods import first_of_month, last_complete_months, shift_month
from app.services.totals import LINE_CATEGORY, LINE_VALUE, lines_query, value_total

AUTONOMY_MIN_MONTHS = 3  # fewer complete months of spending: no average to trust


def autonomy(today: date | None = None, sheet: dict | None = None) -> dict:
    """
    Months of autonomy: how long the liquid money (cash, current and savings accounts) would pay the average monthly
    spending — all of it, or only the fixed and not monthly costs (category nature, F8). The average is over the
    last 12 complete months (fewer when the data starts later; None below AUTONOMY_MIN_MONTHS).
    """
    today = today or date.today()
    sheet = sheet or wealth.balance_sheet(today)
    liquid = float(sum(sheet["current_assets"].values()))
    end = first_of_month(today)
    first = db.session.query(func.min(Transaction.date)).filter(Transaction.type == "expense",
                                                                Transaction.date < end).scalar()
    months = min(12, (end.year - first.year) * 12 + end.month - first.month) if first else 0
    result = {"liquid": liquid, "basis": months, "avg_expenses": None, "avg_essential": None,
              "months_all": None, "months_essential": None}
    if months < AUTONOMY_MIN_MONTHS:
        return result
    start = date(*shift_month(end.year, end.month, -months), 1)
    natures = nature_split(start, end)["amounts"]
    result["avg_expenses"] = value_total(Transaction.type == "expense", Transaction.date >= start, Transaction.date < end) / months
    result["avg_essential"] = (natures["fixed"] + natures["periodic"]) / months
    for key, average in (("months_all", "avg_expenses"), ("months_essential", "avg_essential")):
        if result[average] > 0:
            result[key] = round(max(liquid, 0.0) / result[average], 1)
    return result


def nature_split(start: date, end: date) -> dict:
    """Expenses of [start, end) by the nature of their category (Settings → Categorie): fixed, not monthly, variable."""
    rows = (lines_query(LINE_CATEGORY, func.sum(LINE_VALUE))
            .filter(Transaction.date >= start, Transaction.date < end, Transaction.type == "expense")
            .group_by(LINE_CATEGORY).all())
    nature_of = categories.natures()
    amounts = dict.fromkeys(categories.NATURES, 0.0)
    for category, amount in rows:
        amounts[nature_of.get(category, "variable")] += float(amount or 0)
    total = sum(amounts.values())
    return {"total": total, "amounts": amounts,
            "parts": [{"key": key, "label": str(label), "amount": amounts[key],
                       "share": share(amounts[key], total)}
                      for key, label in categories.NATURES.items()]}


STABILITY_LABELS = {"stable": N_("Stabile"), "variable": N_("Variabile"), "occasional": N_("Occasionale")}


def income_stability(today: date | None = None) -> dict:
    """
    How reliable each source of income is (F10b), over the last 12 complete months: in how many months it came,
    its monthly average when it came, how much it varies (coefficient of variation) and its share of the income.
    Stable: at least 10 months and within ±15%; variable: at least 6 months; occasional: the rest.
    """
    today = today or date.today()
    start, end = last_complete_months(today, 12)
    month = func.date_trunc("month", Transaction.date)
    rows = (lines_query(month, LINE_CATEGORY, func.sum(LINE_VALUE))
            .filter(Transaction.type == "income", Transaction.date >= start, Transaction.date < end)
            .group_by(month, LINE_CATEGORY).all())
    by_source: dict[str, dict] = {}
    for day, category, amount in rows:
        months = by_source.setdefault(categories.main_or(category, UNCATEGORIZED), {})
        key = (day.year, day.month)
        months[key] = months.get(key, 0.0) + float(amount or 0)
    total = sum(sum(m.values()) for m in by_source.values())
    sources = []
    for name, months in by_source.items():
        values = list(months.values())
        average = sum(values) / len(values)
        spread = (sum((v - average) ** 2 for v in values) / len(values)) ** 0.5 / average if average else 0.0
        kind = "stable" if len(values) >= 10 and spread <= 0.15 else "variable" if len(values) >= 6 else "occasional"
        sources.append({"name": name, "months": len(values), "average": round(average, 2), "total": round(sum(values), 2),
                        "variation": round(spread * 100, 1), "share": round(sum(values) / total * 100, 1) if total else 0.0,
                        "kind": kind, "label": STABILITY_LABELS[kind]})
    sources.sort(key=lambda s: s["total"], reverse=True)
    stable = sum(s["total"] for s in sources if s["kind"] == "stable")
    return {"sources": sources, "total": round(total, 2), "monthly": round(total / 12, 2),
            "stable_share": share(stable, total) if total else None,
            "start": start, "end": end}
