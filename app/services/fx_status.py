"""
Dati → Cambi (23 Nov 2026): the exchange rates the archive needs, and where they are missing.

For each currency in use (accounts, movements, holdings and their quotes — history_filler.currencies_in_use): from
when it is needed (its first movement, or the first operation on an instrument quoted in it), the rates stored (from
the ECB or typed by hand), the holes (3+ working days without a rate inside the range), whether the last rate is old,
and the movements dated before the first rate — those are counted 1:1 in euro (T49), so they are the ones to fix.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func

from app.extensions import db
from app.models.currency import ExchangeRate
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import history_filler, market_data

STALE_DAYS = 5   # a last rate older than this (working days and a weekend) is old


def _needed_from(code: str, today: date) -> date:
    """The first day a currency is used: its first movement, or the first operation on an instrument quoted in it."""
    days = [db.session.query(func.min(Transaction.date)).filter(Transaction.currency == code).scalar()]
    first = history_filler._first_operation()
    quoted = {row["symbol"] for row in market_data.overview()
              if market_data.plain_currency(row["currency"]) == code} if market_data.available() else set()
    for holding in Holding.query.filter(Holding.ticker.isnot(None)):
        if holding.ticker.strip().upper() in quoted or (holding.currency or "").upper() == code:
            days.append(first.get(holding.id) or holding.purchase_date)
    days = [d for d in days if d]
    return min(days) if days else today


def report(today: date | None = None) -> list[dict]:
    """One row per currency in use: {code, needed_from, first, last, count, sources, holes, stale, uncovered,
    status: "ok" | "warning" | "missing"}."""
    today = today or date.today()
    rows = []
    for code in sorted(history_filler.currencies_in_use()):
        rates = db.session.query(ExchangeRate.on, ExchangeRate.source).filter(ExchangeRate.currency == code).all()
        have = {on for on, _source in rates}
        needed = _needed_from(code, today)
        first, last = (min(have), max(have)) if have else (None, None)
        holes = history_filler.missing(have, max(needed, first), min(today, last)) if have else []
        holes = [h for h in holes if first < h[0] and h[1] < last]
        uncovered = (Transaction.query.filter(Transaction.currency == code,
                                              Transaction.date < first if first else Transaction.id.isnot(None)).count())
        stale = bool(last and (today - last).days > STALE_DAYS)
        late_start = bool(first and first > needed + timedelta(days=7))
        status = "missing" if not have or uncovered else ("warning" if holes or stale or late_start else "ok")
        rows.append({"code": code, "needed_from": needed, "first": first, "last": last, "count": len(have),
                     "sources": sorted({source for _on, source in rates}), "holes": holes, "stale": stale,
                     "late_start": late_start, "uncovered": uncovered, "status": status})
    return rows


def problems(today: date | None = None) -> int:
    """How many currencies need a look (for the menu)."""
    return sum(1 for row in report(today) if row["status"] != "ok")
