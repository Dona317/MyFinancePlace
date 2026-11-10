"""
Investment performance (F20): how the investments did, independent of when money went in.

- time-weighted return (TWR): month by month (Modified Dietz within the month), chained — what the holdings earned,
  whatever the size and timing of the purchases; next to it the money-weighted return (XIRR, portfolio_ops)
- volatility (yearly, from the monthly returns), worst fall from a peak (maximum drawdown), best and worst month
- up to three benchmarks (tickers such as VWCE.MI, their monthly prices kept in the settings) over the same months
  (F59), and how far the portfolio is from its all-time high
- risk (F58): Sharpe and Sortino ratios against a risk-free rate (a setting), downside deviation, how long the
  falls lasted, the best and worst 12 months
- contribution (F58): what each holding added to the result of a period, in euro and in percentage points

Values at past dates use the units held then (today's minus the trades since) and the price recorded by then.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func

from app.extensions import db
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import broker, periods, settings_store, wealth
from app.services.i18n import _l
from app.services.net_worth_growth import units_after
from app.services.totals import VALUE

BENCHMARK_KEY = "performance.benchmark"     # before F59: one benchmark, {"ticker", "prices", "updated"}
BENCHMARKS_KEY = "performance.benchmarks"   # F59: a list of them
MAX_BENCHMARKS = 3
RISK_FREE_KEY = "performance.risk_free"     # F58: yearly %, for the Sharpe and Sortino ratios
DEFAULT_RISK_FREE = 2.0
MAX_MONTHS = 120
PERIODS = {"all": _l("Dall'inizio"), "ytd": _l("Da inizio anno"), "12": _l("Ultimi 12 mesi"),
           "36": _l("Ultimi 3 anni")}
WINDOWS = (("1A", 12), ("3A", 36), ("5A", 60))


@dataclass
class Report:
    labels: list[str] = field(default_factory=list)
    returns: list[float] = field(default_factory=list)      # monthly, in %
    cumulative: list[float] = field(default_factory=list)   # % since the first month
    benchmark: list[float | None] = field(default_factory=list)  # the first benchmark (as before F59)
    twr: float | None = None
    annualized: float | None = None
    volatility: float | None = None
    max_drawdown: float | None = None
    best: tuple[str, float] | None = None
    worst: tuple[str, float] | None = None
    benchmark_twr: float | None = None
    windows: dict = field(default_factory=dict)              # {"1A": (portfolio %, first benchmark %)}
    heatmap: dict = field(default_factory=dict)              # F49: {2025: [12 monthly returns in % or None]}
    drawdowns: list[float] = field(default_factory=list)     # F49: % below the previous peak, month by month
    # F58: risk
    risk_free: float = DEFAULT_RISK_FREE                     # yearly %
    sharpe: float | None = None
    sortino: float | None = None
    downside: float | None = None                            # downside deviation, yearly %
    drawdown_months: int | None = None                       # the longest fall, from the peak to the recovery
    drawdown_recovered: bool = True                          # … and whether it is over
    underwater_months: int = 0                               # months below the peak now (0 = at the peak)
    best_12: tuple[str, float] | None = None                 # (last month of the 12, %)
    worst_12: tuple[str, float] | None = None
    # F59
    from_peak: float | None = None                           # % below the all-time high now
    benchmarks: list[dict] = field(default_factory=list)     # [{"ticker", "updated", "series", "twr", "windows"}]
    periods: list[tuple] = field(default_factory=list)       # [(label, portfolio %, [benchmark % …])]


def _held_value(h: Holding, on: date, prices: dict[int, float], later: dict[int, float]) -> float:
    """The value of the units a holding had on a date (today's less the trades since) at the price recorded by then
    (none: today's). A holding sold out since then still counts for what it held."""
    if h.purchase_date is not None and h.purchase_date > on:
        return 0.0
    units = (float(h.quantity or 0) - later.get(h.id, 0.0)) * float(h.multiplier if h.multiplier is not None else 1)
    price = h.price if on >= date.today() else prices.get(h.id, h.price)
    return units * price


def _value(holdings: list[Holding], on: date) -> float:
    prices = wealth.prices_on(on) if on < date.today() else {}
    later = units_after(on)
    return sum(_held_value(h, on, prices, later) for h in holdings)


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


def _traded(ids: set[int]) -> set[int]:
    return {hid for (hid,) in db.session.query(Transaction.holding_id).filter(
        Transaction.holding_id.in_(ids or {0}), Transaction.units.isnot(None)).distinct()}


def monthly_returns(holdings: list[Holding], today: date | None = None) -> tuple[list[date], list[float]]:
    today = today or date.today()
    first = _first_date(holdings)
    if first is None or first >= today:
        return [], []
    ends = _ends(first, today)
    ids = {h.id for h in holdings}
    traded = _traded(ids)
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


# ── Risk (F58) ─────────────────────────────────────────────────────────────────

def risk_free() -> float:
    """The yearly risk-free rate in % (a setting; 2 % when unset or unreadable)."""
    try:
        return float(settings_store.get(RISK_FREE_KEY) or DEFAULT_RISK_FREE)
    except ValueError:
        return DEFAULT_RISK_FREE


def save_risk_free(rate: float) -> None:
    if not -10 <= rate <= 50:
        raise ValueError(rate)
    settings_store.set(RISK_FREE_KEY, str(rate))


def monthly_rate(yearly_pct: float) -> float:
    """A yearly rate in % as the monthly rate that compounds to it."""
    return (1 + yearly_pct / 100) ** (1 / 12) - 1


def sharpe(returns: list[float], rf_month: float) -> float | None:
    """(mean monthly return − monthly risk-free rate) / standard deviation of the monthly returns, × √12."""
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    sd = math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1))
    return (mean - rf_month) / sd * math.sqrt(12) if sd > 1e-12 else None


def downside_deviation(returns: list[float], rf_month: float) -> float | None:
    """Monthly: √(Σ min(0, r − risk-free)² / n) — only the months below the risk-free rate weigh."""
    if not returns:
        return None
    return math.sqrt(sum(min(0.0, r - rf_month) ** 2 for r in returns) / len(returns))


def sortino(returns: list[float], rf_month: float) -> float | None:
    """(mean monthly return − monthly risk-free rate) / downside deviation, × √12."""
    if len(returns) < 2:
        return None
    down = downside_deviation(returns, rf_month)
    mean = sum(returns) / len(returns)
    return (mean - rf_month) / down * math.sqrt(12) if down and down > 1e-12 else None


def drawdown_spells(returns: list[float]) -> list[tuple[int, int | None]]:
    """The falls below a peak: (month of the peak, month it was first reached again, or None while it lasts), where
    month 0 is the start and month i the end of the i-th return."""
    spells, level, peak, peak_at, below = [], 1.0, 1.0, 0, False
    for i, r in enumerate(returns, start=1):
        level *= 1 + r
        if level >= peak - 1e-12:
            if below:
                spells.append((peak_at, i))
            peak, peak_at, below = max(peak, level), i, False
        else:
            below = True
    if below:
        spells.append((peak_at, None))
    return spells


def rolling_12(returns: list[float]) -> list[tuple[int, float]]:
    """(index of the last month, chained return) of every run of 12 consecutive months."""
    return [(i - 1, _chain(returns[i - 12:i])) for i in range(12, len(returns) + 1)]


def _risk(result: Report, returns: list[float]) -> None:
    rf = monthly_rate(result.risk_free)
    ratio = sharpe(returns, rf)
    result.sharpe = round(ratio, 2) if ratio is not None else None
    ratio = sortino(returns, rf)
    result.sortino = round(ratio, 2) if ratio is not None else None
    down = downside_deviation(returns, rf)
    result.downside = round(down * math.sqrt(12) * 100, 2) if down is not None else None
    spells = drawdown_spells(returns)
    if spells:
        lengths = [((end if end is not None else len(returns)) - start, end is not None) for start, end in spells]
        result.drawdown_months, result.drawdown_recovered = max(lengths, key=lambda x: x[0])
        result.underwater_months = len(returns) - spells[-1][0] if spells[-1][1] is None else 0
    windows = rolling_12(returns)
    if windows:
        best, worst = max(windows, key=lambda w: w[1]), min(windows, key=lambda w: w[1])
        result.best_12 = (result.labels[best[0]], round(best[1] * 100, 2))
        result.worst_12 = (result.labels[worst[0]], round(worst[1] * 100, 2))


# ── Benchmarks (F20, F59) ──────────────────────────────────────────────────────

def benchmarks() -> list[dict]:
    """The benchmarks, [{"ticker", "prices", "updated"}]; before F59 there was one, under the old key."""
    stored = settings_store.get_json(BENCHMARKS_KEY, None, expect=list)
    if stored is None:
        old = settings_store.get_json(BENCHMARK_KEY, {}, expect=dict)
        stored = [old] if old.get("ticker") else []
    return [b for b in stored if isinstance(b, dict) and b.get("ticker")][:MAX_BENCHMARKS]


def save_benchmarks(items: list[dict]) -> None:
    settings_store.set_json(BENCHMARKS_KEY, items[:MAX_BENCHMARKS])
    if settings_store.get(BENCHMARK_KEY) is not None:
        settings_store.set(BENCHMARK_KEY, None)  # moved into the list


def benchmark_settings() -> dict:
    """The first benchmark (the only one before F59)."""
    found = benchmarks()
    return found[0] if found else {}


def can_add_benchmark(ticker: str) -> bool:
    found = benchmarks()
    return any(b["ticker"] == ticker for b in found) or len(found) < MAX_BENCHMARKS


def save_benchmark(ticker: str, prices: dict[str, float], updated: date) -> None:
    """Add a benchmark, or refresh it when already there; an empty ticker removes them all."""
    if not ticker:
        save_benchmarks([])
        return
    found = benchmarks()
    entry = {"ticker": ticker, "prices": prices, "updated": updated.isoformat()}
    for i, b in enumerate(found):
        if b["ticker"] == ticker:
            found[i] = entry
            break
    else:
        if len(found) >= MAX_BENCHMARKS:
            raise ValueError(ticker)
        found.append(entry)
    save_benchmarks(found)


def remove_benchmark(ticker: str) -> None:
    save_benchmarks([b for b in benchmarks() if b["ticker"] != ticker])


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


def _benchmark_line(b: dict, dates: list[date], returns: list[float]) -> dict:
    prices = b.get("prices") or {}
    series: list[float | None] = [None] * len(dates)
    start_price = _benchmark_on(prices, periods.first_of_month(dates[0]) - timedelta(days=1)) if prices else None
    if start_price:
        series = [round((p / start_price - 1) * 100, 2) if (p := _benchmark_on(prices, d)) else None for d in dates]
    windows = {}
    for label, months in WINDOWS:
        theirs = None
        if len(returns) >= months and prices:
            begin = _benchmark_on(prices, dates[-months] - timedelta(days=31))
            end = _benchmark_on(prices, dates[-1])
            theirs = round((end / begin - 1) * 100, 2) if begin and end else None
        windows[label] = theirs
    return {"ticker": b["ticker"], "updated": b.get("updated"), "series": series,
            "twr": series[-1] if start_price else None, "windows": windows}


def report(holdings: list[Holding], today: date | None = None) -> Report:
    today = today or date.today()
    dates, returns = monthly_returns(holdings, today)
    result = Report(risk_free=risk_free())
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

    for d, r in zip(dates, result.returns):  # the year × month table (the last point can be today: its month)
        result.heatmap.setdefault(d.year, [None] * 12)[d.month - 1] = r
    peak = 1.0
    for c in cumulative:
        peak = max(peak, 1 + c)
        result.drawdowns.append(round(((1 + c) / peak - 1) * 100, 2))
    result.from_peak = result.drawdowns[-1]
    _risk(result, returns)

    result.benchmarks = [_benchmark_line(b, dates, returns) for b in benchmarks()]
    first = result.benchmarks[0] if result.benchmarks else None
    result.benchmark = first["series"] if first else [None] * len(dates)
    result.benchmark_twr = first["twr"] if first else None
    for label, months in WINDOWS:
        mine = _window(dates, returns, months)
        theirs = [b["windows"][label] if mine is not None else None for b in result.benchmarks]
        result.windows[label] = (mine, theirs[0] if theirs else None)
        result.periods.append((label, mine, theirs))
    return result


# ── Contribution of each holding (F58) ─────────────────────────────────────────

@dataclass
class Contribution:
    holding: Holding
    start_value: float = 0.0
    end_value: float = 0.0
    put: float = 0.0        # purchases − sales in the period (a holding entered without trades: at its value)
    income: float = 0.0     # dividends, coupons
    fees: float = 0.0       # the commissions of its trades and its own
    taxes: float = 0.0
    points: float | None = None  # percentage points of the period's return

    @property
    def gain(self) -> float:
        """Realized and unrealized: the change in value less the money put in."""
        return self.end_value - self.start_value - self.put

    @property
    def total(self) -> float:
        return self.gain + self.income - self.fees - self.taxes


def period_start(period: str, ends: list[date], today: date) -> date:
    """The day before the period: a month end the TWR starts from, at most back to the first one."""
    if period == "ytd":
        return max(date(today.year, 1, 1) - timedelta(days=1), ends[0])
    if period in ("12", "36"):
        months = int(period)
        return ends[-months - 1] if len(ends) > months else ends[0]
    return ends[0]


def _by_holding(query) -> dict[int, float]:
    return {hid: float(total or 0) for hid, total in query}


def _prices_and_units(on: date) -> tuple[dict[int, float], dict[int, float]]:
    return (wealth.prices_on(on) if on < date.today() else {}), units_after(on)


def contributions(holdings: list[Holding], period: str = "all", today: date | None = None) -> dict:
    """What each holding added to the result in (start, today]: gain (end value − start value − purchases + sales,
    so realized and unrealized) + income − fees − taxes, in euro and in percentage points of the money invested on
    average (Modified Dietz: the start value plus the flows weighted by the part of the period they stayed in).
    The contributions add up to the portfolio's result; their points to its simple return over the period."""
    today = today or date.today()
    period = period if period in PERIODS else "all"
    first = _first_date(holdings)
    result = {"rows": [], "period": period, "start": None, "capital": 0.0, "total": 0.0, "points": None,
              "fees": 0.0, "taxes": 0.0}
    if first is None or first >= today:
        return result
    ends = _ends(first, today)
    start, end = period_start(period, ends, today), today
    days = (end - start).days or 1
    ids = {h.id for h in holdings}
    rows = {h.id: Contribution(h) for h in holdings}
    p0, l0 = _prices_and_units(start)
    p1, l1 = _prices_and_units(end)
    for h in holdings:
        rows[h.id].start_value = _held_value(h, start, p0, l0)
        rows[h.id].end_value = _held_value(h, end, p1, l1)

    in_period = (Transaction.date > start, Transaction.date <= end)
    weighted: dict[int, float] = defaultdict(float)
    trades = db.session.query(Transaction.holding_id, Transaction.date, func.sign(Transaction.units) * VALUE).filter(
        Transaction.holding_id.in_(ids or {0}), Transaction.units.isnot(None), *in_period)
    for hid, day, amount in trades:
        rows[hid].put += float(amount or 0)
        weighted[hid] += float(amount or 0) * (end - day).days / days
    traded = _traded(ids)
    for h in holdings:  # entered without trades: as in the TWR, money put in at its value at that month's end
        if h.id not in traded and h.purchase_date and start < h.purchase_date <= end:
            on = next(e for e in ends if e >= h.purchase_date)
            rows[h.id].put += _held_value(h, on, *_prices_and_units(on))
            weighted[h.id] += rows[h.id].put / 2

    own = (Transaction.holding_id.in_(ids or {0}), Transaction.units.is_(None), *in_period)
    fee = Transaction.category == broker.FEE_CATEGORY
    by = Transaction.holding_id
    sums = {
        "income": db.session.query(by, func.sum(VALUE)).filter(Transaction.type == "income", *own).group_by(by),
        "fees": db.session.query(by, func.sum(VALUE)).filter(Transaction.type == "expense", fee, *own).group_by(by),
        "taxes": db.session.query(by, func.sum(VALUE)).filter(
            Transaction.type == "expense", ~fee | Transaction.category.is_(None), *own).group_by(by),
    }
    trade = db.aliased(Transaction)
    commissions = (db.session.query(trade.holding_id, func.sum(VALUE)).join(trade, Transaction.fee_for_id == trade.id)
                   .filter(trade.holding_id.in_(ids or {0}), *in_period).group_by(trade.holding_id))
    for kind, query in [*sums.items(), ("fees", commissions)]:
        for hid, value in _by_holding(query).items():
            setattr(rows[hid], kind, getattr(rows[hid], kind) + value)

    capital = sum(r.start_value for r in rows.values()) + sum(weighted.values())
    found = [r for r in rows.values() if r.start_value or r.end_value or r.put or r.income or r.fees or r.taxes]
    for r in found:
        r.points = round(r.total / capital * 100, 2) if capital > 0 else None
    found.sort(key=lambda r: -r.total)
    total = sum(r.total for r in found)
    result.update(rows=found, start=start, capital=round(capital, 2), total=round(total, 2),
                  points=round(total / capital * 100, 2) if capital > 0 else None,
                  fees=round(sum(r.fees for r in found), 2), taxes=round(sum(r.taxes for r in found), 2))
    return result


def contribution_of(holding: Holding, holdings: list[Holding], period: str = "all",
                    today: date | None = None) -> Contribution | None:
    """The contribution of one holding to the portfolio it belongs to (the holding page)."""
    if holding not in holdings:
        return None
    return next((r for r in contributions(holdings, period, today)["rows"] if r.holding.id == holding.id), None)


# ── Value against money put in (F47, F49) ──────────────────────────────────────

def _invested(holdings: list[Holding], on: date) -> float:
    """Money put into the holdings up to a date: their opening positions at cost, purchases (commissions in) minus
    what the sales brought back. Holdings without trades count at cost from their purchase date."""
    ids = [h.id for h in holdings]
    total = 0.0
    for h in holdings:
        opened = h.opening_date or h.purchase_date
        if opened is None or opened <= on:
            quantity = h.opening_quantity if h.opening_quantity is not None else h.quantity
            price = h.opening_price if h.opening_price is not None else h.avg_price
            total += float(quantity or 0) * float(price or 0) * float(h.multiplier or 1)
    trades = db.session.query(func.sum(func.sign(Transaction.units) * VALUE)).filter(
        Transaction.holding_id.in_(ids or [0]), Transaction.units.isnot(None), Transaction.date <= on).scalar()
    trade_ids = db.session.query(Transaction.id).filter(Transaction.holding_id.in_(ids or [0]),
                                                        Transaction.units.isnot(None), Transaction.date <= on)
    fees = db.session.query(func.sum(VALUE)).filter(Transaction.fee_for_id.in_(trade_ids)).scalar()
    return total + float(trades or 0) + float(fees or 0)


def value_series(holdings: list[Holding], today: date | None = None) -> dict:
    """Month-end value of the holdings at the prices recorded by then, and the money put in by then (G37): the chart
    the portfolio page shows instead of the snapshots."""
    today = today or date.today()
    first = _first_date(holdings)
    if first is None or first >= today:
        return {"labels": [], "value": [], "invested": []}
    ends = _ends(first, today)
    return {"labels": [d.strftime("%m/%y") for d in ends],
            "value": [round(_value(holdings, d), 2) for d in ends],
            "invested": [round(_invested(holdings, d), 2) for d in ends]}
