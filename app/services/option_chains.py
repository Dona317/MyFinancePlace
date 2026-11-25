"""
US option chains (25 Nov 2026, F120.3): the expiries of an underlying and, for one of them, its calls and puts —
strike, last price, bid and ask, implied volatility, open interest — read through yfinance (F119), to pick the
contract in the holding form instead of typing its terms.

Only the chains need the library: once chosen, the contract (its OCC symbol as ticker) is priced every day by the
app's own reading of Yahoo, like a share. The IDEM and Eurex options have no free chain: their terms are typed.
"""
from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

from app.services import yf_source


def _library(library=None):
    from flask import current_app

    if library is not None:
        return library
    if not current_app.config.get("YFINANCE", True):
        raise ValueError("yfinance spento")
    if not yf_source.available():
        raise ValueError("yfinance non installato")
    return yf_source._library()


def expiries(underlying: str, library=None) -> list[date]:
    """The expiries listed for an underlying (none: no options on Yahoo, or not a US listing)."""
    ticker = _library(library).Ticker(underlying.strip().upper())
    return [date.fromisoformat(text) for text in (ticker.options or ())]


def _value(raw) -> float | None:
    if raw is None:
        return None
    number = float(raw)
    return None if math.isnan(number) else number


def _rows(frame) -> list[dict]:
    if frame is None or getattr(frame, "empty", True):
        return []
    columns = list(frame.columns)

    def column(name):
        return list(frame[name]) if name in columns else [None] * len(frame.index)
    out = []
    for symbol, strike, last, bid, ask, iv, oi, volume, itm, size in zip(
            column("contractSymbol"), column("strike"), column("lastPrice"), column("bid"), column("ask"),
            column("impliedVolatility"), column("openInterest"), column("volume"), column("inTheMoney"),
            column("contractSize")):
        if not symbol or _value(strike) is None:
            continue
        out.append({"symbol": str(symbol), "strike": _value(strike), "last": _value(last), "bid": _value(bid),
                    "ask": _value(ask), "iv": _value(iv), "open_interest": _value(oi), "volume": _value(volume),
                    "itm": bool(itm), "multiplier": 100 if (size or "REGULAR") == "REGULAR" else 1})
    return out


def chain(underlying: str, expiry: date, library=None) -> dict:
    """{underlying, expiry, price, currency, calls, puts} of one expiry; each row {symbol, strike, last, bid, ask, iv,
    open_interest, volume, itm, multiplier}, by strike."""
    found = _library(library).Ticker(underlying.strip().upper()).option_chain(expiry.isoformat())
    info = getattr(found, "underlying", None) or {}
    rows = {"calls": _rows(getattr(found, "calls", None)), "puts": _rows(getattr(found, "puts", None))}
    currency = next((str(c) for c in [info.get("currency")] if c), "USD")
    price = info.get("regularMarketPrice")
    return {"underlying": underlying.strip().upper(), "expiry": expiry.isoformat(),
            "price": float(Decimal(str(price))) if price is not None else None, "currency": currency,
            "calls": sorted(rows["calls"], key=lambda r: r["strike"]),
            "puts": sorted(rows["puts"], key=lambda r: r["strike"])}
