"""
Investment plans, the Italian PAC (F19e): an amount invested every month or quarter on a set day. When the day comes,
a reminder asks to confirm; the confirmation page splits the amount as the model portfolio says (new money only:
the parts furthest below their target first) at the latest prices, and the purchases become the holdings' operations.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, Decimal

from flask_babel import gettext as _

from app.extensions import db
from app.models.portfolio_model import InvestmentPlan
from app.models.wealth import Holding
from app.services import broker, money, portfolio_models, portfolio_ops
from app.services.i18n import N_

FREQUENCIES = {"monthly": N_("Ogni mese"), "quarterly": N_("Ogni tre mesi")}
UNITS = Decimal("0.0001")


class PlanError(ValueError):
    """The plan cannot be saved or confirmed as it is; the message is shown to the user."""


def period(on: date) -> str:
    return f"{on:%Y-%m}"


def due_date(plan: InvestmentPlan, today: date) -> date | None:
    """This month's instalment day, when this month has one (quarterly: every third month from the start)."""
    if plan.frequency == "quarterly" and (today.month - plan.start.month) % 3:
        return None
    day = min(plan.day, calendar.monthrange(today.year, today.month)[1])
    return date(today.year, today.month, day)


def is_due(plan: InvestmentPlan, today: date) -> bool:
    if today < plan.start or (plan.end and today > plan.end):
        return False
    on = due_date(plan, today)
    return on is not None and on >= plan.start and today >= on and (plan.last_done or "") < period(today)


def due(today: date | None = None) -> list[InvestmentPlan]:
    today = today or date.today()
    return [plan for plan in InvestmentPlan.query.order_by(InvestmentPlan.name).all() if is_due(plan, today)]


def validate(name: str, amount: Decimal | None, frequency: str, day: int | None, start: date | None,
             end: date | None) -> None:
    if not name.strip():
        raise PlanError(_("Dai un nome al piano."))
    if amount is None or amount <= 0:
        raise PlanError(_("Indica un importo maggiore di zero."))
    if frequency not in FREQUENCIES:
        raise PlanError(_("Frequenza sconosciuta."))
    if day is None or not 1 <= day <= 31:
        raise PlanError(_("Il giorno va da 1 a 31."))
    if start is None:
        raise PlanError(_("Indica la data di inizio."))
    if end is not None and end < start:
        raise PlanError(_("La fine viene prima dell'inizio."))


# ── The purchases of an instalment ─────────────────────────────────────────────

@dataclass
class Purchase:
    label: str
    amount: Decimal
    holding: Holding | None       # None: a holding to create (the part's suggested instrument)
    isin: str | None
    ticker: str | None
    price: Decimal | None
    units: Decimal | None


def _units(amount: Decimal, price: Decimal | None, fractional: bool) -> Decimal | None:
    if not price:
        return None
    units = amount / price
    return units.quantize(UNITS, rounding=ROUND_DOWN) if fractional else units.to_integral_value(rounding=ROUND_DOWN)


def proposal(plan: InvestmentPlan) -> list[Purchase]:
    """The instalment split among the parts of the plan's model (or the active one) at the latest prices."""
    template = plan.template or portfolio_models.active()
    if template is None:
        raise PlanError(_("Il piano ha bisogno di un portafoglio modello: creane uno o rendine uno attivo."))
    slots = {slot.label: slot for slot in template.slots}
    purchases = []
    for line in portfolio_models.rebalance(template, "new", Decimal(plan.amount)).lines:
        if line.move <= 0:
            continue
        slot = slots.get(line.label)
        price = Decimal(str(line.via.price)) if line.via is not None and line.via.price else None
        purchases.append(Purchase(line.label, line.move, line.via, slot.isin if slot else None,
                                  slot.ticker if slot else None, price, _units(line.move, price, plan.fractional)))
    return purchases


@dataclass
class Order:
    holding_id: int | None
    label: str
    isin: str | None
    ticker: str | None
    units: Decimal
    price: Decimal


def _holding(order: Order) -> Holding:
    if order.holding_id:
        holding = db.session.get(Holding, order.holding_id)
        if holding is not None:
            return holding
    holding = Holding(name=order.label if not order.ticker else f"{order.label} ({order.ticker})", isin=order.isin,
                      ticker=order.ticker, asset_class="ETF", quantity=0, avg_price=0, opening_quantity=0,
                      opening_price=0)
    db.session.add(holding)
    db.session.flush()
    return holding


def confirm(plan: InvestmentPlan, orders: list[Order], on: date) -> int:
    """Buy what was confirmed (with the broker's commission) and mark the period done."""
    bought = 0
    for order in orders:
        if order.units <= 0 or order.price <= 0:
            continue
        holding = _holding(order)
        fee = broker.commission(plan.account, money.cents(order.units * order.price))
        portfolio_ops.record(holding, portfolio_ops.Operation("buy", on, plan.account, units=order.units,
                                                              price=order.price, fee=fee,
                                                              notes=_("PAC «%(name)s»", name=plan.name)))
        bought += 1
    if not bought:
        raise PlanError(_("Nessun acquisto da confermare: indica quote e prezzo."))
    plan.last_done = period(on)
    return bought
