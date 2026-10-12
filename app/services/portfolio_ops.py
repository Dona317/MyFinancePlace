"""
The operations of a holding (F19): purchases and sales in units, dividends and coupons, commissions and taxes, all
kept as transactions linked to the holding.

A holding starts from its opening position (the units and average price it had before the operations recorded here:
a position already owned, entered by hand) and moves with every purchase and sale, in date order: a purchase adds
units and cost (commission included, as brokers report it), a sale removes units at the average cost. The holding's
quantity and average price are recomputed from scratch after any operation is added, changed or deleted, so they
always agree with the list.

The return of a holding (or of the whole portfolio) is the money-weighted one (XIRR): the yearly rate at which what
went in, what came out and what it is worth today balance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from flask_babel import gettext as _
from sqlalchemy import func

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import broker, display, money, wealth
from app.services.i18n import _l

INCOME_CATEGORY = "Dividendi e cedole"
TAX_CATEGORY = "Tasse e imposte"
KINDS = {"buy": _l("Acquisto"), "sell": _l("Vendita"), "dividend": _l("Dividendo"), "coupon": _l("Cedola"),
         "fee": _l("Commissione"), "tax": _l("Imposta")}


# ── Operations ─────────────────────────────────────────────────────────────────

def trades(holding: Holding) -> list[Transaction]:
    """Its purchases and sales in units, oldest first."""
    return (Transaction.query.filter(Transaction.holding_id == holding.id, Transaction.units.isnot(None),
                                     Transaction.unit_price.isnot(None))
            .order_by(Transaction.date, Transaction.id).all())


def operations(holding: Holding) -> list[Transaction]:
    """Everything linked to it (trades, dividends, coupons, commissions of its trades, taxes), newest first."""
    trade_ids = db.session.query(Transaction.id).filter(Transaction.holding_id == holding.id)
    return (Transaction.query.filter((Transaction.holding_id == holding.id) | (Transaction.fee_for_id.in_(trade_ids)))
            .order_by(Transaction.date.desc(), Transaction.id.desc()).all())


def kind_of(tx: Transaction) -> str:
    if tx.units is not None:
        return "buy" if tx.units > 0 else "sell"
    if tx.fee_for_id is not None or tx.category == broker.FEE_CATEGORY:
        return "fee"
    if tx.type == "income":
        return "coupon" if "cedol" in (tx.description or "").lower() else "dividend"
    return "tax"


def _fees_by_trade(trade_ids: list[int]) -> dict[int, Decimal]:
    if not trade_ids:
        return {}
    rows = (db.session.query(Transaction.fee_for_id, func.sum(Transaction.amount))
            .filter(Transaction.fee_for_id.in_(trade_ids)).group_by(Transaction.fee_for_id))
    return {trade_id: Decimal(total) for trade_id, total in rows}


def recompute(holding: Holding) -> None:
    """Quantity and average price from the opening position and the trades, in date order."""
    if holding.opening_quantity is None:  # a holding from before F19 (or a restored backup): set it first
        opening_from_now(holding)
    quantity = Decimal(holding.opening_quantity or 0)
    cost = quantity * Decimal(holding.opening_price if holding.opening_price is not None else holding.avg_price or 0)
    found = trades(holding)
    fees = _fees_by_trade([t.id for t in found])
    for trade in found:
        units, price = Decimal(trade.units), Decimal(trade.unit_price)
        if units > 0:
            cost += units * price + fees.get(trade.id, Decimal(0))
            quantity += units
        elif quantity > 0:
            sold = min(-units, quantity)
            cost -= cost / quantity * sold
            quantity -= sold
    holding.quantity = quantity
    if quantity > 0:
        holding.avg_price = money.price(cost / quantity)


def ensure_opening(holding_id: int | None) -> None:
    """Before a new trade is added: a holding without an opening position (created before F19, or in code) gets one
    from what it holds now, which does not include the new trade yet."""
    holding = db.session.get(Holding, holding_id) if holding_id else None
    if holding is not None and holding.opening_quantity is None:
        with db.session.no_autoflush:
            opening_from_now(holding)


def holdings_of(transaction_ids) -> set[int]:
    """The holdings that transactions move: their own, and the one of the trade a commission belongs to."""
    ids = list(transaction_ids)
    if not ids:
        return set()
    own = db.session.query(Transaction.holding_id).filter(Transaction.id.in_(ids), Transaction.holding_id.isnot(None))
    trade = db.aliased(Transaction)
    of_fees = (db.session.query(trade.holding_id).join(Transaction, Transaction.fee_for_id == trade.id)
               .filter(Transaction.id.in_(ids), trade.holding_id.isnot(None)))
    return {i for (i,) in own} | {i for (i,) in of_fees}


def recompute_ids(holding_ids) -> None:
    """After transactions were edited or deleted: the holdings they were (or are now) linked to."""
    for holding_id in {i for i in holding_ids if i}:
        holding = db.session.get(Holding, holding_id)
        if holding is not None:
            recompute(holding)


@dataclass
class Operation:
    kind: str
    on: date
    account: Account | None
    units: Decimal | None = None
    price: Decimal | None = None
    amount: Decimal | None = None      # dividend, coupon, fee, tax: the money (net, in euro)
    fee: Decimal | None = None         # the broker's commission of a purchase or sale
    notes: str | None = None


def _description(holding: Holding, op: Operation) -> str:
    label = str(KINDS[op.kind])
    if op.units is not None:
        return f"{label} {display.plain(op.units)} {holding.name}"
    return f"{label} {holding.name}"


def record(holding: Holding, op: Operation) -> list[Transaction]:
    """Save an operation as transactions (the trade and its commission, or the income / expense) and move the
    holding."""
    if op.kind not in KINDS:
        raise ValueError(_("Tipo di operazione sconosciuto."))
    ensure_opening(holding.id)
    if op.kind in ("buy", "sell"):
        if not op.units or op.units <= 0 or not op.price or op.price <= 0:
            raise ValueError(_("Indica quote e prezzo per quota, entrambi maggiori di zero."))
        if op.kind == "sell" and op.units > Decimal(holding.quantity or 0):
            raise ValueError(_("Non puoi vendere più quote di quelle che hai (%(units)s).",
                               units=display.plain(holding.quantity)))
        units = op.units if op.kind == "buy" else -op.units
        account_id = op.account.id if op.account else None
        trade = Transaction(date=op.on, description=_description(holding, op), amount=money.cents(op.units * op.price),
                            currency="EUR", type="transfer", category="Investimenti", holding_id=holding.id,
                            units=units, unit_price=op.price, notes=op.notes, tags=[],
                            account_id=account_id if units > 0 else None,
                            counter_account_id=account_id if units < 0 else None)
        created = [trade]
        if op.fee:
            if op.fee < 0:
                raise ValueError(_("La commissione non può essere negativa."))
            created.append(broker.fee_transaction(trade, op.fee, op.account))
        db.session.add_all(created)
        db.session.flush()
        wealth.record_price(holding, op.price, op.on)
    else:
        if not op.amount or op.amount <= 0:
            raise ValueError(_("Indica l'importo, maggiore di zero."))
        income = op.kind in ("dividend", "coupon")
        category = INCOME_CATEGORY if income else (broker.FEE_CATEGORY if op.kind == "fee" else TAX_CATEGORY)
        created = [Transaction(date=op.on, description=_description(holding, op), amount=money.cents(op.amount),
                               currency="EUR", type="income" if income else "expense", category=category,
                               holding_id=holding.id, notes=op.notes, tags=[],
                               account_id=op.account.id if op.account else None)]
        db.session.add_all(created)
        db.session.flush()
    recompute(holding)
    return created


# ── Returns ────────────────────────────────────────────────────────────────────

def xirr(flows: list[tuple[date, float]]) -> float | None:
    """The yearly rate that brings the dated flows (negative = money in, positive = money out) to zero; None when it
    cannot be told (fewer than two flows, all of one sign, or no solution)."""
    flows = [(d, a) for d, a in flows if a]
    if len(flows) < 2 or all(a > 0 for _d, a in flows) or all(a < 0 for _d, a in flows):
        return None
    start = min(d for d, _a in flows)
    years = [((d - start).days / 365.0, a) for d, a in flows]

    def value(rate: float) -> float:
        return sum(a / (1 + rate) ** t for t, a in years)

    low, high = -0.9999, 10.0
    if value(low) * value(high) > 0:
        return None
    for _step in range(200):  # bisection: slow but never lost
        middle = (low + high) / 2
        if value(low) * value(middle) <= 0:
            high = middle
        else:
            low = middle
        if high - low < 1e-9:
            break
    return round((low + high) / 2 * 100, 2)


def _flows(holdings: list[Holding], today: date) -> list[tuple[date, float]]:
    ids = [h.id for h in holdings]
    if not ids:
        return []
    flows = []
    for h in holdings:
        if h.opening_quantity and (h.opening_date or h.purchase_date):
            flows.append((h.opening_date or h.purchase_date, -float(h.opening_quantity) * float(h.opening_price or 0)))
    linked = Transaction.query.filter(Transaction.holding_id.in_(ids)).all()
    fees = _fees_by_trade([t.id for t in linked if t.units is not None])
    for tx in linked:
        amount = float(tx.amount)
        if tx.units is not None:
            fee = float(fees.get(tx.id, 0))
            flows.append((tx.date, -(amount + fee) if tx.units > 0 else amount - fee))
        elif tx.type == "income":
            flows.append((tx.date, amount))
        elif tx.type == "expense":
            flows.append((tx.date, -amount))
    worth = sum(h.value for h in holdings)
    if worth:
        flows.append((today, worth))
    return flows


def performance(holdings: list[Holding], today: date | None = None) -> dict:
    """Unrealized and realized gain, income received and the money-weighted yearly return."""
    from app.services import capital_gains

    today = today or date.today()
    ids = {h.id for h in holdings}
    sales, _containers = capital_gains.realized()
    income = (db.session.query(func.coalesce(func.sum(Transaction.amount), 0))
              .filter(Transaction.holding_id.in_(ids or {0}), Transaction.type == "income").scalar())
    costs = (db.session.query(func.coalesce(func.sum(Transaction.amount), 0))
             .filter(Transaction.holding_id.in_(ids or {0}), Transaction.type == "expense",
                     Transaction.units.is_(None)).scalar())
    return {
        "unrealized": round(sum(h.gain for h in holdings), 2),
        "realized": round(float(sum((s.result for s in sales if s.holding.id in ids), Decimal(0))), 2),
        "income": round(float(income), 2),
        "costs": round(float(costs), 2),
        "xirr": xirr(_flows(holdings, today)),
    }


def opening_from_now(holding: Holding) -> None:
    """For a holding created before F19: its opening position is what it holds minus the trades recorded since."""
    recorded = sum((Decimal(t.units) for t in trades(holding)), Decimal(0))
    holding.opening_quantity = max(Decimal(holding.quantity or 0) - recorded, Decimal(0))
    holding.opening_price = holding.avg_price
    holding.opening_date = holding.purchase_date
