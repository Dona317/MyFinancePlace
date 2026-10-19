"""
Stock splits and the composition of the portfolio (F20).

Split: «1 old share = N new» from a day — the units held before it are multiplied by N and the prices divided by N
(the opening position, the trades before the day, the price history), so values and gains do not jump.

Composition: each holding can say where it invests (region) and in what (sector); the portfolio's exposure is the
sum of the values by region and by sector. An ETF on the whole world is «Globale»; nothing set is «Non indicato».
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from flask_babel import gettext as _

from app.models.transaction import Transaction
from app.models.wealth import Holding, HoldingPrice
from app.services import money, portfolio_ops
from app.services.i18n import N_

REGIONS = [N_("Globale"), N_("Italia"), N_("Europa"), N_("Nord America"), N_("Asia e Pacifico"),
           N_("Mercati emergenti"), N_("Altro")]
SECTORS = [N_("Diversificato"), N_("Tecnologia"), N_("Finanza"), N_("Salute"), N_("Energia"), N_("Utilities"),
           N_("Industria"), N_("Beni di consumo"), N_("Immobiliare"), N_("Materie prime"),
           N_("Obbligazioni governative"), N_("Obbligazioni societarie"), N_("Liquidità"), N_("Altro")]
UNSET = N_("Non indicato")


def split(holding: Holding, ratio: Decimal, on: date) -> int:
    """Apply a split of `ratio` new units for each old one, effective on `on`; how many trades were adjusted."""
    if ratio is None or ratio <= 0 or ratio == 1:
        raise ValueError(_("Il rapporto deve essere un numero positivo diverso da 1 (es. 10 per «1 vecchia = 10 nuove»)."))
    portfolio_ops.ensure_opening(holding.id)
    if holding.opening_date is None or holding.opening_date < on:
        holding.opening_quantity = Decimal(holding.opening_quantity or 0) * ratio
        if holding.opening_price is not None:
            holding.opening_price = money.price(Decimal(holding.opening_price) / ratio)
    adjusted = 0
    for trade in Transaction.query.filter(Transaction.holding_id == holding.id, Transaction.units.isnot(None),
                                          Transaction.date < on):
        trade.units = Decimal(trade.units) * ratio
        trade.unit_price = money.price(Decimal(trade.unit_price) / ratio)
        adjusted += 1
    for point in HoldingPrice.query.filter(HoldingPrice.holding_id == holding.id, HoldingPrice.on < on):
        point.price = money.price(Decimal(point.price) / ratio)
    if holding.price_date is None or holding.price_date < on:
        if holding.current_price is not None:
            holding.current_price = money.price(Decimal(holding.current_price) / ratio)
    portfolio_ops.recompute(holding)
    return adjusted


def exposure(holdings: list[Holding]) -> dict:
    """{"region": [(name, value, %)], "sector": [...], "total": value}"""
    total = sum(h.value for h in holdings)
    result = {"total": round(total, 2)}
    for field in ("region", "sector"):
        sums = defaultdict(float)
        for h in holdings:
            sums[getattr(h, field) or UNSET] += h.value
        result[field] = sorted(((name, round(value, 2), round(value / total * 100, 1) if total else 0.0)
                                for name, value in sums.items() if value), key=lambda row: -row[1])
    return result
