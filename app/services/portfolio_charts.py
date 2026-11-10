"""
The data of the portfolio's charts (G40, G41, G50 of reports/Grafici da riportare.md), built here so the templates only
hand it to the chart helpers of static/js/charts.js:

- the price of a holding with its purchases, sales, dividends and coupons as markers and its average purchase price;
- the weights of a rebalancing plan against their targets and tolerance bands;
- the allocation as a tree, asset class → holding, for the treemap of the positions page.
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import date
from decimal import Decimal

from app.models.wealth import Holding, HoldingPrice
from app.services import asset_classes, portfolio_ops
from app.services.i18n import tr


def _number(value, places: int = 4) -> float:
    return round(float(value), places)


def price_chart(holding: Holding, points: list[HoldingPrice]) -> dict:
    """The price line on the days of the price history and of the operations (one axis for both), the markers of the
    purchases and sales at their unit price, the dividends and coupons on the price line of their day, and the average
    purchase price of the units held now (None when none are held)."""
    prices = {p.on: float(p.price) for p in points}
    trades = portfolio_ops.trades(holding)
    income = [tx for tx in portfolio_ops.operations(holding)
              if tx.holding_id == holding.id and portfolio_ops.kind_of(tx) in ("dividend", "coupon")]
    days = sorted(set(prices) | {t.date for t in trades} | {tx.date for tx in income})
    known = sorted(prices)

    def price_on(day: date) -> float | None:
        """The price of that day, else the latest before it, else the first after it."""
        if not known:
            return None
        i = bisect_right(known, day)
        return prices[known[i - 1]] if i else prices[known[0]]

    buys, sells = [], []
    for trade in trades:
        units = Decimal(trade.units)
        point = {"x": trade.date.isoformat(), "y": _number(trade.unit_price), "units": _number(abs(units))}
        (buys if units > 0 else sells).append(point)
    paid = [{"x": tx.date.isoformat(), "y": price_on(tx.date), "amount": _number(tx.amount, 2),
             "kind": portfolio_ops.kind_of(tx)} for tx in sorted(income, key=lambda tx: (tx.date, tx.id))]
    held = Decimal(holding.quantity or 0) > 0 and holding.avg_price
    return {
        "labels": [d.isoformat() for d in days],
        "data": [prices.get(d) for d in days],
        "prices": len(prices),
        "buys": buys,
        "sells": sells,
        "income": [p for p in paid if p["y"] is not None],
        "avg_price": _number(holding.avg_price) if held else None,
    }


def target_bands(plan) -> dict:
    """Each part of a rebalancing plan: its weight now, its target and the band around the target (target ± the
    template's tolerance, never below zero), and whether it is outside the band."""
    band = Decimal(plan.template.band or 0)
    return {
        "labels": [line.label for line in plan.lines],
        "weight": [_number(line.weight, 2) for line in plan.lines],
        "target": [_number(line.target, 2) for line in plan.lines],
        "band": [[_number(max(Decimal(0), line.target - band), 2), _number(line.target + band, 2)]
                 for line in plan.lines],
        "off": [abs(line.drift) > band for line in plan.lines],
        "tolerance": _number(band, 2),
    }


def allocation_tree(holdings: list[Holding]) -> list[dict]:
    """The holdings with a value as leaves of their asset class (translated), the largest class first and, inside
    it, the largest holding first."""
    leaves = [{"asset_class": tr(asset_classes.of(h)), "name": h.name, "value": round(float(h.value), 2)}
              for h in holdings if h.value and h.value > 0]
    by_group: dict[str, float] = {}
    for leaf in leaves:
        by_group[leaf["asset_class"]] = by_group.get(leaf["asset_class"], 0.0) + leaf["value"]
    return sorted(leaves, key=lambda leaf: (-by_group[leaf["asset_class"]], leaf["asset_class"], -leaf["value"]))
