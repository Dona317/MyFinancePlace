"""
The exchange-rate effect (F43, F49): for a holding quoted in another currency (an Apple share in dollars, an ETF
in pounds), how much of its return in euro came from the instrument and how much from the currency.

From the prices kept with their quote (HoldingPrice.price_ccy, currency, fx_rate), between the first price since the
holding was bought and the latest one:

    (1 + return in euro) = (1 + return in its currency) × (1 + change of the exchange rate)

and the euro the currency added (or took) on today's value: value − value / (1 + change of the rate).
Holdings in euro, or without two prices in their currency, have no effect to show.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.models.wealth import Holding, HoldingPrice
from app.services import money


@dataclass
class Effect:
    holding: Holding
    currency: str
    start: date
    end: date
    local: float          # the instrument's return in its own currency (0.12 = +12 %)
    fx: float             # the change of the exchange rate (euro for one unit), same period
    total: float          # the return in euro: (1 + local) × (1 + fx) − 1
    fx_euro: Decimal      # euro the currency added (+) or took (−) on today's value


def of_holding(holding: Holding) -> Effect | None:
    query = (HoldingPrice.query.filter(HoldingPrice.holding_id == holding.id, HoldingPrice.price_ccy.isnot(None),
                                       HoldingPrice.fx_rate.isnot(None))
             .order_by(HoldingPrice.on))
    if holding.purchase_date:
        query = query.filter(HoldingPrice.on >= holding.purchase_date)
    points = query.all()
    if len(points) < 2:
        return None
    first, last = points[0], points[-1]
    if not first.price_ccy or not first.fx_rate:
        return None
    local = float(last.price_ccy / first.price_ccy) - 1
    fx = float(last.fx_rate / first.fx_rate) - 1
    value = Decimal(str(holding.value))
    fx_euro = money.cents(value - value / Decimal(str(1 + fx))) if fx > -1 else Decimal(0)
    return Effect(holding, last.currency, first.on, last.on, local, fx, (1 + local) * (1 + fx) - 1, fx_euro)


@dataclass
class Summary:
    effects: list[Effect]
    by_currency: dict[str, Decimal]   # currency → euro added or taken by it
    total: Decimal


def of_holdings(holdings: list[Holding]) -> Summary:
    effects = [e for e in (of_holding(h) for h in holdings if (h.currency or "EUR") != "EUR") if e is not None]
    by_currency: dict[str, Decimal] = defaultdict(Decimal)
    for effect in effects:
        by_currency[effect.currency] += effect.fx_euro
    effects.sort(key=lambda e: -abs(e.fx_euro))
    return Summary(effects, dict(sorted(by_currency.items())), sum(by_currency.values(), Decimal(0)))
