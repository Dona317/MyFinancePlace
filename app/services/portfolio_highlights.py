"""
The portfolio at a glance (F22): what moved most since 1 January and in the last 12 months, the heaviest holdings and
how concentrated the portfolio is, how far it is from the active model, the prices that stopped moving and the
income expected in the next 12 months.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.models.wealth import Holding
from app.services import income_report, periods, portfolio_models, price_feed, wealth

SHOWN = 3
HEAVIEST = 5
STALE_DAYS = 30


@dataclass
class Move:
    holding: Holding
    then: float
    now: float

    @property
    def pct(self) -> float:
        return round((self.now / self.then - 1) * 100, 1)

    @property
    def gain(self) -> float:
        return round(self.holding.units * (self.now - self.then), 2)


def movers(holdings: list[Holding], since: date) -> dict[str, list[Move]]:
    """The holdings that gained and lost most (by price) since a day, with the price they had then."""
    prices = wealth.prices_on(since)
    moves = [Move(h, prices[h.id], h.price) for h in holdings
             if prices.get(h.id) and h.price and (h.purchase_date is None or h.purchase_date <= since)]
    moves.sort(key=lambda m: m.pct)
    return {"best": [m for m in reversed(moves) if m.pct > 0][:SHOWN], "worst": [m for m in moves if m.pct < 0][:SHOWN]}


def heaviest(holdings: list[Holding]) -> dict:
    total = sum(h.value for h in holdings)
    rows = sorted(((h, round(h.value / total * 100, 1)) for h in holdings if total), key=lambda row: -row[1])
    top = rows[:HEAVIEST]
    return {"rows": top, "top_share": round(sum(share for _, share in top), 1), "count": len(holdings)}


def stale(holdings: list[Holding], today: date) -> list[tuple[Holding, str]]:
    """Market holdings whose price is old, or that have no source to update it."""
    found = []
    for h in holdings:
        if h.asset_class not in price_feed.MARKET_CLASSES:
            continue
        if h.price_source == "manual":
            found.append((h, "manual"))
        elif h.price_date is None or h.price_date < today - timedelta(days=STALE_DAYS):
            found.append((h, "old"))
    return found


def model_gaps(holdings: list[Holding]) -> dict | None:
    """The lines of the active model furthest from their target."""
    template = portfolio_models.active()
    if template is None:
        return None
    lines, _ = portfolio_models.standing(template, holdings)
    gaps = sorted((line for line in lines if not line.outside), key=lambda line: -abs(line.drift))[:SHOWN]
    out = [line for line in lines if abs(line.drift) > Decimal(template.band)]
    return {"template": template, "gaps": gaps, "out_of_band": len(out)}


def highlights(today: date | None = None) -> dict:
    today = today or date.today()
    holdings = portfolio_models.investments()
    income = income_report.report(today.year, today)
    return {
        "today": today,
        "ytd": movers(holdings, date(today.year, 1, 1)),
        "year": movers(holdings, periods.add_months(today, -12)),
        "heaviest": heaviest(holdings),
        "stale": stale(holdings, today),
        "model": model_gaps(holdings),
        "income": {"next_12": income["last_12"], "monthly": income["monthly_average"],
                   "top": sorted(income["holdings"], key=lambda row: -row.last_12)[:SHOWN]},
    }
