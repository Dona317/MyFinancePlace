"""
Investment performance (F20): how the investments did, independent of when money went in.

- time-weighted return (TWR): month by month (Modified Dietz within the month), chained — what the holdings earned,
  whatever the size and timing of the purchases; next to it the money-weighted return (XIRR, portfolio_ops)
- volatility (yearly, from the monthly returns), worst fall from a peak (maximum drawdown), best and worst month
- a benchmark (a ticker such as VWCE.MI, its monthly prices kept in the settings) over the same months

Values at past dates use the units held then (today's minus the trades since) and the price recorded by then.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func

from app.extensions import db
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import periods, settings_store, wealth
from app.services.net_worth_growth import units_after
from app.services.totals import VALUE

BENCHMARK_KEY = "performance.benchmark"
MAX_MONTHS = 120


@dataclass
class Report:
    labels: list[str] = field(default_factory=list)
    returns: list[float] = field(default_factory=list)      # monthly, in %
    cumulative: list[float] = field(default_factory=list)   # % since the first month
    benchmark: list[float | None] = field(default_factory=list)
    twr: float | None = None
    annualized: float | None = None
    volatility: float | None = None
    max_drawdown: float | None = None
    best: tuple[str, float] | None = None
    worst: tuple[str, float] | None = None
    benchmark_twr: float | None = None
    windows: dict = field(default_factory=dict)              # {"1A": (portfolio %, benchmark %)}


def _value(holdings: list[Holding], on: date) -> float:
    prices = wealth.prices_on(on) if on < date.today() else {}
    later = units_after(on)
    total = 0.0
    held = {h.id for h in wealth.holdings_on(on)}
    for h in holdings:
        if h.id not in held:
            continue
        now = float(h.quantity or 0)
        share = (now - later.get(h.id, 0.0)) / now if now else 0.0
        total += wealth.value_on(h, on, prices) * share
    return total


def _flows(ids: set[int], start: date, end: date) -> tuple[float, float, float]:
    """Money put in (purchases − sales), the same weighted by the part of the period it stayed invested (Modified
    Dietz), and the income received (dividends, coupons), in (start, end]."""
    if not ids:
        return 0.0, 0.0, 0.0
    period = (Transaction.holding_id.in_(ids), Transaction.date > start, Transaction.date <= end)
    rows = db.session.query(Transaction.date, func.sign(Transaction.units) * VALUE).filter(
        Transaction.units.isnot(None), *period).all()
    days = (end - start).days or 1
    put = sum(float(v or 0) for _d, v in rows)
    weighted = sum(float(v or 0) * (end - d).days / days for d, v in rows)
    income = db.session.query(func.sum(VALUE)).filter(Transaction.type == "income", *period).scalar()
    return put, weighted, float(income or 0)


def _entered(holdings: list[Holding], start: date, end: date, traded: set[int]) -> float:
    """Holdings that appear in the period without trades (entered with their value): money put in."""
    prices = wealth.prices_on(end) if end < date.today() else {}
    return sum(wealth.value_on(h, end, prices) for h in holdings
               if h.id not in traded and h.purchase_date and start < h.purchase_date <= end)


def _ends(first: date, today: date) -> list[date]:
    ends, day = [], periods.first_of_month(first) - timedelta(days=1)
    while day < today and len(ends) <= MAX_MONTHS:
        ends.append(day)
        day = periods.add_months(day + timedelta(days=1), 1) - timedelta(days=1)
    return ends[-MAX_MONTHS:] + [today]


def _first_date(holdings: list[Holding]) -> date | None:
    ids = [h.id for h in holdings]
    first_trade = db.session.query(func.min(Transaction.date)).filter(
        Transaction.holding_id.in_(ids or [0]), Transaction.units.isnot(None)).scalar()
    dates = [d for d in [first_trade, *(h.purchase_date for h in holdings), *(h.opening_date for h in holdings)] if d]
    return min(dates) if dates else None


def monthly_returns(holdings: list[Holding], today: date | None = None) -> tuple[list[date], list[float]]:
    today = today or date.today()
    first = _first_date(holdings)
    if first is None or first >= today:
        return [], []
    ends = _ends(first, today)
    ids = {h.id for h in holdings}
    traded = {hid for (hid,) in db.session.query(Transaction.holding_id).filter(
        Transaction.holding_id.in_(ids or {0}), Transaction.units.isnot(None)).distinct()}
    values = [_value(holdings, end) for end in ends]
    dates, returns = [], []
    for i in range(1, len(ends)):
        put, weighted, income = _flows(ids, ends[i - 1], ends[i])
        entered = _entered(holdings, ends[i - 1], ends[i], traded)
        put, weighted = put + entered, weighted + entered / 2
        base = values[i - 1] + weighted
        if base <= 0:
            continue
        dates.append(ends[i])
        returns.append((values[i] - values[i - 1] - put + income) / base)
    return dates, returns


def _chain(returns: list[float]) -> float:
    total = 1.0
    for r in returns:
        total *= 1 + r
    return total - 1


def _drawdown(cumulative: list[float]) -> float:
    peak, worst = 1.0, 0.0
    for c in cumulative:
        level = 1 + c
        peak = max(peak, level)
        worst = min(worst, level / peak - 1)
    return worst


def benchmark_settings() -> dict:
    return settings_store.get_json(BENCHMARK_KEY, {}, expect=dict)


def save_benchmark(ticker: str, prices: dict[str, float], updated: date) -> None:
    settings_store.set_json(BENCHMARK_KEY, {"ticker": ticker, "prices": prices, "updated": updated.isoformat()})


def _benchmark_on(prices: dict[str, float], on: date) -> float | None:
    """The benchmark's latest monthly price on or before `on`."""
    best = None
    for day, price in prices.items():
        if day <= on.isoformat() and (best is None or day > best[0]):
            best = (day, price)
    return best[1] if best else None


def _window(dates: list[date], returns: list[float], months: int) -> float | None:
    if len(returns) < months:
        return None
    return round(_chain(returns[-months:]) * 100, 2)


def report(holdings: list[Holding], today: date | None = None) -> Report:
    today = today or date.today()
    dates, returns = monthly_returns(holdings, today)
    result = Report()
    if not returns:
        return result
    cumulative, total = [], 1.0
    for r in returns:
        total *= 1 + r
        cumulative.append(total - 1)
    result.labels = [d.strftime("%m/%y") for d in dates]
    result.returns = [round(r * 100, 2) for r in returns]
    result.cumulative = [round(c * 100, 2) for c in cumulative]
    result.twr = round(cumulative[-1] * 100, 2)
    years = len(returns) / 12
    result.annualized = round(((1 + cumulative[-1]) ** (1 / years) - 1) * 100, 2) if years >= 1 else None
    if len(returns) > 1:
        mean = sum(returns) / len(returns)
        result.volatility = round(math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1) * 12) * 100, 2)
    result.max_drawdown = round(_drawdown(cumulative) * 100, 2)
    best, worst = max(range(len(returns)), key=returns.__getitem__), min(range(len(returns)), key=returns.__getitem__)
    result.best, result.worst = (result.labels[best], result.returns[best]), (result.labels[worst], result.returns[worst])

    prices = benchmark_settings().get("prices") or {}
    bench = [None] * len(dates)
    start_price = _benchmark_on(prices, periods.first_of_month(dates[0]) - timedelta(days=1)) if prices else None
    if start_price:
        bench = [round((p / start_price - 1) * 100, 2) if (p := _benchmark_on(prices, d)) else None for d in dates]
        result.benchmark_twr = bench[-1]
    result.benchmark = bench
    for label, months in (("1A", 12), ("3A", 36), ("5A", 60)):
        mine = _window(dates, returns, months)
        theirs = None
        if mine is not None and prices:
            begin = _benchmark_on(prices, dates[-months] - timedelta(days=31))
            end = _benchmark_on(prices, dates[-1])
            theirs = round((end / begin - 1) * 100, 2) if begin and end else None
        result.windows[label] = (mine, theirs)
    return result
