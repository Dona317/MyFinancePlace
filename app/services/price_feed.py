"""
Prices from the internet (F5b, F19), free and without an API key, only when the user turns it on (Settings): the
requests send nothing but the tickers, ISINs or names looked up.

- ETFs, shares, bonds, funds, derivatives: Yahoo Finance's public chart endpoint, by ticker with the exchange suffix
  (VWCE.DE, ENEL.MI, SWDA.MI…); Stooq's CSV quote as a reserve when Yahoo does not answer. A holding with only its
  ISIN gets its ticker from Yahoo's search. A price in another currency is converted with the saved exchange rates.
- Crypto: CoinGecko's simple price, in euro, by CoinGecko id (bitcoin, ethereum…); the common symbols are mapped.

Every price read goes into the holding's history (F5) for the day it refers to; the first time, the last year of
weekly prices too, so the charts start full. With the setting on, prices are read once a day by themselves: on the
first visit of the day to the portfolio or the dashboard (in the background), and by the desktop app.
"""
from __future__ import annotations

import csv
import io
import json
import re
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import current_app
from flask_babel import gettext as _

from app.extensions import db
from app.models.wealth import Holding, HoldingPrice
from app.services import currency, money, settings_store, studio, wealth
from app.services.ui_settings import current_settings

YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range}&interval={interval}"
YAHOO_SEARCH = "https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=10&newsCount=0"
STOOQ = "https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
COINGECKO = "https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=eur&include_last_updated_at=true"
CRYPTO_CLASSES = ("Criptovaluta",)
MARKET_CLASSES = ("ETF", "Azione", "Obbligazione", "Fondo", "Derivato")  # priced on an exchange; the rest by hand
SOURCES = ("auto", "yahoo", "stooq", "coingecko", "manual")
COINGECKO_IDS = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "ADA": "cardano", "XRP": "ripple",
                 "DOT": "polkadot", "DOGE": "dogecoin", "LTC": "litecoin", "BNB": "binancecoin", "USDT": "tether",
                 "USDC": "usd-coin", "MATIC": "matic-network", "AVAX": "avalanche-2", "LINK": "chainlink"}
# Yahoo's kinds of instrument → our asset classes (indices and currencies are not something one holds)
QUOTE_TYPES = {"EQUITY": "Azione", "ETF": "ETF", "MUTUALFUND": "Fondo", "BOND": "Obbligazione", "FUTURE": "Derivato",
               "OPTION": "Derivato", "CRYPTOCURRENCY": "Criptovaluta"}
# Listings shown first when a search finds the same instrument on several exchanges: Milan, then the euro ones
PREFERRED_EXCHANGES = ("MIL", "GER", "AMS", "PAR", "EBS", "LSE")
# Yahoo suffix → Stooq suffix and the currency it quotes in (Stooq has no Italian listings)
STOOQ_MARKETS = {"": ("us", "USD"), "DE": ("de", "EUR"), "L": ("uk", "GBX"), "T": ("jp", "JPY"), "HK": ("hk", "HKD")}
ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
HISTORY_POINTS = 5  # a holding with fewer saved prices gets the last year of weekly ones
LAST_RUN = "prices.last_run"
TIMEOUT = 15
_running: set = set()
_lock = threading.Lock()


class MissingRate(ValueError):
    """The price is in a currency without a saved exchange rate: no other source would do better."""


@dataclass
class Result:
    holding: Holding
    price: Decimal | None = None
    on: date | None = None
    error: str | None = None
    source: str | None = None
    history: list = field(default_factory=list)  # (day, price in euro) of the past year, when read


@dataclass
class Candidate:
    """An instrument found by a search: what fills the holding's form."""
    symbol: str
    name: str
    asset_class: str
    exchange: str | None = None
    isin: str | None = None

    def as_dict(self) -> dict:
        return {"symbol": self.symbol, "name": self.name, "asset_class": self.asset_class, "exchange": self.exchange,
                "isin": self.isin}


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 MyFinancePlace",
                                                   "Accept": "application/json, text/csv, */*"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - fixed https endpoints
        return response.read().decode("utf-8")


def _get_json(url: str):
    return json.loads(_fetch(url))


def _get_text(url: str) -> str:
    return _fetch(url)


# ── Which source ───────────────────────────────────────────────────────────────

def source_of(holding: Holding) -> str | None:
    """The source its price is read from, None when it is valued by hand."""
    chosen = holding.price_source or "auto"
    if chosen == "manual":
        return None
    if chosen != "auto":
        return chosen
    if holding.asset_class in CRYPTO_CLASSES:
        return "coingecko"
    return "yahoo" if holding.asset_class in MARKET_CLASSES else None


def supported(holding: Holding) -> bool:
    return bool(holding.ticker or holding.isin) and source_of(holding) is not None


def _coingecko_id(holding: Holding) -> str:
    ticker = (holding.ticker or "").strip()
    return COINGECKO_IDS.get(ticker.upper(), ticker.lower())


# ── Search: ISIN, ticker or name → instruments ─────────────────────────────────

def lookup(text: str) -> list[Candidate]:
    """Instruments matching an ISIN, a ticker or a name (Yahoo's search), the Milan and euro listings first."""
    query = (text or "").strip()
    if not query:
        return []
    isin = query.upper() if ISIN.match(query.upper()) else None
    data = _get_json(YAHOO_SEARCH.format(query=urllib.parse.quote(isin or query)))
    found = []
    for item in data.get("quotes") or []:
        kind = QUOTE_TYPES.get(str(item.get("quoteType") or "").upper())
        symbol = item.get("symbol")
        if not kind or not symbol:
            continue
        name = item.get("longname") or item.get("shortname") or symbol
        found.append((item.get("exchange"), Candidate(symbol, name, kind, item.get("exchDisp") or item.get("exchange"), isin)))
    rank = {code: i for i, code in enumerate(PREFERRED_EXCHANGES)}
    found.sort(key=lambda pair: rank.get(pair[0], len(rank)))
    return [candidate for _exchange, candidate in found]


def _resolve_ticker(holding: Holding) -> None:
    """A holding with only its ISIN: the ticker of its first listing (Milan if there is one)."""
    if holding.ticker or not holding.isin:
        return
    candidates = lookup(holding.isin)
    if not candidates:
        raise ValueError(_("ISIN %(isin)s non trovato: scrivi il ticker con il suffisso di borsa (es. SWDA.MI)",
                           isin=holding.isin))
    holding.ticker, holding.exchange = candidates[0].symbol, holding.exchange or candidates[0].exchange


# ── Reading a price ────────────────────────────────────────────────────────────

def _to_euro(value: Decimal, code: str, on: date) -> Decimal:
    if code in ("GBP_PENCE",):
        value, code = value / 100, "GBP"
    if code != currency.BASE:
        if currency.rate_on(code, on) is None:
            raise MissingRate(_("prezzo in %(code)s: manca il cambio (Impostazioni → Valute)", code=code))
        value = currency.to_base(value, code, on)
    return money.price(value)


def _currency_code(raw: str | None) -> str:
    raw = raw or "EUR"
    return "GBP_PENCE" if raw in ("GBp", "GBX", "GBx") else raw.upper()


def _remember_currency(holding: Holding, code: str) -> None:
    if not holding.currency:
        holding.currency = "GBP" if code == "GBP_PENCE" else code[:3]


def _day(stamp) -> date:
    return datetime.fromtimestamp(stamp or datetime.now().timestamp(), tz=timezone.utc).date()


def _yahoo(holding: Holding, with_history: bool = False) -> tuple[Decimal, date, list]:
    ticker = holding.ticker.strip().upper()
    span = ("1y", "1wk") if with_history else ("5d", "1d")
    data = _get_json(YAHOO.format(ticker=urllib.parse.quote(ticker), range=span[0], interval=span[1]))
    results = (data.get("chart") or {}).get("result") or []
    if not results:
        raise ValueError(_("ticker «%(ticker)s» non trovato (per Borsa Italiana aggiungi .MI, per Xetra .DE)",
                           ticker=holding.ticker))
    meta = results[0].get("meta") or {}
    price, code = meta.get("regularMarketPrice"), _currency_code(meta.get("currency"))
    if price is None:
        raise ValueError(_("nessun prezzo per «%(ticker)s»", ticker=holding.ticker))
    on = _day(meta.get("regularMarketTime"))
    value = _to_euro(Decimal(str(price)), code, on)
    _remember_currency(holding, code)
    history = []
    if with_history:
        stamps = results[0].get("timestamp") or []
        closes = (((results[0].get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
        for stamp, close in zip(stamps, closes):
            day = _day(stamp)
            if close is None or day >= on:
                continue
            try:
                history.append((day, _to_euro(Decimal(str(close)), code, day)))
            except MissingRate:
                continue  # no rate that far back: those weeks stay without a price
    return value, on, history


def _stooq_symbol(ticker: str) -> tuple[str, str]:
    base, _dot, suffix = ticker.strip().upper().partition(".")
    if suffix not in STOOQ_MARKETS:
        raise ValueError(_("non quotato su Stooq (borsa .%(suffix)s)", suffix=suffix))
    market, code = STOOQ_MARKETS[suffix]
    return f"{base.lower()}.{market}", code


def _stooq(holding: Holding) -> tuple[Decimal, date, list]:
    symbol, code = _stooq_symbol(holding.ticker)
    rows = list(csv.DictReader(io.StringIO(_get_text(STOOQ.format(symbol=urllib.parse.quote(symbol))))))
    row = rows[0] if rows else {}
    try:
        price, on = Decimal(row.get("Close") or ""), date.fromisoformat(row.get("Date") or "")
    except (InvalidOperation, ValueError):
        raise ValueError(_("«%(ticker)s» non trovato su Stooq", ticker=holding.ticker)) from None
    if code == "GBX":
        code = "GBP_PENCE"
    _remember_currency(holding, code)
    return _to_euro(price, code, on), on, []


def _coingecko(holdings: list[Holding]) -> dict[int, tuple[Decimal, date] | str]:
    ids = {h.id: _coingecko_id(h) for h in holdings}
    data = _get_json(COINGECKO.format(ids=",".join(sorted(set(ids.values())))))
    found = {}
    for holding_id, coin in ids.items():
        quote = data.get(coin) or {}
        if "eur" not in quote:
            found[holding_id] = _("criptovaluta «%(coin)s» non trovata su CoinGecko (usa il suo id, es. bitcoin)", coin=coin)
            continue
        found[holding_id] = (Decimal(str(quote["eur"])), _day(quote.get("last_updated_at")))
    return found


def _wants_history(holding: Holding) -> bool:
    return holding.id is not None and HoldingPrice.query.filter_by(holding_id=holding.id).count() < HISTORY_POINTS


def _market(holding: Holding) -> Result:
    """Yahoo, then Stooq when Yahoo does not answer (or the other way round when Stooq was chosen)."""
    try:
        _resolve_ticker(holding)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return Result(holding, error=str(exc))
    first = source_of(holding)
    order = [first] if (holding.price_source or "auto") != "auto" else [first, "stooq"]
    errors = []
    for source in order:
        try:
            if source == "stooq":
                price, on, history = _stooq(holding)
            else:
                price, on, history = _yahoo(holding, with_history=_wants_history(holding))
            return Result(holding, price, on, source=source, history=history)
        except MissingRate as exc:
            return Result(holding, error=str(exc))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc) if not errors else f"Stooq: {exc}")
    return Result(holding, error=" · ".join(errors))


def update_all(holdings: list[Holding]) -> list[Result]:
    """Read the price of every holding with a source and record it; the others are left alone. Network errors are
    reported per holding, never raised."""
    results = []
    crypto = [h for h in holdings if supported(h) and source_of(h) == "coingecko"]
    if crypto:
        try:
            quotes = _coingecko(crypto)
        except (OSError, ValueError) as exc:
            quotes = {h.id: _("CoinGecko non risponde (%(exc)s)", exc=exc) for h in crypto}
        for holding in crypto:
            quote = quotes[holding.id]
            results.append(Result(holding, error=quote) if isinstance(quote, str)
                           else Result(holding, *quote, source="coingecko"))
    results += [_market(h) for h in holdings if supported(h) and source_of(h) in ("yahoo", "stooq")]
    today = date.today()
    for result in results:
        for day, price in result.history:
            if price > 0:
                wealth.record_price(result.holding, price, day)
        if result.price is not None and result.price > 0:
            wealth.record_price(result.holding, result.price, min(result.on, today))
    return results


# ── Once a day, by itself ──────────────────────────────────────────────────────

def due(today: date | None = None) -> bool:
    """Prices from the internet are on and were not read yet today."""
    today = today or date.today()
    return bool(current_settings()["prices_online"]) and settings_store.get(LAST_RUN) != today.isoformat()


def refresh_daily(today: date | None = None) -> list[Result] | None:
    """The day's prices, once a day (None when not due)."""
    today = today or date.today()
    if not due(today):
        return None
    settings_store.set(LAST_RUN, today.isoformat())  # first: a second visit meanwhile does not start it again
    results = update_all(wealth.holdings_on())
    db.session.commit()
    return results


def refresh_in_background() -> None:
    """On a page visit: the day's prices read in a thread, so the page does not wait for the internet."""
    if not due():
        return
    client = studio.current()
    if current_app.config.get("PRICES_SYNC"):
        refresh_daily()
        return
    key = client.id if client is not None else None
    with _lock:
        if key in _running:
            return
        _running.add(key)
    app = current_app._get_current_object()
    threading.Thread(target=_refresh_thread, args=(app, client, key), daemon=True, name="prices-daily").start()


def _refresh_thread(app, client, key) -> None:
    try:
        with app.app_context(), app.test_request_context("/"):
            studio.activate(client)
            refresh_daily()
    except Exception:  # noqa: BLE001 - a failed reading must not hurt the app; the next day tries again
        app.logger.exception("daily prices not read")
    finally:
        with _lock:
            _running.discard(key)


def refresh_all_archives(today: date | None = None) -> int:
    """The desktop app's daily round: the prices of every client archive; returns how many were read."""
    read = 0
    for client in [c for c in studio.clients() if not c.archived]:
        with studio.using(client):
            results = refresh_daily(today) or []
            read += sum(1 for r in results if r.error is None)
    return read
