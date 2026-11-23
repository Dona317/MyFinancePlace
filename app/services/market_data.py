"""
The market data store (D10, F69): end-of-day closes of the instruments, in a database of its own — not in an
archive — so they are shared by every archive and client, survive restoring a backup, and stay from one version of
the app to the next.

Where: MARKET_DATABASE_URL when set (a server can point it at its own PostgreSQL database), otherwise a SQLite file
`market.sqlite` in the app's data folder (the instance folder; on the desktop app, the user's data folder). The
schema is created and brought up to date by this module on first use, version by version (`SCHEMA`), so every
version of the app finds it ready; nothing in the archives' migrations touches it.

Tables:
- instruments: a listing by its Yahoo symbol (VWCE.MI), with ISIN, name, the currency it quotes in, first and last
  close stored, when it was last read;
- closes: one row per instrument and trading day — the close in the instrument's currency (not converted: the
  conversion to euro happens when it is used, with the day's rate) and the adjusted close (dividends and splits);
- meta: the schema version.

Reading: Yahoo Finance's public chart endpoint, daily, from a start date (the first time: from 2000 or the first
trading day) and then from the last close stored minus a week (late corrections). Only the symbol is sent. Or a
CSV file of closes (Yahoo's own download, justETF, investing.com, a spreadsheet): date and close columns.

Use (Fase 2): a holding is linked to the store by its ticker (the Yahoo symbol, VWCE.MI) or, failing that, by its
ISIN; the past prices of the archive (`wealth.prices_on`) take the stored close of the day when it is newer than
the last price recorded by hand — only for instruments quoted in euro (ETF, shares, funds), since the closes are
kept in the instrument's currency.
"""
from __future__ import annotations

import bisect
import csv
import io
import json
import os
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from flask import current_app
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    create_engine,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine

ENV = "MARKET_DATABASE_URL"
FILE = "market.sqlite"
YAHOO_DAILY = ("https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={start}&period2={end}"
               "&interval=1d&events=div%2Csplit&includeAdjustedClose=true")
FIRST_DAY = date(2000, 1, 1)
OVERLAP = timedelta(days=7)
TIMEOUT = 20
SCHEMA = 1

# The main funds and ETFs whose history is worth having from the start (Borsa Italiana listings, in euro), and the
# indices used as benchmarks: what «Scarica i fondi principali» reads
MAIN_FUNDS = [
    ("VWCE.MI", "IE00BK5BQT80", "Vanguard FTSE All-World UCITS ETF Acc"),
    ("SWDA.MI", "IE00B4L5Y983", "iShares Core MSCI World UCITS ETF"),
    ("CSSPX.MI", "IE00B5BMR087", "iShares Core S&P 500 UCITS ETF"),
    ("EIMI.MI", "IE00BKM4GZ66", "iShares Core MSCI EM IMI UCITS ETF"),
    ("MEUD.MI", "LU0908500753", "Amundi Core Stoxx Europe 600 UCITS ETF"),
    ("WSML.MI", "IE00BF4RFH31", "iShares MSCI World Small Cap UCITS ETF"),
    ("AGGH.MI", "IE00BDBRDM35", "iShares Core Global Aggregate Bond UCITS ETF EUR Hedged"),
    ("SEGA.MI", "IE00B4WXJJ64", "iShares Core Euro Government Bond UCITS ETF"),
    ("IEAC.MI", "IE00B3F81R35", "iShares Core Euro Corporate Bond UCITS ETF"),
    ("IBGL.MI", "IE00B1FZS913", "iShares Euro Government Bond 15-30yr UCITS ETF"),
    ("IBGM.MI", "IE00B1FZS806", "iShares Euro Government Bond 7-10yr UCITS ETF"),
    ("XEON.MI", "LU0290358497", "Xtrackers II EUR Overnight Rate Swap UCITS ETF"),
    ("SGLD.MI", "IE00B579F325", "Invesco Physical Gold ETC"),
    ("ICOM.MI", "IE00BDFL4P12", "iShares Diversified Commodity Swap UCITS ETF"),
    ("IWDP.MI", "IE00B1FZS350", "iShares Developed Markets Property Yield UCITS ETF"),
    ("V60A.MI", "IE00BMVB5R75", "Vanguard LifeStrategy 60% Equity UCITS ETF"),
    ("V80A.MI", "IE00BMVB5P51", "Vanguard LifeStrategy 80% Equity UCITS ETF"),
    ("^GSPC", None, "S&P 500 (indice)"),
    ("^STOXX50E", None, "Euro Stoxx 50 (indice)"),
    ("FTSEMIB.MI", None, "FTSE MIB (indice)"),
]

metadata = MetaData()
meta_table = Table("meta", metadata, Column("key", String(40), primary_key=True), Column("value", Text))
instruments = Table(
    "instruments", metadata,
    Column("id", Integer, primary_key=True),
    Column("symbol", String(40), nullable=False, unique=True),
    Column("isin", String(12), index=True),
    Column("name", Text),
    Column("currency", String(8)),
    Column("exchange", String(40)),
    Column("first_day", Date),
    Column("last_day", Date),
    Column("synced_at", DateTime),
    Column("error", Text),
)
closes = Table(
    "closes", metadata,
    Column("instrument_id", Integer, ForeignKey("instruments.id", ondelete="CASCADE"), primary_key=True),
    Column("day", Date, primary_key=True),
    Column("close", Numeric(20, 6), nullable=False),
    Column("adj_close", Numeric(20, 6)),
    Column("source", String(20), nullable=False, default="yahoo"),
)

_engines: dict[str, Engine] = {}


def url() -> str:
    configured = os.environ.get(ENV) or current_app.config.get(ENV)
    if configured:
        return configured
    folder = Path(current_app.instance_path)
    folder.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{folder / FILE}"


def engine() -> Engine:
    """The store's engine, made the first time; the schema brought up to date."""
    address = url()
    if address not in _engines:
        made = create_engine(address, future=True)
        _upgrade(made)
        _engines[address] = made
    return _engines[address]


def _upgrade(made: Engine) -> None:
    """Every version of the app opens the store at its schema: create what is missing, then the steps after it."""
    metadata.create_all(made)
    with made.begin() as conn:
        row = conn.execute(select(meta_table.c.value).where(meta_table.c.key == "schema")).first()
        version = int(row[0]) if row else 0
        # future steps go here: `if version < 2: conn.execute(text("ALTER TABLE …"))`
        if version != SCHEMA:
            if row:
                conn.execute(update(meta_table).where(meta_table.c.key == "schema").values(value=str(SCHEMA)))
            else:
                conn.execute(insert(meta_table).values(key="schema", value=str(SCHEMA)))


def schema_version() -> int:
    with engine().connect() as conn:
        return int(conn.execute(select(meta_table.c.value).where(meta_table.c.key == "schema")).scalar_one())


# ── Reading from Yahoo ─────────────────────────────────────────────────────────

def _fetch(address: str) -> dict:
    request = urllib.request.Request(address, headers={"User-Agent": "Mozilla/5.0 MyFinancePlace",
                                                       "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - a fixed https endpoint
        return json.loads(response.read().decode("utf-8"))


def _stamp(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())


@dataclass
class Daily:
    currency: str | None
    exchange: str | None
    name: str | None
    points: list[tuple[date, Decimal, Decimal | None]]   # (day, close, adjusted close)


def parse_chart(data: dict) -> Daily:
    """Yahoo's chart answer → the daily closes (days without a close skipped), in the instrument's currency."""
    results = (data.get("chart") or {}).get("result") or []
    if not results:
        error = ((data.get("chart") or {}).get("error") or {}).get("description")
        raise ValueError(error or "symbol not found")
    result = results[0]
    meta = result.get("meta") or {}
    stamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quote = (indicators.get("quote") or [{}])[0]
    adjusted = ((indicators.get("adjclose") or [{}])[0]).get("adjclose") or [None] * len(stamps)
    offset = timedelta(seconds=meta.get("gmtoffset") or 0)
    points = {}
    for stamp, close, adj in zip(stamps, quote.get("close") or [], adjusted):
        if close is None:
            continue
        day = (datetime.fromtimestamp(stamp, tz=timezone.utc) + offset).date()
        points[day] = (day, Decimal(str(round(close, 6))), Decimal(str(round(adj, 6))) if adj is not None else None)
    return Daily(meta.get("currency"), meta.get("exchangeName"), meta.get("longName") or meta.get("shortName"),
                 [points[d] for d in sorted(points)])


def read_yahoo(symbol: str, start: date, end: date) -> Daily:
    return parse_chart(_fetch(YAHOO_DAILY.format(symbol=urllib.parse.quote(symbol), start=_stamp(start),
                                                 end=_stamp(end + timedelta(days=1)))))


# ── The store ──────────────────────────────────────────────────────────────────

def _instrument(conn, symbol: str, isin: str | None = None, name: str | None = None) -> dict:
    row = conn.execute(select(instruments).where(instruments.c.symbol == symbol)).mappings().first()
    if row is None:
        conn.execute(insert(instruments).values(symbol=symbol, isin=isin, name=name))
        row = conn.execute(select(instruments).where(instruments.c.symbol == symbol)).mappings().first()
    elif (isin and not row["isin"]) or (name and not row["name"]):
        conn.execute(update(instruments).where(instruments.c.id == row["id"])
                     .values(isin=row["isin"] or isin, name=row["name"] or name))
    return dict(row)


def store(symbol: str, daily: Daily, isin: str | None = None, name: str | None = None, source: str = "yahoo") -> int:
    """Save the closes read (a day already there is overwritten: the source may correct it); how many."""
    with engine().begin() as conn:
        row = _instrument(conn, symbol, isin, name or daily.name)
        days = [p[0] for p in daily.points]
        if days:
            conn.execute(closes.delete().where(closes.c.instrument_id == row["id"], closes.c.day.in_(days)))
            conn.execute(insert(closes), [{"instrument_id": row["id"], "day": d, "close": c, "adj_close": a,
                                           "source": source} for d, c, a in daily.points])
        first, last = conn.execute(select(func.min(closes.c.day), func.max(closes.c.day))
                                   .where(closes.c.instrument_id == row["id"])).one()
        conn.execute(update(instruments).where(instruments.c.id == row["id"]).values(
            currency=daily.currency or row["currency"], exchange=daily.exchange or row["exchange"],
            name=row["name"] or daily.name, first_day=first, last_day=last, synced_at=datetime.utcnow(), error=None))
    return len(daily.points)


def days(symbol: str) -> list[date]:
    """The days with a close stored, oldest first."""
    query = (select(closes.c.day).join(instruments, instruments.c.id == closes.c.instrument_id)
             .where(instruments.c.symbol == symbol.strip().upper()).order_by(closes.c.day))
    with engine().connect() as conn:
        return [day for (day,) in conn.execute(query)]


def sources_of(symbol: str) -> list[str]:
    """Where the closes stored of an instrument came from (yahoo, stooq, file), the most used first."""
    query = (select(closes.c.source, func.count()).join(instruments, instruments.c.id == closes.c.instrument_id)
             .where(instruments.c.symbol == symbol.strip().upper()).group_by(closes.c.source)
             .order_by(func.count().desc()))
    with engine().connect() as conn:
        return [source for source, _n in conn.execute(query)]


def plain_currency(code: str | None) -> str | None:
    """A quote currency as an ISO code: London's pence (GBp, GBX) are pounds (the closes are then divided by 100)."""
    if not code:
        return code
    return "GBP" if code in ("GBp", "GBX", "GBx") else code.upper()


def remember_error(symbol: str, message: str, isin: str | None = None, name: str | None = None) -> None:
    _remember_error(symbol, message, isin, name)


def _remember_error(symbol: str, message: str, isin: str | None = None, name: str | None = None) -> None:
    with engine().begin() as conn:
        row = _instrument(conn, symbol, isin, name)
        conn.execute(update(instruments).where(instruments.c.id == row["id"])
                     .values(error=message[:300], synced_at=datetime.utcnow()))


@dataclass
class Sync:
    symbol: str
    added: int = 0
    error: str | None = None


def sync(symbol: str, isin: str | None = None, name: str | None = None, today: date | None = None,
         reader=None) -> Sync:
    """Bring one instrument up to date: everything the first time, then from the last close minus a week."""
    today = today or date.today()
    symbol = symbol.strip().upper()
    with engine().connect() as conn:
        last = conn.execute(select(instruments.c.last_day).where(instruments.c.symbol == symbol)).scalar()
    start = (last - OVERLAP) if last else FIRST_DAY
    try:
        daily = (reader or read_yahoo)(symbol, start, today)
    except Exception as exc:  # no network, symbol unknown, an odd answer: recorded, the others go on
        message = str(exc) or type(exc).__name__
        _remember_error(symbol, message, isin, name)
        return Sync(symbol, error=message)
    return Sync(symbol, store(symbol, daily, isin, name))


def sync_main_funds(today: date | None = None, reader=None) -> list[Sync]:
    return [sync(symbol, isin, name, today, reader) for symbol, isin, name in MAIN_FUNDS]


def history(symbol: str, start: date | None = None, end: date | None = None) -> list[tuple[date, Decimal]]:
    """The closes stored of one instrument, oldest first, in its own currency."""
    query = (select(closes.c.day, closes.c.close).join(instruments, instruments.c.id == closes.c.instrument_id)
             .where(instruments.c.symbol == symbol.strip().upper()).order_by(closes.c.day))
    if start:
        query = query.where(closes.c.day >= start)
    if end:
        query = query.where(closes.c.day <= end)
    with engine().connect() as conn:
        return [(day, Decimal(close)) for day, close in conn.execute(query)]


def close_on(symbol: str, day: date) -> tuple[date, Decimal] | None:
    """The last close on or before `day` (a holiday carries the day before), or None."""
    query = (select(closes.c.day, closes.c.close).join(instruments, instruments.c.id == closes.c.instrument_id)
             .where(instruments.c.symbol == symbol.strip().upper(), closes.c.day <= day)
             .order_by(closes.c.day.desc()).limit(1))
    with engine().connect() as conn:
        row = conn.execute(query).first()
    return (row[0], Decimal(row[1])) if row else None


def overview() -> list[dict]:
    """Every instrument of the store with how many closes it has, for the prices page."""
    query = (select(instruments, func.count(closes.c.day).label("count"))
             .join(closes, closes.c.instrument_id == instruments.c.id, isouter=True)
             .group_by(instruments.c.id).order_by(instruments.c.symbol))
    with engine().connect() as conn:
        return [dict(row) for row in conn.execute(query).mappings()]


# ── Closes from a file ─────────────────────────────────────────────────────────

DATE_HEADERS = ("date", "data", "day", "giorno")
CLOSE_HEADERS = ("close", "chiusura", "price", "prezzo", "ultimo", "last", "nav")
ADJ_HEADERS = ("adj close", "adj_close", "adjusted close", "chiusura rettificata")


def read_csv(raw: bytes, currency: str | None = None) -> Daily:
    """A CSV of daily closes → the same as a Yahoo answer. The columns are found by their header (Date/Data,
    Close/Chiusura/Price/Ultimo/NAV, optionally Adj Close); separator `,` `;` or tab; dates as 2026-11-02,
    02/11/2026 or 02.11.2026; numbers with either decimal mark. Rows without a valid date or close are skipped."""
    from app.services.parsing import to_date, to_decimal

    text = raw.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    if not rows:
        raise ValueError("empty file")
    header = [cell.strip().lower() for cell in rows[0]]

    def column(names: Iterable[str]) -> int | None:
        return next((i for i, cell in enumerate(header) if cell in names), None)

    day_at, close_at, adj_at = column(DATE_HEADERS), column(CLOSE_HEADERS), column(ADJ_HEADERS)
    if day_at is None or close_at is None:
        raise ValueError("the file needs a date column and a close column (Date, Close)")
    points = {}
    for row in rows[1:]:
        if len(row) <= max(day_at, close_at):
            continue
        day, close = to_date(row[day_at]), to_decimal(row[close_at])
        if day is None or close is None or close <= 0:
            continue
        adj = to_decimal(row[adj_at]) if adj_at is not None and len(row) > adj_at else None
        points[day] = (day, close, adj)
    if not points:
        raise ValueError("no row with a date and a close")
    return Daily(currency, None, None, [points[d] for d in sorted(points)])


# ── Use by the archive ─────────────────────────────────────────────────────────

LINKED_CLASSES = ("ETF", "Azione", "Fondo comune")   # quoted per unit, like the closes (bonds are in % of face value)


def available() -> bool:
    """Whether there is a store to read, without making one (a configured URL, or the SQLite file)."""
    if os.environ.get(ENV) or current_app.config.get(ENV):
        return True
    return (Path(current_app.instance_path) / FILE).exists()


def _catalog() -> tuple[dict[str, dict], dict[str, str]]:
    """The instruments with closes: {symbol: row} and {isin: symbol}, once per request."""
    from app.services import request_cache

    store_cache = request_cache.cache()
    if "market_catalog" not in store_cache:
        by_symbol = {row["symbol"]: row for row in overview() if row["count"]}
        by_isin = {}
        for symbol, row in sorted(by_symbol.items()):
            if row["isin"]:
                by_isin.setdefault(row["isin"].upper(), symbol)
        store_cache["market_catalog"] = (by_symbol, by_isin)
    return store_cache["market_catalog"]


def link(holding) -> tuple[str | None, str]:
    """The symbol whose closes price a holding, and why (or why not): "ticker", "isin", or a reason it is not
    linked — "class" (not priced per unit), "currency" (not quoted in euro), "missing" (no history stored)."""
    if holding.asset_class not in LINKED_CLASSES:
        return None, "class"
    by_symbol, by_isin = _catalog() if available() else ({}, {})
    ticker = (holding.ticker or "").strip().upper()
    if ticker in by_symbol:
        symbol, how = ticker, "ticker"
    elif (holding.isin or "").strip().upper() in by_isin:
        symbol, how = by_isin[holding.isin.strip().upper()], "isin"
    else:
        return None, "missing"
    # F110: a close in another currency counts too, turned into euro with the day's rate (ECB) — when there are rates
    code = plain_currency(by_symbol[symbol]["currency"]) or "EUR"
    if code != "EUR" and not _rates(code)[0]:
        return None, "currency"
    return symbol, how


def _rates(code: str) -> tuple[list[date], list[float]]:
    """The archive's rates of a currency (euro value of one unit), oldest first, once per request."""
    from app.extensions import db
    from app.models.currency import ExchangeRate
    from app.services import request_cache

    store_cache = request_cache.cache().setdefault("market_rates", {})
    if code not in store_cache:
        rows = db.session.query(ExchangeRate.on, ExchangeRate.rate).filter(ExchangeRate.currency == code).order_by(
            ExchangeRate.on).all()
        store_cache[code] = ([d for d, _r in rows], [float(r) for _d, r in rows])
    return store_cache[code]


def _series(symbol: str) -> tuple[list[date], list[float]]:
    """The closes of an instrument in euro, oldest first: one quoted in another currency is turned into euro with
    the rate of its day (or the last before); London's pence are pounds / 100; a day before any rate is left out."""
    from app.services import request_cache

    store_cache = request_cache.cache().setdefault("market_series", {})
    if symbol not in store_cache:
        points = history(symbol)
        raw = (_catalog()[0].get(symbol.strip().upper()) or {}).get("currency") if available() else None
        code = plain_currency(raw) or "EUR"
        scale = 0.01 if raw in ("GBp", "GBX", "GBx") else 1.0
        if code == "EUR":
            store_cache[symbol] = ([d for d, _c in points], [float(c) * scale for _d, c in points])
        else:
            rate_days, rate_values = _rates(code)
            days_out, values_out = [], []
            for day, close in points:
                at = bisect.bisect_right(rate_days, day)
                if at:
                    days_out.append(day)
                    values_out.append(float(close) * scale * rate_values[at - 1])
            store_cache[symbol] = (days_out, values_out)
    return store_cache[symbol]


def close_before(symbol: str, day: date) -> tuple[date, float] | None:
    """The last stored close on or before a day, from the request's copy of the series."""
    days, values = _series(symbol)
    at = bisect.bisect_right(days, day)
    return (days[at - 1], values[at - 1]) if at else None


def linked_holdings() -> dict[int, str]:
    """{holding id: symbol} of every holding the store prices, once per request."""
    from app.models.wealth import Holding
    from app.services import request_cache

    store_cache = request_cache.cache()
    if "market_links" not in store_cache:
        found = {}
        if available():
            candidates = Holding.query.filter(Holding.asset_class.in_(LINKED_CLASSES),
                                              (Holding.ticker.isnot(None)) | (Holding.isin.isnot(None)))
            for holding in candidates:
                symbol, _how = link(holding)
                if symbol:
                    found[holding.id] = symbol
        store_cache["market_links"] = found
    return store_cache["market_links"]


def overlay(recorded: dict[int, tuple[date, float]], on: date) -> dict[int, float]:
    """The archive's latest recorded prices on a date, each replaced by the stored close when that is newer."""
    prices = {hid: price for hid, (_day, price) in recorded.items()}
    for hid, symbol in linked_holdings().items():
        close = close_before(symbol, on)
        if close and (hid not in recorded or close[0] >= recorded[hid][0]):
            prices[hid] = close[1]
    return prices
