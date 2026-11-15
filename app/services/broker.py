"""
Investment trades entered in units, and the broker's commission (F17).

Each broker (an account) can have its commission rule: a fixed part plus a percent of the traded amount, kept within
a minimum and a maximum. A trade entered as units × price gets its commission computed from the rule and, once the
user confirms it, saved as a separate expense ("Commissioni") linked to the trade; the holding's quantity and
average purchase price follow the trade (services.portfolio_ops: the commission is part of the cost of a purchase, as
brokers report it).
Without a rule, or without the confirmation, everything stays manual as before.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.models.account import Account
from app.models.transaction import Transaction
from app.services.money import CENT

FEE_CATEGORY = "Commissioni"


def rule_of(account):
    """F96: where the commission rule of trades paid from an account lives — its securities account, the one place
    it is set; the account itself only for a rule entered before, when it has no securities account with a rule.
    A securities account passed in is its own rule."""
    from flask import has_app_context

    if not isinstance(account, Account) or account.id is None or not has_app_context():
        return account
    from app.services import securities  # here: securities imports this module's neighbours

    dossier = securities.dossier_of(account)
    return dossier if dossier is not None and (dossier.has_fee_rule or not account.has_fee_rule) else account


def commission(account: Account | None, gross: Decimal) -> Decimal | None:
    """The commission of a trade of `gross` euro on this broker; None without a rule."""
    account = rule_of(account)
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
    found = {a.id: rule_of(a) for a in accounts}
    return {aid: {"fixed": float(r.fee_fixed or 0), "percent": float(r.fee_percent or 0),
                  "min": float(r.fee_min) if r.fee_min is not None else None,
                  "max": float(r.fee_max) if r.fee_max is not None else None}
            for aid, r in found.items() if r is not None and r.has_fee_rule}


def fee_transaction(trade: Transaction, fee: Decimal, account: Account | None) -> Transaction:
    """The commission of a trade as its own expense, on the same account and day."""
    broker = account.name if account else ""
    return Transaction(date=trade.date, description=f"Commissione {broker}: {trade.description}".replace("  ", " "),
                       amount=fee, currency="EUR", type="expense", category=FEE_CATEGORY, counterparty=broker or None,
                       tags=[t for t in (broker, "commissione") if t], account_id=account.id if account else None,
                       fee_for=trade)
