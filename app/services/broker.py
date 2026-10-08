"""
Investment trades entered in units, and the broker's commission (F17).

Each broker (an account) can have its commission rule: a fixed part plus a percent of the traded amount, kept within
a minimum and a maximum. A trade entered as units × price gets its commission computed from the rule and, once the
user confirms it, saved as a separate expense ("Commissioni") linked to the trade; the holding's quantity and
average purchase price follow the trade (the commission is part of the cost of a purchase, as brokers report it).
Without a rule, or without the confirmation, everything stays manual as before.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import money, wealth
from app.services.money import CENT

FEE_CATEGORY = "Commissioni"


def commission(account: Account | None, gross: Decimal) -> Decimal | None:
    """The commission of a trade of `gross` euro on this broker; None without a rule."""
    if account is None or not account.has_fee_rule:
        return None
    fee = Decimal(account.fee_fixed or 0) + abs(gross) * Decimal(account.fee_percent or 0) / 100
    if account.fee_min is not None:
        fee = max(fee, Decimal(account.fee_min))
    if account.fee_max is not None:
        fee = min(fee, Decimal(account.fee_max))
    return fee.quantize(CENT, rounding=ROUND_HALF_UP)


def rules(accounts: list[Account]) -> dict[int, dict]:
    """The rules of the accounts that have one, for the form's live estimate."""
    return {a.id: {"fixed": float(a.fee_fixed or 0), "percent": float(a.fee_percent or 0),
                   "min": float(a.fee_min) if a.fee_min is not None else None,
                   "max": float(a.fee_max) if a.fee_max is not None else None}
            for a in accounts if a.has_fee_rule}


def apply_trade(holding: Holding, units: Decimal, price: Decimal, fee: Decimal, on) -> None:
    """Move the holding by a trade: a purchase raises the quantity and averages its cost (commission included), a
    sale lowers the quantity and leaves the average price; the trade's price becomes a point of the price history."""
    quantity = Decimal(holding.quantity or 0)
    if units > 0:
        cost = quantity * Decimal(holding.avg_price or 0) + units * price + fee
        holding.quantity = quantity + units
        holding.avg_price = money.price(cost / holding.quantity)
    else:
        holding.quantity = max(quantity + units, Decimal(0))
    wealth.record_price(holding, price, on)


def fee_transaction(trade: Transaction, fee: Decimal, account: Account | None) -> Transaction:
    """The commission of a trade as its own expense, on the same account and day."""
    broker = account.name if account else ""
    return Transaction(date=trade.date, description=f"Commissione {broker}: {trade.description}".replace("  ", " "),
                       amount=fee, currency="EUR", type="expense", category=FEE_CATEGORY, counterparty=broker or None,
                       tags=[t for t in (broker, "commissione") if t], account_id=account.id if account else None,
                       fee_for=trade)
