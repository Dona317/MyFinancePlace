"""
Capital gains and losses of the trades entered in units (F15): what each sale realized, the losses carried
forward and the tax.

- **Cost**: weighted average cost of the units held, purchase commissions included (as Italian brokers compute
  it); a sale's proceeds are net of its commission. Units held before the first recorded trade count at the
  holding's average price.
- **Kinds**: a gain on an ETF or a fund is a *reddito di capitale* (taxed in full, no offset); a gain on shares,
  bonds or crypto is a *reddito diverso* and is first offset by the losses not yet used. Every loss is a reddito
  diverso, usable until 31 December of the fourth following year. Crypto losses offset only crypto gains.
- **Containers**: under the *regime amministrato* each broker (account) keeps its own losses; under the *regime
  dichiarativo* they all go into the return (quadro RT).
- **Rates**: 26%; 12,5% for government bonds (set on the holding; a loss offsets them for 48,08% of its amount);
  crypto 26% until 2025, 33% from 2026.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import tax_rules

CENT = Decimal("0.01")
DICHIARATIVO = "dichiarativo"


@dataclass
class Sale:
    on: date
    holding: Holding
    account: Account | None
    units: Decimal
    proceeds: Decimal  # net of the sale's commission
    cost: Decimal      # average cost of the units sold, purchase commissions included
    rate: Decimal
    kind: str          # "capitale" | "diversi" | "cripto"
    offset: Decimal = Decimal(0)    # part of the gain cancelled by past losses
    estimated: bool = False         # cost of units held before the first recorded trade
    oversold: bool = False          # more units sold than held

    @property
    def result(self) -> Decimal:
        return self.proceeds - self.cost

    @property
    def taxable(self) -> Decimal:
        return max(self.result - self.offset, Decimal(0))

    @property
    def tax(self) -> Decimal:
        return (self.taxable * self.rate / 100).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class Loss:
    year: int
    amount: Decimal
    left: Decimal
    crypto: bool

    @property
    def expires(self) -> int:
        return self.year + tax_rules.LOSS_YEARS


@dataclass
class Container:
    """A broker under the regime amministrato, or the return (regime dichiarativo)."""
    key: str
    label: str
    regime: str
    losses: list[Loss] = field(default_factory=list)


def _kind(holding: Holding) -> str:
    if holding.asset_class == tax_rules.CRYPTO:
        return "cripto"
    return "capitale" if holding.asset_class in tax_rules.FUND_CLASSES else "diversi"


def _trades() -> list[Transaction]:
    return (Transaction.query.filter(Transaction.holding_id.isnot(None), Transaction.units.isnot(None),
                                     Transaction.unit_price.isnot(None))
            .order_by(Transaction.date, Transaction.id).all())


def _fees() -> dict[int, Decimal]:
    rows = Transaction.query.filter(Transaction.fee_for_id.isnot(None)).all()
    fees: dict[int, Decimal] = defaultdict(Decimal)
    for fee in rows:
        fees[fee.fee_for_id] += abs(Decimal(fee.amount or 0))
    return fees


def _container(account: Account | None, containers: dict[str, Container]) -> Container:
    regime = account.tax_regime if account is not None else "amministrato"
    if regime == DICHIARATIVO:
        key, label = DICHIARATIVO, "Dichiarazione (quadro RT)"
    else:
        key, label = f"account-{account.id if account else 0}", account.name if account else "—"
    return containers.setdefault(key, Container(key, label, regime))


def _offset(sale: Sale, box: Container) -> None:
    """Cancel as much of the sale's gain as the container's losses still allow (oldest first)."""
    weight = tax_rules.GOVERNMENT_BOND_WEIGHT if sale.rate == tax_rules.GOVERNMENT_BOND_RATE else Decimal(1)
    gain = sale.result
    for loss in box.losses:
        if gain <= 0:
            break
        if loss.left <= 0 or loss.expires < sale.on.year or loss.year > sale.on.year or loss.crypto != (sale.kind == "cripto"):
            continue
        cancel = min(gain, loss.left / weight)
        loss.left -= (cancel * weight).quantize(CENT)
        sale.offset += cancel
        gain -= cancel


def realized(until: int | None = None) -> tuple[list[Sale], dict[str, Container]]:
    """Every sale with its result, in order, and the containers with their losses as they stand at the end of
    `until` (or now)."""
    fees, positions, sales, containers = _fees(), {}, [], {}
    trades = _trades()
    holdings = {h.id: h for h in Holding.query.filter(Holding.id.in_({tx.holding_id for tx in trades}))}
    recorded: dict[int, Decimal] = defaultdict(Decimal)
    for tx in trades:
        recorded[tx.holding_id] += Decimal(tx.units)
    for tx in trades:
        holding = holdings.get(tx.holding_id)
        if holding is None or (until is not None and tx.date.year > until):
            continue
        if holding.id not in positions:  # what was held before the first recorded trade
            before = max(Decimal(holding.quantity or 0) - recorded[holding.id], Decimal(0))
            positions[holding.id] = [before, before * Decimal(holding.avg_price or 0), before > 0]
        quantity, cost, estimated = positions[holding.id]
        units, price, fee = Decimal(tx.units), Decimal(tx.unit_price), fees.get(tx.id, Decimal(0))
        account = tx.account if tx.account is not None else tx.counter_account
        if units > 0:
            positions[holding.id] = [quantity + units, cost + units * price + fee, estimated]
            continue
        sold = -units
        oversold = sold > quantity
        average = cost / quantity if quantity else Decimal(0)
        sale_cost = average * min(sold, quantity)
        sale = Sale(tx.date, holding, account, sold, sold * price - fee, sale_cost.quantize(CENT),
                    tax_rules.gain_rate(holding.asset_class, tx.date.year, holding.tax_rate), _kind(holding),
                    estimated=estimated, oversold=oversold)
        positions[holding.id] = [max(quantity - sold, Decimal(0)), cost - sale_cost, estimated]
        box = _container(account, containers)
        if sale.result < 0:
            box.losses.append(Loss(tx.date.year, -sale.result, -sale.result, sale.kind == "cripto"))
        elif sale.kind != "capitale":
            _offset(sale, box)
        sales.append(sale)
    return sales, containers


def year_summary(year: int) -> dict:
    """The year's sales and, per container: gains, losses, offsets, tax, and the losses still usable after it."""
    sales, containers = realized(until=year)
    of_year = [s for s in sales if s.on.year == year]
    boxes = []
    for box in containers.values():
        mine = [s for s in of_year if _container(s.account, containers) is box]
        usable = [loss for loss in box.losses if loss.left > 0 and loss.expires >= year]
        if not mine and not usable:
            continue
        boxes.append({
            "box": box, "sales": mine,
            "gains": sum((s.result for s in mine if s.result > 0), Decimal(0)),
            "losses": sum((-s.result for s in mine if s.result < 0), Decimal(0)),
            "offset": sum((s.offset for s in mine), Decimal(0)),
            "taxable": sum((s.taxable for s in mine), Decimal(0)),
            "tax": sum((s.tax for s in mine), Decimal(0)),
            "proceeds": sum((s.proceeds for s in mine), Decimal(0)),
            "costs": sum((s.cost for s in mine), Decimal(0)),
            "carried": sorted(usable, key=lambda loss: loss.year),
        })
    boxes.sort(key=lambda b: (b["box"].regime == DICHIARATIVO, b["box"].label))
    return {"year": year, "boxes": boxes, "sales": of_year,
            "tax": sum((b["tax"] for b in boxes), Decimal(0)),
            "estimated": any(s.estimated for s in of_year), "oversold": [s for s in of_year if s.oversold]}


def years() -> list[int]:
    """The years with at least one trade, newest first."""
    return sorted({tx.date.year for tx in _trades()}, reverse=True)
