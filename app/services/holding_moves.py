"""
The movements of the holdings — trades entered in units, dividends, coupons, the commissions of the trades — read
once per request.

A page that draws a series (the value of the portfolio at each month-end, the money put in by then, the monthly
returns) asks the same questions for dozens of dates: «units bought after this day», «purchases minus sales in this
month». One query per date and question made hundreds of them; the movements of the holdings are few (hundreds, some
thousands), so they are read once and every date is answered from memory. Sums are made on the stored decimals, as
the database made them. What is read is forgotten as soon as the request writes (services.request_cache.data).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import func

from app.extensions import db
from app.models.transaction import Transaction
from app.services import request_cache
from app.services.totals import VALUE

ZERO = Decimal(0)


class Move(NamedTuple):
    id: int
    holding_id: int
    date: date
    type: str | None
    units: Decimal | None   # bought (negative: sold); None for a dividend, a coupon, a tax
    value: Decimal | None   # in the base currency, without sign

    @property
    def signed(self) -> Decimal:
        """A trade's money: put in when buying, taken out (negative) when selling."""
        if self.units is None or self.value is None or not self.units:
            return ZERO
        return self.value if self.units > 0 else -self.value


def moves() -> list[Move]:
    """Every transaction linked to a holding, oldest first."""
    store = request_cache.data()
    if "holding_moves" not in store:
        rows = (db.session.query(Transaction.id, Transaction.holding_id, Transaction.date, Transaction.type,
                                 Transaction.units, VALUE)
                .filter(Transaction.holding_id.isnot(None)).order_by(Transaction.date, Transaction.id))
        store["holding_moves"] = [Move(*row) for row in rows]
    return store["holding_moves"]


def trades() -> list[Move]:
    """The purchases and sales: the movements entered in units."""
    store = request_cache.data()
    if "holding_trades" not in store:
        store["holding_trades"] = [move for move in moves() if move.units is not None]
    return store["holding_trades"]


def fees() -> dict[int, Decimal]:
    """{trade id: the commissions saved as expenses of their own for it (F17)}."""
    store = request_cache.data()
    if "holding_fees" not in store:
        rows = (db.session.query(Transaction.fee_for_id, func.sum(VALUE))
                .filter(Transaction.fee_for_id.isnot(None)).group_by(Transaction.fee_for_id))
        store["holding_fees"] = {trade_id: total for trade_id, total in rows if total is not None}
    return store["holding_fees"]
