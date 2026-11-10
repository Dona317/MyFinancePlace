"""
The order register (F46): every operation of every holding in one list — purchases and sales with their price and
commission, dividends, coupons, standalone commissions and taxes — filtered by portfolio, securities account,
holding, kind and period, with the totals and a CSV.

A trade's commission is a transaction of its own (fee_for_id); here it is shown on the trade's row, not twice.
"""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import portfolio_ops


@dataclass
class Row:
    tx: Transaction
    kind: str
    fee: Decimal = Decimal(0)
    holding: Holding | None = None

    @property
    def gross(self) -> Decimal:
        return abs(Decimal(self.tx.amount or 0))


@dataclass
class Register:
    rows: list[Row]
    totals: dict = field(default_factory=dict)


@dataclass
class Filters:
    portfolio_id: int | None = None
    securities_account_id: int | None = None
    holding_id: int | None = None
    kind: str | None = None
    start: date | None = None
    end: date | None = None


def register(filters: Filters | None = None) -> Register:
    filters = filters or Filters()
    query = Transaction.query.filter(Transaction.holding_id.isnot(None))
    if filters.portfolio_id:
        query = query.filter(Transaction.portfolio_id == filters.portfolio_id)
    if filters.securities_account_id:
        query = query.filter(Transaction.securities_account_id == filters.securities_account_id)
    if filters.holding_id:
        query = query.filter(Transaction.holding_id == filters.holding_id)
    if filters.start:
        query = query.filter(Transaction.date >= filters.start)
    if filters.end:
        query = query.filter(Transaction.date <= filters.end)
    found = query.order_by(Transaction.date.desc(), Transaction.id.desc()).all()
    trade_ids = [t.id for t in found if t.units is not None]
    fees = defaultdict(Decimal)
    if trade_ids:
        rows = (db.session.query(Transaction.fee_for_id, db.func.sum(Transaction.amount))
                .filter(Transaction.fee_for_id.in_(trade_ids)).group_by(Transaction.fee_for_id))
        for trade_id, total in rows:
            fees[trade_id] = Decimal(total)
    holdings = {h.id: h for h in Holding.query.filter(Holding.id.in_({t.holding_id for t in found} or {0}))}
    rows = [Row(t, portfolio_ops.kind_of(t), fees.get(t.id, Decimal(0)), holdings.get(t.holding_id)) for t in found]
    if filters.kind:
        rows = [r for r in rows if r.kind == filters.kind]
    totals = {kind: Decimal(0) for kind in portfolio_ops.KINDS}
    commissions = Decimal(0)
    for row in rows:
        totals[row.kind] += row.gross
        commissions += row.fee if row.kind in ("buy", "sell") else (row.gross if row.kind == "fee" else 0)
    totals["commissions"] = commissions
    return Register(rows, totals)


def to_csv(found: Register, names: dict[str, dict[int, str]]) -> str:
    """The register as a CSV (semicolon-separated, decimal comma: opens in Excel as Italian numbers)."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(["Data", "Operazione", "Titolo", "ISIN", "Conto titoli", "Portafoglio", "Quote", "Prezzo",
                     "Importo", "Commissione", "Conto", "Note"])

    def number(value) -> str:
        return "" if value is None else str(value).replace(".", ",")

    for row in found.rows:
        tx = row.tx
        holding = row.holding
        writer.writerow([tx.date.isoformat(), str(portfolio_ops.KINDS[row.kind]), holding.name if holding else "",
                         holding.isin or "" if holding else "", names["dossiers"].get(tx.securities_account_id, ""),
                         names["portfolios"].get(tx.portfolio_id, ""),
                         number(abs(tx.units)) if tx.units is not None else "", number(tx.unit_price),
                         number(row.gross), number(row.fee) if row.fee else "",
                         (tx.account or tx.counter_account).name if (tx.account or tx.counter_account) else "",
                         tx.notes or ""])
    return out.getvalue()
