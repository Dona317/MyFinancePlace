"""
Assets valued by hand, and the ones that lose value (F22): a house, a car, gold, a collection.

A valuation is a price of a day with a note (an appraisal, the OMI value, the used-car list price). A holding with a
yearly depreciation (a car: about 15 %) loses that share of its value each year from its last valuation (or its
purchase): the points of each month are written by themselves, marked as estimated, and replaced as soon as a new
valuation is entered. Past balance sheets and the growth of net worth read them like any other price.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models.wealth import Holding, HoldingPrice
from app.services import money, periods, settings_store, wealth

LAST_RUN = "valuations.last_run"
SUGGESTED_RATES = {"Veicolo": Decimal(15)}  # proposed in the form for the class
HAND_VALUED = ("Immobile", "Veicolo", "Oggetti di valore", "Altro")  # «valuations» rather than «prices»


def revalue(holding: Holding, price: Decimal, on: date, note: str | None = None) -> None:
    """A valuation entered by hand: the estimates after it are dropped and the depreciation starts again from it."""
    wealth.record_price(holding, price, on)
    db.session.flush()
    point = HoldingPrice.query.filter_by(holding_id=holding.id, on=on).one()
    point.note, point.estimated = (note or "").strip() or None, False
    forget()


def _base(holding: Holding) -> tuple[date, Decimal] | None:
    """Where the depreciation starts: the last valuation by hand, else the purchase."""
    point = (HoldingPrice.query.filter_by(holding_id=holding.id, estimated=False)
             .order_by(HoldingPrice.on.desc()).first())
    if point is not None:
        return point.on, Decimal(point.price)
    start = holding.purchase_date or holding.opening_date
    price = holding.opening_price if holding.opening_price is not None else holding.avg_price
    return (start, Decimal(price)) if start is not None and price is not None else None


def worth(base_price: Decimal, rate: Decimal, start: date, on: date) -> Decimal:
    """`base_price` after losing `rate` % a year from `start` to `on`."""
    years = max((on - start).days, 0) / 365.25
    return money.price(base_price * Decimal(str((1 - float(rate) / 100) ** years)))


def depreciate(holding: Holding, today: date | None = None) -> int:
    """Write the estimated points (the 1st of each month after the base, and today); how many."""
    today = today or date.today()
    rate = holding.depreciation_rate
    base = _base(holding) if rate else None
    if base is None or base[0] >= today:
        return 0
    start, price = base
    HoldingPrice.query.filter(HoldingPrice.holding_id == holding.id, HoldingPrice.estimated.is_(True),
                              HoldingPrice.on > start).delete(synchronize_session=False)
    days, day = [], periods.add_months(periods.first_of_month(start), 1)
    while day < today:
        days.append(day)
        day = periods.add_months(day, 1)
    days.append(today)
    for on in days:
        db.session.add(HoldingPrice(holding_id=holding.id, on=on, price=worth(price, Decimal(rate), start, on),
                                    estimated=True))
    holding.current_price, holding.price_date = worth(price, Decimal(rate), start, today), today
    return len(days)


def forget() -> None:
    """Something changed: the next page visit writes the estimates again."""
    settings_store.set(LAST_RUN, "")


def refresh_daily(today: date | None = None) -> int:
    """Once a day (on the first visit of the dashboard or the portfolio): the depreciation of every asset that has one."""
    today = today or date.today()
    if settings_store.get(LAST_RUN) == today.isoformat():
        return 0
    settings_store.set(LAST_RUN, today.isoformat())
    count = sum(depreciate(h, today) for h in Holding.query.filter(Holding.depreciation_rate.isnot(None),
                                                                   Holding.depreciation_rate > 0))
    db.session.commit()
    return count
