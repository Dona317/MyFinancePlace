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
trading day) and then from the last close stored minus a week (late corrections). Only the symbol is sent.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
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


def store(symbol: str, daily: Daily, isin: str | None = None, name: str | None = None) -> int:
    """Save the closes read (a day already there is overwritten: the source may correct it); how many."""
    with engine().begin() as conn:
        row = _instrument(conn, symbol, isin, name or daily.name)
        days = [p[0] for p in daily.points]
        if days:
            conn.execute(closes.delete().where(closes.c.instrument_id == row["id"], closes.c.day.in_(days)))
            conn.execute(insert(closes), [{"instrument_id": row["id"], "day": d, "close": c, "adj_close": a,
                                           "source": "yahoo"} for d, c, a in daily.points])
        first, last = conn.execute(select(func.min(closes.c.day), func.max(closes.c.day))
                                   .where(closes.c.instrument_id == row["id"])).one()
        conn.execute(update(instruments).where(instruments.c.id == row["id"]).values(
            currency=daily.currency or row["currency"], exchange=daily.exchange or row["exchange"],
            name=row["name"] or daily.name, first_day=first, last_day=last, synced_at=datetime.utcnow(), error=None))
    return len(daily.points)


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
