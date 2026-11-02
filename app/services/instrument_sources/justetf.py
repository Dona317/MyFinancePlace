"""justETF: the European ETFs, by ISIN — the name from the profile page, the latest price in euro from its quote."""
from __future__ import annotations

import re

from flask_babel import gettext as _

from .base import Broken, Candidate, NotFound, Quote, day, first_heading, get_json, get_text, number

SITE = "justetf"
PROFILE = "https://www.justetf.com/it/etf-profile.html?isin={isin}"
QUOTE = "https://www.justetf.com/api/etfs/{isin}/quote?locale=it&currency=EUR&isin={isin}"


def find(isin: str) -> list[Candidate]:
    page = get_text(SITE, PROFILE.format(isin=isin))
    if isin not in page:
        raise NotFound(_("nessun risultato"))
    name = first_heading(page)
    if not name:
        raise Broken(_("la pagina è cambiata"))
    ticker = re.search(r"Ticker[^<]*</[^>]+>\s*<[^>]+>\s*([A-Z0-9]{2,8})\s*<", page)
    return [Candidate(ticker.group(1) if ticker else "", name, "ETF", None, isin, source=SITE, price_source=SITE)]


def quote(isin: str) -> Quote:
    data = get_json(SITE, QUOTE.format(isin=isin))
    latest = (data or {}).get("latestQuote") or {}
    price = number(str(latest.get("raw"))) if latest.get("raw") is not None else number(latest.get("localized"))
    on = day(str(data.get("latestQuoteDate") or ""))
    if price is None or on is None:
        raise Broken(_("la risposta è cambiata"))
    return Quote(price, on, "EUR")
