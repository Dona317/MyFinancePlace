"""
The statements of a year, closed (requested on 2 November 2026): during the year the balance sheet, the income
statement and the cash flow fill up as the transactions come in; on the first visit of the new year the ones of every
past year not closed yet are saved as they are. Afterwards a change to a transaction of a closed year (up to its 31
December: the balance sheet depends on every earlier one too) is noticed — the bell and Contabilità say so — and the
statements can be saved again, as a new version.
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, text

from app.extensions import db
from app.models.transaction import Transaction
from app.models.year_close import YearClose
from app.services import analytics, wealth

# what makes a transaction count in the statements; a change to any of them is a change to the year
FINGERPRINT_SQL = text("""
    SELECT md5(coalesce(string_agg(concat_ws('|', id, date, amount, amount_base, currency, type, category,
                                             account_id, counter_account_id, holding_id, debt_id), ',' ORDER BY id), ''))
    FROM transactions WHERE date <= :end
""")


def _plain(value):
    """The statements as JSON: dates as text, amounts as numbers."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _plain(dataclasses.asdict(value))
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def fingerprint(year: int) -> str:
    return db.session.execute(FINGERPRINT_SQL, {"end": date(year, 12, 31)}).scalar() or ""


def statements(year: int) -> dict:
    return _plain({"balance_sheet": wealth.balance_sheet(date(year, 12, 31)),
                   "income_statement": analytics.income_statement(year),
                   "cash_flow": analytics.cash_flow(year)})


def latest(year: int) -> YearClose | None:
    return YearClose.query.filter_by(year=year).order_by(YearClose.version.desc()).first()


def close(year: int, automatic: bool = False) -> YearClose:
    """Save the statements of `year` as they are now: the first version, or the next one."""
    previous = latest(year)
    row = YearClose(year=year, version=(previous.version + 1) if previous else 1, automatic=automatic,
                    fingerprint=fingerprint(year), data=statements(year))
    db.session.add(row)
    db.session.commit()
    return row


def ensure(today: date | None = None) -> list[YearClose]:
    """From 1 January: every past year with transactions and not closed yet is closed (the statements saved)."""
    today = today or date.today()
    closed = {year for (year,) in db.session.query(YearClose.year).distinct()}
    first = db.session.query(func.min(Transaction.date)).scalar()
    if first is None:
        return []
    return [close(year, automatic=True) for year in range(first.year, today.year) if year not in closed]


def changed() -> list[YearClose]:
    """The last close of each year whose transactions are no longer the ones it was made with."""
    rows = []
    for (year,) in db.session.query(YearClose.year).distinct().order_by(YearClose.year):
        last = latest(year)
        if last.fingerprint != fingerprint(year):
            rows.append(last)
    return rows


def overview() -> list[dict]:
    """Each closed year, newest first: its versions (newest first) and whether its data changed since."""
    stale = {row.year for row in changed()}
    years = [year for (year,) in db.session.query(YearClose.year).distinct().order_by(YearClose.year.desc())]
    return [{"year": year, "changed": year in stale,
             "versions": YearClose.query.filter_by(year=year).order_by(YearClose.version.desc()).all()} for year in years]
