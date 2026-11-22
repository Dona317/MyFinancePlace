"""
Transazioni → Investimenti (22 Nov 2026): the purchases and sales of securities (and their commissions) have a tab of
their own in Transazioni, out of the ordinary list; a movement of the current account that was one (−5.000 € to the
broker for VWCE) is moved there by saying the security, the units, the price and the commission.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import and_, or_

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import broker, broker_import, money, portfolio_ops

# a trade of a security, or the commission of one: in the Investimenti tab, not in the ordinary list
INVESTMENT = or_(and_(Transaction.holding_id.isnot(None), Transaction.units.isnot(None)),
                 Transaction.fee_for_id.isnot(None))


def ordinary():
    """The condition of the ordinary list of Transazioni: everything but the investment operations."""
    return ~INVESTMENT


def holding_named(name: str) -> Holding:
    """A security of the portfolio by its name, ISIN or ticker; a new one when there is none (its kind guessed)."""
    text = " ".join((name or "").split())
    if not text:
        raise ValueError("name")
    found = Holding.query.filter(or_(Holding.name.ilike(text), Holding.isin == text.upper(),
                                     Holding.ticker.ilike(text))).first()
    if found is not None:
        return found
    isin = text.upper() if broker_import.ISIN.fullmatch(text.upper()) else None
    holding = Holding(name=text[:200], isin=isin, asset_class=broker_import.guess_class(text), quantity=0, avg_price=0,
                      opening_quantity=0, opening_price=0)
    db.session.add(holding)
    db.session.flush()
    return holding


def move(tx: Transaction, holding: Holding, units: Decimal | None, price: Decimal | None,
         fee: Decimal | None = None) -> Transaction:
    """
    The movement becomes an operation of `holding`: money out of the account a purchase, into it a sale. The
    commission is part of the movement (the bank shows one amount): it becomes the trade's own commission and the
    trade keeps the rest. Units or price may be left out: the other one and the amount give it.
    """
    if tx.units is not None and tx.holding_id:
        raise ValueError("already")
    fee = money.cents(abs(fee)) if fee else Decimal(0)
    whole = abs(Decimal(tx.amount or 0))
    selling = tx.type == "income" or (tx.type == "transfer" and tx.account_id is None)
    # a purchase costs the trade plus the commission; a sale brings the trade minus it
    gross = whole + fee if selling else whole - fee
    if gross <= 0:
        raise ValueError("fee")
    units = abs(units) if units else None
    price = abs(price) if price else None
    if units is None and price:
        units = gross / price
    if price is None and units:
        price = gross / units
    if not units or not price:
        raise ValueError("units")
    account_id = tx.account_id or tx.counter_account_id
    account = db.session.get(Account, account_id) if account_id else None
    portfolio_ops.ensure_opening(holding.id)
    tx.holding_id, tx.units, tx.unit_price = holding.id, -units if selling else units, price
    tx.amount = gross
    tx.type, tx.category = "transfer", "Investimenti"
    tx.account_id, tx.counter_account_id = (None, account_id) if selling else (account_id, None)
    tx.splits = []
    if fee:
        db.session.add(broker.fee_transaction(tx, fee, account))
    db.session.flush()
    portfolio_ops.recompute(holding)
    return tx
