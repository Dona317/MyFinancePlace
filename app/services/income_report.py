"""
Passive income (F20): dividends, coupons and interest, by month, by year and by holding, with the yield on what was
paid and on what it is worth now, and the next twelve months estimated from the last twelve.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import categories, periods
from app.services.i18n import N_

DIVIDENDS, INTEREST = "Dividendi e cedole", "Interessi"
KINDS = {"dividend": N_("Dividendi"), "coupon": N_("Cedole"), "interest": N_("Interessi")}


@dataclass
class Payment:
    tx: Transaction
    kind: str
    amount: Decimal


@dataclass
class HoldingIncome:
    holding: Holding
    year: Decimal
    last_12: Decimal

    @property
    def yield_on_cost(self) -> float | None:
        return float(self.last_12) / self.holding.cost * 100 if self.holding.cost else None

    @property
    def yield_on_value(self) -> float | None:
        return float(self.last_12) / self.holding.value * 100 if self.holding.value else None


def _kind(tx: Transaction, holding: Holding | None) -> str:
    if categories.top(tx.category) == INTEREST and holding is None:
        return "interest"
    if (holding is not None and holding.asset_class == "Obbligazione") or "cedol" in (tx.description or "").lower():
        return "coupon"
    return "dividend" if holding is not None or categories.top(tx.category) == DIVIDENDS else "interest"


def payments(start: date | None = None, end: date | None = None) -> list[Payment]:
    """Every dividend, coupon and interest received in [start, end]."""
    query = Transaction.query.filter(Transaction.type == "income")
    if start:
        query = query.filter(Transaction.date >= start)
    if end:
        query = query.filter(Transaction.date <= end)
    holdings = {h.id: h for h in Holding.query.all()}
    found = []
    for tx in query.order_by(Transaction.date).all():
        holding = holdings.get(tx.holding_id)
        if holding is None and categories.top(tx.category) not in (DIVIDENDS, INTEREST):
            continue
        amount = abs(Decimal(tx.amount_base if tx.amount_base is not None else tx.amount))
        found.append(Payment(tx, _kind(tx, holding), amount))
    return found


def report(year: int, today: date | None = None) -> dict:
    today = today or date.today()
    every = payments()
    months = {kind: [Decimal(0)] * 12 for kind in KINDS}
    by_year, per_holding, per_holding_12 = defaultdict(Decimal), defaultdict(Decimal), defaultdict(Decimal)
    since = periods.add_months(today, -12)
    for p in every:
        by_year[p.tx.date.year] += p.amount
        if p.tx.date.year == year:
            months[p.kind][p.tx.date.month - 1] += p.amount
            if p.tx.holding_id:
                per_holding[p.tx.holding_id] += p.amount
        if since < p.tx.date <= today and p.tx.holding_id:
            per_holding_12[p.tx.holding_id] += p.amount
    last_12 = sum((p.amount for p in every if since < p.tx.date <= today), Decimal(0))
    holdings = {h.id: h for h in Holding.query.filter(Holding.id.in_(set(per_holding) | set(per_holding_12)))}
    rows = sorted((HoldingIncome(holdings[i], per_holding[i], per_holding_12[i]) for i in holdings),
                  key=lambda r: (-r.year, -r.last_12, r.holding.name))
    return {"year": year, "months": months, "total": sum((sum(v) for v in months.values()), Decimal(0)),
            "by_year": sorted(by_year.items()), "holdings": rows, "last_12": last_12,
            "monthly_average": (last_12 / 12).quantize(Decimal("0.01")),
            "years": sorted({p.tx.date.year for p in every} | {today.year}, reverse=True)}
