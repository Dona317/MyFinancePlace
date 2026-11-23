"""
The past prices of the portfolio, collected by themselves (23 Nov 2026, F110): a «filler» that reads the daily closes
of the instruments held — and only those — into the market data store (market_data), from the first operation on
each, and fills the holes it finds; and the ECB exchange rates of the currencies in use, so the closes of
instruments not quoted in euro count too.

    holdings quoted on an exchange (ETF, shares, funds, bonds), with a ticker — or an ISIN, its ticker looked up
        └─▶ the range wanted: from the first operation (a month before) to today
              └─▶ what is missing in the store: everything (first time), the start, the holes of 3+ trading days,
                  the last week (late corrections)
                    └─▶ each piece read from Yahoo, else from Stooq (a Milan listing: its Xetra twin, in euro),
                        else from justETF by the ISIN (the one of the link pasted, history_links)

Only the tickers are sent (and the ISIN to justETF). It runs with «Prezzi da internet» on: once a day in the background (on the first visit
to the dashboard or the portfolio), or from the «Riempi i buchi» button.
"""
from __future__ import annotations

import csv
import io
import threading
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from flask import current_app
from sqlalchemy import func

from app.extensions import db
from app.models.account import Account
from app.models.currency import ExchangeRate
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import currency, market_data, price_feed, settings_store, studio
from app.services.ui_settings import current_settings

STOOQ_DAILY = "https://stooq.com/q/d/l/?s={symbol}&d1={start}&d2={end}&i=d"
ECB_HISTORY = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
MIN_GAP = 3                  # trading days missing in a row that make a hole (shorter: a holiday)
BEFORE_FIRST = timedelta(days=31)
DEFAULT_YEARS = 1            # a holding with no operation dated: its last year
LAST_RUN = "history_filler.last_run"
TIMEOUT = 25
CLASSES = ("ETF", "Azione", "Fondo comune", "Obbligazione")


@dataclass
class Target:
    symbol: str
    isin: str | None
    name: str
    start: date
    holding_ids: list[int] = field(default_factory=list)


@dataclass
class Filled:
    symbol: str
    name: str = ""
    added: int = 0
    pieces: int = 0          # ranges read
    holes: int = 0           # holes still there after
    sources: list[str] = field(default_factory=list)
    error: str | None = None


# ── What to read ───────────────────────────────────────────────────────────────

def _first_operation() -> dict[int, date]:
    rows = (db.session.query(Transaction.holding_id, func.min(Transaction.date))
            .filter(Transaction.holding_id.isnot(None)).group_by(Transaction.holding_id).all())
    return {hid: day for hid, day in rows}


def targets(today: date | None = None, errors: list | None = None, resolve: bool = True) -> list[Target]:
    """The instruments held to read: by ticker (one with only its ISIN gets its ticker looked up and saved), from
    the first operation on it (or its purchase date) a month before; one instrument held twice read once."""
    today = today or date.today()
    first = _first_operation()
    found: dict[str, Target] = {}
    for holding in Holding.query.filter(Holding.asset_class.in_(CLASSES)).order_by(Holding.id):
        if not holding.ticker and holding.isin and resolve:
            try:
                price_feed._resolve_ticker(holding)
                db.session.commit()
            except (OSError, ValueError) as exc:
                if errors is not None:
                    errors.append(Filled(holding.isin, holding.name, error=str(exc)[:200]))
                continue
        if not holding.ticker:
            continue
        symbol = holding.ticker.strip().upper()
        began = min(d for d in (first.get(holding.id), holding.purchase_date, holding.opening_date) if d) \
            if any((first.get(holding.id), holding.purchase_date, holding.opening_date)) \
            else today.replace(year=today.year - DEFAULT_YEARS)
        start = max(began - BEFORE_FIRST, market_data.FIRST_DAY)
        target = found.setdefault(symbol, Target(symbol, holding.isin, holding.name, start))
        target.start = min(target.start, start)
        target.holding_ids.append(holding.id)
    return list(found.values())


# ── Holes ──────────────────────────────────────────────────────────────────────

def trading_days(start: date, end: date) -> list[date]:
    """Monday to Friday between two days (holidays are told apart by MIN_GAP)."""
    days, day = [], start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def missing(have: set[date], start: date, end: date, min_gap: int = MIN_GAP) -> list[tuple[date, date]]:
    """The ranges to read: runs of at least `min_gap` trading days without a close; the start and the end of the
    range count whatever their length (nothing before the first close, or after the last)."""
    if not have:
        return [(start, end)] if start <= end else []
    days = trading_days(start, end)
    runs, current = [], []
    for day in days:
        if day in have:
            if current:
                runs.append(current)
                current = []
        else:
            current.append(day)
    if current:
        runs.append(current)
    first, last = min(have), max(have)
    keep = []
    for run in runs:
        at_start, at_end = run[-1] < first, run[0] > last
        if len(run) >= min_gap or at_start or at_end:
            keep.append((run[0], run[-1]))
    return keep


def holes(have: set[date], start: date, end: date) -> int:
    """The holes inside what is stored (not the days before the first close or after the last)."""
    if not have:
        return 0
    first, last = min(have), max(have)
    return sum(1 for a, b in missing(have, max(start, first), min(end, last)))


# ── Sources ────────────────────────────────────────────────────────────────────

def _text(address: str) -> str:
    request = urllib.request.Request(address, headers={"User-Agent": "Mozilla/5.0 MyFinancePlace"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - fixed https endpoints
        return response.read().decode("utf-8-sig", errors="replace")


def stooq_symbol(symbol: str) -> tuple[str, str]:
    """The Stooq symbol of a Yahoo one and its currency; a Milan listing (not on Stooq) reads its Xetra twin, which
    quotes the same instrument in euro."""
    base, _dot, suffix = symbol.strip().upper().partition(".")
    if suffix == "MI":
        return f"{base.lower()}.de", "EUR"
    return price_feed._stooq_symbol(symbol)


def parse_stooq(text: str, code: str) -> market_data.Daily:
    rows = list(csv.DictReader(io.StringIO(text)))
    points = {}
    for row in rows:
        try:
            day, close = date.fromisoformat((row.get("Date") or "").strip()), Decimal((row.get("Close") or "").strip())
        except (ValueError, InvalidOperation):
            continue
        if close > 0:
            points[day] = (day, close, None)
    if not points:
        raise ValueError("Stooq: nessuna chiusura")
    return market_data.Daily(code, "Stooq", None, [points[d] for d in sorted(points)])


def read_stooq(symbol: str, start: date, end: date) -> market_data.Daily:
    stooq, code = stooq_symbol(symbol)
    return parse_stooq(_text(STOOQ_DAILY.format(symbol=urllib.parse.quote(stooq), start=start.strftime("%Y%m%d"),
                                                end=end.strftime("%Y%m%d"))), code)


SOURCES = (("yahoo", market_data.read_yahoo), ("stooq", read_stooq))


def fill(target: Target, today: date | None = None, sources=None) -> Filled:
    """Read what the store misses of one instrument, piece by piece, from the first source that answers."""
    from app.services import history_links

    today = today or date.today()
    sources = sources or (*SOURCES, *history_links.sources_for(target))
    result = Filled(target.symbol, target.name)
    have = set(market_data.days(target.symbol))
    wanted = missing(have, target.start, today)
    if have:  # the last week again: late corrections
        tail = max(max(have) - market_data.OVERLAP, target.start)
        wanted = [w for w in wanted if w[0] < tail] + [(tail, today)]
    errors = []
    for start, end in wanted:
        for name, reader in sources:
            try:
                daily = reader(target.symbol, start, end)
            except Exception as exc:  # noqa: BLE001 - no network, unknown symbol, an odd answer: the next source
                errors.append(f"{name}: {str(exc)[:80]}")
                continue
            if daily.points:
                result.added += market_data.store(target.symbol, daily, target.isin, target.name, source=name)
                if name not in result.sources:
                    result.sources.append(name)
                break
        result.pieces += 1
    after = set(market_data.days(target.symbol))
    result.holes = holes(after, target.start, today)
    if not after and errors:
        result.error = "; ".join(errors[-2:])
        market_data.remember_error(target.symbol, result.error, target.isin, target.name)
    return result


def coverage(today: date | None = None) -> list[dict]:
    """For the Prices page, without going on the internet: each instrument held, the range wanted, what is stored
    (first and last close, how many), the holes inside it, the sources and the last error."""
    today = today or date.today()
    rows = {row["symbol"]: row for row in market_data.overview()} if market_data.available() else {}
    out = []
    for target in targets(today, resolve=False):
        have = set(market_data.days(target.symbol)) if target.symbol in rows else set()
        wanted_days = len(trading_days(target.start, today))
        inside = len([d for d in have if d >= target.start])
        row = rows.get(target.symbol) or {}
        out.append({"symbol": target.symbol, "name": target.name, "start": target.start,
                    "first": min(have) if have else None, "last": max(have) if have else None, "count": len(have),
                    "share": round(min(inside / wanted_days, 1) * 100) if wanted_days else 0,
                    "holes": holes(have, target.start, today), "sources": market_data.sources_of(target.symbol) if have else [],
                    "currency": row.get("currency"), "error": row.get("error")})
    return out


# ── Exchange rates (ECB) ───────────────────────────────────────────────────────

def currencies_in_use() -> set[str]:
    """The currencies other than the euro the archive uses: accounts, transactions, holdings and their closes."""
    codes = {c for (c,) in db.session.query(Account.currency).distinct()}
    codes |= {c for (c,) in db.session.query(Transaction.currency).distinct()}
    codes |= {c for (c,) in db.session.query(Holding.currency).distinct()}
    held = {t.upper() for (t,) in db.session.query(Holding.ticker).filter(Holding.ticker.isnot(None))}
    if held and market_data.available():
        codes |= {row["currency"] for row in market_data.overview() if row["symbol"] in held}
    codes = {market_data.plain_currency(c) for c in codes if c}
    return {c for c in codes if c and c != "EUR" and c in currency.CURRENCIES}


def parse_ecb_history(raw: bytes, wanted: set[str], since: date) -> list[tuple[date, str, Decimal]]:
    """The ECB's whole history (a zip with one CSV: Date, USD, JPY…, units per euro) → (day, currency, euro value
    of one unit) for the currencies wanted, from a day."""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        text = archive.read(archive.namelist()[0]).decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    header = [cell.strip() for cell in next(reader)]
    columns = {code: i for i, code in enumerate(header) if code in wanted}
    rates = []
    for row in reader:
        try:
            day = date.fromisoformat(row[0].strip())
        except (ValueError, IndexError):
            continue
        if day < since:
            continue
        for code, i in columns.items():
            try:
                per_euro = Decimal(row[i].strip())
            except (InvalidOperation, IndexError):
                continue
            if per_euro > 0:
                rates.append((day, code, (Decimal(1) / per_euro).quantize(Decimal("0.00000001"))))
    return rates


def fill_rates(today: date | None = None, fetch=None) -> dict:
    """The ECB rates of the currencies in use: the whole history needed once (from the first day they are used),
    then the last 90 days. Rates typed by hand are kept. {"currencies", "added"}."""
    today = today or date.today()
    wanted = currencies_in_use()
    if not wanted:
        return {"currencies": [], "added": 0}
    oldest = {code: day for code, day in db.session.query(ExchangeRate.currency, func.min(ExchangeRate.on))
              .filter(ExchangeRate.source == "ecb").group_by(ExchangeRate.currency)}
    first_tx = db.session.query(func.min(Transaction.date)).scalar() or today
    first_op = min(_first_operation().values(), default=today)
    since = max(min(first_tx, first_op) - timedelta(days=7), date(1999, 1, 4))
    needs_history = any(code not in oldest or oldest[code] > since + timedelta(days=7) for code in wanted)
    added = 0
    if needs_history:
        raw = (fetch or _bytes)(ECB_HISTORY)
        rates = parse_ecb_history(raw, wanted, since)
        existing = {(r.currency, r.on): r for r in ExchangeRate.query.filter(
            ExchangeRate.currency.in_(wanted), ExchangeRate.on >= since)}
        for day, code, rate in rates:
            row = existing.get((code, day))
            if row is None:
                db.session.add(ExchangeRate(currency=code, on=day, rate=rate, source="ecb"))
                added += 1
            elif row.source == "ecb":
                row.rate = rate
        db.session.commit()
        currency.recompute()
    else:
        added = currency.download_ecb(history=True)
    return {"currencies": sorted(wanted), "added": added}


def _bytes(address: str) -> bytes:
    request = urllib.request.Request(address, headers={"User-Agent": "Mozilla/5.0 MyFinancePlace"})
    with urllib.request.urlopen(request, timeout=TIMEOUT * 2) as response:  # noqa: S310 - the ECB's fixed file
        return response.read()


# ── Running ────────────────────────────────────────────────────────────────────

@dataclass
class Run:
    filled: list[Filled]
    rates: dict | None = None
    rates_error: str | None = None


def run(today: date | None = None, sources=None, fetch=None, progress=None) -> Run:
    """Every instrument held, then the exchange rates; `progress(done, total, what)` told at each step."""
    today = today or date.today()
    tell = progress or (lambda done, total, what: None)
    tell(0, 0, "database di partenza")
    try:
        market_data.seed_if_empty()  # F114: an empty store starts from the one shipped with the app
    except (OSError, ValueError):
        pass
    errors: list[Filled] = []
    wanted = targets(today, errors)
    total = len(wanted) + 1  # the instruments, then the rates
    found = []
    for done, target in enumerate(wanted):
        tell(done, total, target.symbol)
        found.append(fill(target, today, sources))
    found += errors
    tell(len(wanted), total, "BCE")
    rates, rates_error = None, None
    try:
        rates = fill_rates(today, fetch)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        db.session.rollback()
        rates_error = str(exc)[:200]
    tell(total, total, "")
    return Run(found, rates, rates_error)


# ── The state of a run, for the pill at the bottom of the page (like the AI classification) ──

_status: dict = {}


def _key():
    client = studio.current()
    return client.id if client is not None else None


def status() -> dict | None:
    """The run of this archive: {"id", "state": "running" | "done", "done", "total", "what", "summary"}; None when
    none ran since the app started."""
    return _status.get(_key())


def _set(key, **values) -> None:
    with _lock:
        _status[key] = {**_status.get(key, {}), **values}


def _summary(result: Run) -> dict:
    good = [f for f in result.filled if not f.error]
    return {"instruments": len(good), "closes": sum(f.added for f in good), "holes": sum(f.holes for f in good),
            "errors": [f"{f.symbol}: {f.error[:60]}" for f in result.filled if f.error][:5],
            "rates": (result.rates or {}).get("added", 0), "currencies": (result.rates or {}).get("currencies", []),
            "rates_error": result.rates_error}


def due(today: date | None = None) -> bool:
    today = today or date.today()
    return bool(current_settings()["prices_online"]) and settings_store.get(LAST_RUN) != today.isoformat()


_lock = threading.Lock()
_running: set = set()


def run_in_background(force: bool = False) -> bool:
    """Once a day on a page visit (or now, `force`: «Riempi i buchi ora»): the filling in a thread, so the page does
    not wait for the internet; its progress in status(). False when one is already running."""
    if not force and not due():
        return False
    settings_store.set(LAST_RUN, date.today().isoformat())  # first: a second visit meanwhile does not start it again
    db.session.commit()
    client = studio.current()
    key = client.id if client is not None else None
    with _lock:
        if key in _running:
            return False
        _running.add(key)
    _set(key, id=f"{date.today().isoformat()}-{len(_status)}-{threading.get_ident()}", state="running", done=0,
         total=0, what="", summary=None)
    if current_app.config.get("PRICES_SYNC"):
        _work(key)
        return True
    app = current_app._get_current_object()
    threading.Thread(target=_thread, args=(app, client, key), daemon=True, name="history-filler").start()
    return True


def _work(key) -> None:
    try:
        result = run(progress=lambda done, total, what: _set(key, done=done, total=total, what=what))
        _set(key, state="done", summary=_summary(result))
    finally:
        with _lock:
            _running.discard(key)


def _thread(app, client, key) -> None:
    try:
        with app.app_context():
            studio.activate(client)
            _work(key)
    except Exception:  # noqa: BLE001 - a background job never breaks the app; the next day tries again
        _set(key, state="done", summary={"instruments": 0, "closes": 0, "holes": 0, "errors": ["errore imprevisto"],
                                          "rates": 0, "currencies": [], "rates_error": None})
        with app.app_context():
            app.logger.exception("history filler failed")
    finally:
        with _lock:
            _running.discard(key)
