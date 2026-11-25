"""
yfinance as a source of the daily closes (25 Nov 2026, F119): the open-source library that reads Yahoo Finance, tried
when the app's own reading of Yahoo (market_data.read_yahoo) does not answer — it handles Yahoo's cookies and limits
by itself — before Stooq and justETF.

The user's decision (25 Nov 2026), knowing that recent versions of the library present themselves to Yahoo as a
browser (curl_cffi): the one exception to the rule of not working around a site's limits (F69). Only the symbol is
sent, as with the other sources.

It is optional: an installation without the library (`pip install yfinance`) simply does not have this source.
"""
from __future__ import annotations

import importlib.util
import logging
import math
from datetime import date, timedelta
from decimal import Decimal

from app.services import market_data

NAME = "yfinance"


def available() -> bool:
    return importlib.util.find_spec("yfinance") is not None


def read_if_on(symbol: str, start: date, end: date) -> market_data.Daily:
    """The filler's source: off when the library is missing or the app says so (YFINANCE = False: the tests)."""
    from flask import current_app

    if not current_app.config.get("YFINANCE", True):
        raise ValueError("yfinance spento")
    if not available():
        raise ValueError("yfinance non installato")
    return read(symbol, start, end)


def _library():
    import yfinance

    logging.getLogger("yfinance").setLevel(logging.CRITICAL)  # its cookie and «possibly delisted» chatter
    return yfinance


def _number(value) -> Decimal | None:
    if value is None:
        return None
    number = float(value)
    if math.isnan(number) or number == 0:
        return None
    return Decimal(str(round(number, 6)))


def read(symbol: str, start: date, end: date, library=None) -> market_data.Daily:
    """The daily closes (and the adjusted ones) of a Yahoo symbol between two days, in the instrument's currency."""
    yf = library or _library()
    ticker = yf.Ticker(symbol)
    frame = ticker.history(start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(), interval="1d",
                           auto_adjust=False, actions=False)
    if frame is None or frame.empty:
        raise ValueError("yfinance: nessuna chiusura")
    columns = list(frame.columns)
    closes = list(frame["Close"])
    adjusted = list(frame["Adj Close"]) if "Adj Close" in columns else [None] * len(closes)
    points = {}
    for stamp, close, adj in zip(frame.index, closes, adjusted):
        value = _number(close)
        if value is None:
            continue
        day = stamp.date() if hasattr(stamp, "date") else stamp
        points[day] = (day, value, _number(adj))
    if not points:
        raise ValueError("yfinance: nessuna chiusura")
    meta = getattr(ticker, "history_metadata", None) or {}
    return market_data.Daily(meta.get("currency"), meta.get("exchangeName"), meta.get("longName") or meta.get("shortName"),
                             [points[d] for d in sorted(points)])
