"""
Where the net worth growth comes from (F20), month by month:

    change of the net worth = savings + markets + debt repaid + new assets + other

- savings: income minus expenses of the month (a mortgage instalment counts whole as an expense…)
- debt repaid: …and the capital it repaid comes back here, as the debts went down
- markets: what the holdings gained or lost, net of what was bought and sold in the month
- new assets: holdings entered in the month without trades (a house, a car, a position found later)
- other: whatever is left (exchange rates, corrections of balances, movements without a date in the period)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func

from app.extensions import db
from app.models.transaction import Transaction
from app.models.wealth import Debt, Holding
from app.services import wealth
from app.services.totals import VALUE, value_total


@dataclass
class Month:
    end: date
    net_worth: float
    change: float
    savings: float
    markets: float
    debt_repaid: float
    new_assets: float

    @property
    def other(self) -> float:
        return round(self.change - self.savings - self.markets - self.debt_repaid - self.new_assets, 2)


def _units_after(on: date) -> dict[int, float]:
    """Units bought minus sold after `on`, by holding: what is held today less these is what was held then."""
    rows = db.session.query(Transaction.holding_id, func.sum(Transaction.units)).filter(
        Transaction.holding_id.isnot(None), Transaction.units.isnot(None), Transaction.date > on).group_by(
        Transaction.holding_id)
    return {hid: float(units or 0) for hid, units in rows}


def _holdings_value(on: date) -> float:
    """The holdings at the quantity they had then (today's less the trades since) and the price they had then."""
    prices = wealth.prices_on(on) if on < date.today() else {}
    later = _units_after(on)
    total = 0.0
    for h in wealth.holdings_on(on):
        now = float(h.quantity or 0)
        share = (now - later.get(h.id, 0.0)) / now if now else 0.0
        total += wealth.value_on(h, on, prices) * share
    return total


def _owed(on: date) -> float:
    return sum(wealth.debt_summary(d, on)["balance"] for d in Debt.query.all())


def _net_buys(start: date, end: date) -> float:
    """Money put into holdings in (start, end]: purchases minus sales."""
    signed = func.sum(func.sign(Transaction.units) * VALUE)
    total = db.session.query(signed).filter(Transaction.holding_id.isnot(None), Transaction.units.isnot(None),
                                            Transaction.date > start, Transaction.date <= end).scalar()
    return float(total or 0)


def _new_assets(start: date, end: date) -> float:
    traded = {hid for (hid,) in db.session.query(Transaction.holding_id).filter(
        Transaction.holding_id.isnot(None), Transaction.units.isnot(None)).distinct()}
    prices = wealth.prices_on(end) if end < date.today() else {}
    return sum(wealth.value_on(h, end, prices) for h in Holding.query.filter(
        Holding.purchase_date > start, Holding.purchase_date <= end) if h.id not in traded)


def months(count: int = 12, today: date | None = None) -> list[Month]:
    """The last `count` months (the current one up to today), oldest first."""
    ends = list(reversed(wealth.month_ends(count + 1, today)))
    values = {end: _holdings_value(end) for end in ends}
    owed = {end: _owed(end) for end in ends}
    net = {end: wealth.cash_balance(end) + values[end] - owed[end] for end in ends}
    rows = []
    for start, end in zip(ends, ends[1:]):
        period = (Transaction.date > start, Transaction.date <= end)
        savings = value_total(Transaction.type == "income", *period) - value_total(Transaction.type == "expense", *period)
        new = _new_assets(start, end)
        markets = values[end] - values[start] - _net_buys(start, end) - new
        rows.append(Month(end, round(net[end], 2), round(net[end] - net[start], 2), round(savings, 2), round(markets, 2),
                          round(owed[start] - owed[end], 2), round(new, 2)))
    return rows


def velocity(rows: list[Month]) -> dict:
    """Average monthly growth and the share of it that came from saving."""
    if not rows:
        return {"monthly": 0.0, "savings": 0.0, "markets": 0.0, "savings_share": None}
    n = len(rows)
    change, savings, markets = (sum(getattr(r, field) for r in rows) / n for field in ("change", "savings", "markets"))
    return {"monthly": round(change, 2), "savings": round(savings, 2), "markets": round(markets, 2),
            "savings_share": round(savings / change * 100, 1) if change > 0 else None}

