"""
Prices from the internet (F5b), free and without an API key, only when the user turns it on (Settings) and asks for
it: the request sends nothing but the tickers.

- ETFs, shares, bonds, funds: Yahoo Finance's public chart endpoint, by ticker with the exchange suffix
  (VWCE.DE, ENEL.MI, SWDA.MI…); a price in another currency is converted with the saved exchange rates.
- Crypto: CoinGecko's simple price, in euro, by CoinGecko id (bitcoin, ethereum…); the common symbols are mapped.

Every price read goes into the holding's history (F5) for the day it refers to.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from flask_babel import gettext as _

from app.models.wealth import Holding
from app.services import currency, wealth

YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=1d"
COINGECKO = "https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=eur&include_last_updated_at=true"
CRYPTO_CLASSES = ("Criptovaluta",)
MARKET_CLASSES = ("ETF", "Azione", "Obbligazione", "Fondo")  # priced on an exchange; the rest is valued by hand
COINGECKO_IDS = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "ADA": "cardano", "XRP": "ripple",
                 "DOT": "polkadot", "DOGE": "dogecoin", "LTC": "litecoin", "BNB": "binancecoin", "USDT": "tether",
                 "USDC": "usd-coin", "MATIC": "matic-network", "AVAX": "avalanche-2", "LINK": "chainlink"}
TIMEOUT = 15


@dataclass
class Result:
    holding: Holding
    price: Decimal | None = None
    on: date | None = None
    error: str | None = None


def _get_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 MyFinancePlace", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - fixed https endpoints
        return json.loads(response.read().decode("utf-8"))


def supported(holding: Holding) -> bool:
    return bool(holding.ticker) and holding.asset_class in MARKET_CLASSES + CRYPTO_CLASSES


def _coingecko_id(holding: Holding) -> str:
    ticker = holding.ticker.strip()
    return COINGECKO_IDS.get(ticker.upper(), ticker.lower())


def _yahoo(holding: Holding) -> tuple[Decimal, date]:
    data = _get_json(YAHOO.format(ticker=urllib.parse.quote(holding.ticker.strip().upper())))
    results = (data.get("chart") or {}).get("result") or []
    if not results:
        raise ValueError(_("ticker «%(ticker)s» non trovato (per Borsa Italiana aggiungi .MI, per Xetra .DE)",
                           ticker=holding.ticker))
    meta = results[0].get("meta") or {}
    price, raw_code = meta.get("regularMarketPrice"), meta.get("currency") or "EUR"
    if price is None:
        raise ValueError(_("nessun prezzo per «%(ticker)s»", ticker=holding.ticker))
    on = datetime.fromtimestamp(meta.get("regularMarketTime") or datetime.now().timestamp(), tz=timezone.utc).date()
    value, code = Decimal(str(price)), raw_code.upper()
    if raw_code in ("GBp", "GBX", "GBx"):  # London quotes in pence
        value, code = value / 100, "GBP"
    if code != currency.BASE:
        if currency.rate_on(code, on) is None:
            raise ValueError(_("prezzo in %(code)s: manca il cambio (Impostazioni → Valute)", code=code))
        value = currency.to_base(value, code, on)
    return value.quantize(Decimal("0.000001")), on


def _coingecko(holdings: list[Holding]) -> dict[int, tuple[Decimal, date] | str]:
    ids = {h.id: _coingecko_id(h) for h in holdings}
    data = _get_json(COINGECKO.format(ids=",".join(sorted(set(ids.values())))))
    found = {}
    for holding_id, coin in ids.items():
        quote = data.get(coin) or {}
        if "eur" not in quote:
            found[holding_id] = _("criptovaluta «%(coin)s» non trovata su CoinGecko (usa il suo id, es. bitcoin)", coin=coin)
            continue
        stamp = quote.get("last_updated_at") or datetime.now().timestamp()
        found[holding_id] = (Decimal(str(quote["eur"])), datetime.fromtimestamp(stamp, tz=timezone.utc).date())
    return found


def update_all(holdings: list[Holding]) -> list[Result]:
    """Read the price of every supported holding and record it; the others are left alone. Network errors are
    reported per holding, never raised."""
    results = []
    crypto = [h for h in holdings if supported(h) and h.asset_class in CRYPTO_CLASSES]
    if crypto:
        try:
            quotes = _coingecko(crypto)
        except (OSError, ValueError) as exc:
            quotes = {h.id: _("CoinGecko non risponde (%(exc)s)", exc=exc) for h in crypto}
        for holding in crypto:
            quote = quotes[holding.id]
            results.append(Result(holding, error=quote) if isinstance(quote, str) else Result(holding, *quote))
    for holding in (h for h in holdings if supported(h) and h.asset_class in MARKET_CLASSES):
        try:
            results.append(Result(holding, *_yahoo(holding)))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            results.append(Result(holding, error=str(exc)))
    for result in results:
        if result.price is not None and result.price > 0:
            wealth.record_price(result.holding, result.price, min(result.on, date.today()))
    return results
