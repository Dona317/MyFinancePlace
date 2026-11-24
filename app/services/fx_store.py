"""
Exchange rates in the shared price database (24 Nov 2026, F116): day by day, how many units of a currency one euro
buys — the instruments «FX.USD», «FX.GBP»… of market_data, next to the closes, shared by every archive and kept with
no connection. They turn into euro, day by day, the closes of instruments quoted in another currency.

    the main currencies (MAIN) come with the starting price database, since 1999
    any other the ECB publishes: added from Dati → Cambi, its whole history read from the ECB
    one the ECB does not publish: added from a CSV file (date, rate)
    once a day (the market data update), the ones from the ECB brought up to date

The archive's own rates (Impostazioni → Valute, ExchangeRate) stay what they are: they count the archive's movements.
"""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app.services import market_data

PREFIX = "FX."
SOURCE_ECB = "ecb"
MAIN = ("USD", "GBP", "CHF", "JPY", "CNY", "CAD", "AUD")
# what the ECB publishes every day (its reference rates)
ECB = ("USD", "JPY", "BGN", "CZK", "DKK", "GBP", "HUF", "PLN", "RON", "SEK", "CHF", "ISK", "NOK", "TRY", "AUD", "BRL",
       "CAD", "CNY", "HKD", "IDR", "ILS", "INR", "KRW", "MXN", "MYR", "NZD", "PHP", "SGD", "THB", "ZAR")
STALE = timedelta(days=4)
GONE = timedelta(days=60)  # no rate for two months: the ECB stopped (BGN, 2026: Bulgaria in the euro)


def symbol(code: str) -> str:
    return f"{PREFIX}{code.strip().upper()}"


def parse_ecb_history(raw: bytes, codes) -> dict[str, list[tuple[date, Decimal]]]:
    """The ECB's whole history (a zip with one CSV: Date, USD, JPY…, units for one euro) → {currency: [(day, rate)]}
    for the currencies asked, oldest first."""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        text = archive.read(archive.namelist()[0]).decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    header = [cell.strip() for cell in next(reader)]
    columns = {code: i for i, code in enumerate(header) if code in codes}
    points: dict[str, dict] = {code: {} for code in columns}
    for row in reader:
        try:
            day = date.fromisoformat(row[0].strip())
        except (ValueError, IndexError):
            continue
        for code, i in columns.items():
            try:
                value = Decimal(row[i].strip())
            except (InvalidOperation, IndexError):
                continue
            if value > 0:
                points[code][day] = value
    return {code: sorted(days.items()) for code, days in points.items() if days}


def store_ecb(raw: bytes, codes=MAIN) -> int:
    """The ECB's history of some currencies into the price database; how many rates."""
    added = 0
    for code, points in parse_ecb_history(raw, codes).items():
        daily = market_data.Daily(code, "BCE", None, [(d, v, None) for d, v in points])
        added += market_data.store(symbol(code), daily, None, f"Cambio: {code} per 1 euro", source=SOURCE_ECB)
    return added


def _ecb_zip(fetch=None) -> bytes:
    from app.services import history_filler  # the ECB's address and the download live there

    return (fetch or history_filler._bytes)(history_filler.ECB_HISTORY)


def listed() -> list[dict]:
    """The currencies in the price database: {code, first, last, count, sources}, by code."""
    if not market_data.available():
        return []
    rows = []
    for row in market_data.overview():
        if row["symbol"].startswith(PREFIX) and row["count"]:
            code = row["symbol"][len(PREFIX):]
            rows.append({"code": code, "first": row["first_day"], "last": row["last_day"], "count": row["count"],
                         "sources": market_data.sources_of(row["symbol"])})
    return sorted(rows, key=lambda r: r["code"])


def addable() -> list[str]:
    """The ECB's currencies not in the price database yet."""
    have = {r["code"] for r in listed()}
    return [code for code in sorted(ECB) if code not in have]


def add_from_ecb(code: str, fetch=None) -> int:
    """A currency the ECB publishes: its whole history, now."""
    code = code.strip().upper()
    if code not in ECB:
        raise ValueError(code)
    added = store_ecb(_ecb_zip(fetch), (code,))
    if not added:
        raise ValueError(code)
    return added


def add_from_csv(code: str, raw: bytes) -> market_data.Daily:
    """A currency from a file: a date column and a rate column (units for one euro), as the closes are read."""
    code = code.strip().upper()
    if len(code) != 3 or not code.isalpha() or code == "EUR":
        raise ValueError(code)
    daily = market_data.read_csv(raw, code)
    market_data.store(symbol(code), daily, None, f"Cambio: {code} per 1 euro", source="file")
    return daily


def refresh(today: date | None = None, fetch=None) -> int:
    """Once a day: the currencies the ECB publishes that are in the price database, brought up to date when their
    last rate is older than four days (weekends and holidays have none) — not those the ECB stopped publishing;
    how many rates."""
    today = today or date.today()
    due = [r["code"] for r in listed() if r["code"] in ECB and SOURCE_ECB in r["sources"]
           and today - GONE < r["last"] < today - STALE]
    if not due:
        return 0
    return store_ecb(_ecb_zip(fetch), tuple(due))
