"""
Theoretical orders: what a rebalancing (or a PAC instalment) says to buy and sell, saved before going to the broker
and kept until the user says they were executed.

While they wait, nothing moves: the real positions stay as they are, and the page of the theoretical orders shows
what they would become — units, average buying price (ABP), liquidity of each money account. That liquidity is an
estimate **gross of commissions**: the orders' gross amounts only, since the broker's costs are known afterwards.

At the confirmation the user gives, for each order, the units and price actually executed, and the commissions in
one of three ways:
- one for each order (as before);
- one total, split over the executed orders in proportion to their amount;
- the liquidity actually left on each money account after the orders: the commissions are what is missing from the
  estimate (estimated liquidity − actual liquidity), split in the same way. 319 € expected and 300 € on the account
  means 19 € of commissions.
The executed orders become the holdings' operations (services.portfolio_ops), with their commission; the ones not
ticked stay theoretical.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal

from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.planned_order import PlannedOrder
from app.models.portfolio_model import InvestmentPlan
from app.models.securities import Portfolio, SecuritiesAccount
from app.models.wealth import Holding
from app.services import accounts, money, portfolio_ops, securities

CENT = Decimal("0.01")
FEE_MODES = ("each", "total", "cash")


class PlannedError(ValueError):
    """The orders cannot be saved or confirmed as they are; the message is shown to the user."""


# ── Saving ─────────────────────────────────────────────────────────────────────

@dataclass
class Draft:
    holding: Holding
    side: str
    units: Decimal
    price: Decimal
    label: str = ""


def _place(draft: Draft, dossier: SecuritiesAccount | None, folio: Portfolio | None, account: Account | None):
    """Where an order will be executed: the choices made, else — a sale — where most of the units are, — a purchase —
    where the holding already sits; the money moves on that securities account's liquidity."""
    if dossier is None or (draft.side == "sell" and folio is None):
        held = sorted((p for p in securities.positions([draft.holding]) if p.quantity > 0), key=lambda p: -p.quantity)
        if draft.side == "sell" and held:
            if dossier is None and held[0].securities_account_id:
                dossier = db.session.get(SecuritiesAccount, held[0].securities_account_id)
            if folio is None and held[0].portfolio_id:
                folio = db.session.get(Portfolio, held[0].portfolio_id)
        elif dossier is None:
            dossier = securities.main_place(draft.holding)
    if account is None and dossier is not None:
        account = dossier.settlement_account
    return account, dossier, folio


def save(drafts: list[Draft], source: str = "rebalance", account: Account | None = None,
         dossier: SecuritiesAccount | None = None, folio: Portfolio | None = None,
         plan: InvestmentPlan | None = None, notes: str | None = None) -> str:
    """Keep the orders as theoretical ones; the batch they were saved in."""
    batch = uuid.uuid4().hex
    saved = 0
    for draft in drafts:
        if draft.units is None or draft.units <= 0 or draft.price is None or draft.price <= 0:
            continue
        where, place, portfolio = _place(draft, dossier, folio, account)
        db.session.add(PlannedOrder(batch=batch, source=source, label=draft.label or None, holding_id=draft.holding.id,
                                    side=draft.side, units=draft.units, price=draft.price,
                                    account_id=where.id if where else None,
                                    securities_account_id=place.id if place else None,
                                    portfolio_id=portfolio.id if portfolio else None,
                                    plan_id=plan.id if plan else None, notes=notes))
        saved += 1
    if not saved:
        raise PlannedError(_("Nessun ordine da salvare: indica quote e prezzo."))
    db.session.flush()
    return batch


def discard(batch: str) -> int:
    return PlannedOrder.query.filter_by(batch=batch).delete()


# ── What they would become ─────────────────────────────────────────────────────

def gross(order) -> Decimal:
    return money.cents(Decimal(order.units) * Decimal(order.price))


@dataclass
class Batch:
    batch: str
    orders: list[PlannedOrder]

    @property
    def created_at(self):
        return min(o.created_at for o in self.orders)

    @property
    def source(self) -> str:
        return self.orders[0].source

    @property
    def bought(self) -> Decimal:
        return sum((gross(o) for o in self.orders if o.side == "buy"), Decimal(0))

    @property
    def sold(self) -> Decimal:
        return sum((gross(o) for o in self.orders if o.side == "sell"), Decimal(0))


def batches() -> list[Batch]:
    grouped: dict[str, list[PlannedOrder]] = defaultdict(list)
    for order in PlannedOrder.query.order_by(PlannedOrder.created_at, PlannedOrder.id):
        grouped[order.batch].append(order)
    return sorted((Batch(key, orders) for key, orders in grouped.items()), key=lambda b: b.created_at)


def count() -> int:
    return PlannedOrder.query.count()


@dataclass
class Theoretical:
    holding: Holding
    units_now: Decimal
    abp_now: Decimal
    change: Decimal = Decimal(0)          # + bought, − sold
    units_bought: Decimal = Decimal(0)
    cost_bought: Decimal = Decimal(0)     # gross of commissions: they are not known yet

    @property
    def units(self) -> Decimal:
        return self.units_now + self.change

    @property
    def abp(self) -> Decimal:
        """The average buying price after the orders: purchases move it, sales take units at the average."""
        held = self.units_now + self.units_bought
        if not self.units_bought or not held:
            return self.abp_now
        return ((self.units_now * self.abp_now + self.cost_bought) / held).quantize(Decimal("0.000001"))

    @property
    def value(self) -> Decimal:
        return money.cents(self.units * Decimal(str(self.holding.price)))


def positions(orders: list[PlannedOrder]) -> list[Theoretical]:
    """Each holding the orders touch: units and ABP now and after them (purchases first, as a broker settles)."""
    found: dict[int, Theoretical] = {}
    for order in orders:
        h = order.holding
        row = found.setdefault(h.id, Theoretical(h, Decimal(h.quantity or 0), Decimal(h.avg_price or 0)))
        units = Decimal(order.units)
        if order.side == "buy":
            row.change += units
            row.units_bought += units
            row.cost_bought += units * Decimal(order.price)
        else:
            row.change -= units
    return sorted(found.values(), key=lambda r: r.holding.name)


@dataclass
class Cash:
    account: Account | None
    now: Decimal
    bought: Decimal = Decimal(0)
    sold: Decimal = Decimal(0)
    orders: list = field(default_factory=list)

    @property
    def expected(self) -> Decimal:
        """The liquidity after the orders, gross of commissions (and of the tax on a sale's gain)."""
        return self.now - self.bought + self.sold


def cash(orders, on: date | None = None, executed: dict[int, tuple[Decimal, Decimal]] | None = None) -> list[Cash]:
    """The liquidity of each money account before and after the orders; `executed` (order id → units, price)
    replaces the planned figures with the executed ones."""
    found: dict[int | None, Cash] = {}
    for order in orders:
        account = order.account
        key = account.id if account is not None else None
        if key not in found:
            found[key] = Cash(account, money.cents(Decimal(str(accounts.balance(account, on)))) if account else Decimal(0))
        units, price = (executed or {}).get(order.id, (order.units, order.price))
        amount = money.cents(Decimal(units) * Decimal(price))
        row = found[key]
        if order.side == "buy":
            row.bought += amount
        else:
            row.sold += amount
        row.orders.append(order)
    return list(found.values())


# ── Executed ───────────────────────────────────────────────────────────────────

def split(total: Decimal, amounts: list[Decimal]) -> list[Decimal]:
    """`total` in cents over the amounts, in proportion; the cents left over go to the biggest."""
    total = money.cents(total)
    weight = sum(amounts, Decimal(0))
    if not amounts:
        return []
    if not weight:
        parts = [Decimal(0)] * len(amounts)
        parts[0] = total
        return parts
    parts = [(total * a / weight).quantize(CENT, rounding=ROUND_DOWN) for a in amounts]
    parts[amounts.index(max(amounts))] += total - sum(parts, Decimal(0))
    return parts


@dataclass
class Execution:
    order: PlannedOrder
    units: Decimal
    price: Decimal
    fee: Decimal | None = None   # mode «each»: the order's own commission


@dataclass
class Result:
    recorded: int
    fees: Decimal
    by_account: dict = field(default_factory=dict)   # account name → commissions found from its liquidity


def commissions(executed: list[Execution], mode: str, total: Decimal | None = None,
                actual: dict[int | None, Decimal] | None = None, on: date | None = None) -> tuple[list[Decimal], dict]:
    """The commission of each executed order, in the chosen mode; and, mode «cash», the commissions found on each
    money account."""
    if mode not in FEE_MODES:
        raise PlannedError(_("Scegli come indicare le commissioni."))
    amounts = [money.cents(e.units * e.price) for e in executed]
    if mode == "each":
        fees = [e.fee or Decimal(0) for e in executed]
        if any(f < 0 for f in fees):
            raise PlannedError(_("La commissione non può essere negativa."))
        return fees, {}
    if mode == "total":
        if total is None or total < 0:
            raise PlannedError(_("Indica le commissioni totali (zero se non ce ne sono)."))
        return split(total, amounts), {}
    fees = [Decimal(0)] * len(executed)
    found = {}
    index = {id(e): i for i, e in enumerate(executed)}
    by_account: dict[int | None, list[Execution]] = defaultdict(list)
    for e in executed:
        by_account[e.order.account_id].append(e)
    for account_id, group in by_account.items():
        if account_id is None:
            raise PlannedError(_("Un ordine non ha un conto di liquidità: indica le commissioni a mano."))
        if actual is None or actual.get(account_id) is None:
            raise PlannedError(_("Indica la liquidità che hai ora su ogni conto degli ordini."))
        row = cash([e.order for e in group], on, {e.order.id: (e.units, e.price) for e in group})[0]
        missing = row.expected - money.cents(actual[account_id])
        if missing < 0:
            raise PlannedError(_("Su «%(account)s» hai %(diff)s € in più di quanto atteso: controlla quote e prezzi "
                                 "eseguiti, o indica le commissioni a mano.", account=row.account.name,
                                 diff=f"{-missing:.2f}".replace(".", ",")))
        found[row.account.name] = missing
        for e, fee in zip(group, split(missing, [money.cents(e.units * e.price) for e in group])):
            fees[index[id(e)]] = fee
    return fees, found


def confirm(batch: str, executed: list[Execution], on: date, mode: str = "each", total: Decimal | None = None,
            actual: dict[int | None, Decimal] | None = None) -> Result:
    """The executed orders become operations, with their commission; the others stay theoretical."""
    executed = [e for e in executed if e.order.batch == batch and e.units and e.units > 0 and e.price and e.price > 0]
    if not executed:
        raise PlannedError(_("Nessun ordine eseguito: spunta quelli fatti e indica quote e prezzo."))
    if on > date.today():
        raise PlannedError(_("La data non può essere nel futuro."))
    fees, found = commissions(executed, mode, total, actual, on)
    plans = set()
    for e, fee in zip(executed, fees):
        order = e.order
        name = order.plan.name if order.plan is not None else None
        note = _("PAC «%(name)s»", name=name) if name else (order.notes or _("Ordine del ribilanciamento"))
        portfolio_ops.record(order.holding, portfolio_ops.Operation(
            order.side, on, order.account, units=e.units, price=e.price, fee=fee or None, notes=note,
            securities_account=order.securities_account, portfolio=order.portfolio,
            exact_place=order.securities_account is None and order.account is None))
        if order.plan is not None:
            plans.add(order.plan)
        db.session.delete(order)
    for plan in plans:
        plan.last_done = f"{on:%Y-%m}"
    db.session.flush()
    return Result(len(executed), sum(fees, Decimal(0)), found)
