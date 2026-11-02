"""
Borsa Italiana: government and corporate bonds of the MOT, ETFs and ETCs, shares and certificates of Milan, by ISIN.
The search leads to the instrument's page; its last price (or reference price) and date are read from it. Bond prices
are a percentage of the face value: the quantity of a bond is its face value, its price per unit is the price / 100.
"""
from __future__ import annotations

import re

from flask_babel import gettext as _

from .base import Broken, Candidate, NotFound, Quote, after_label, day, first_heading, get_text, number

SITE = "borsaitaliana"
ROOT = "https://www.borsaitaliana.it"
SEARCH = ROOT + "/borsa/ricerca/risultati.html?q={isin}&lang=it"
MARKETS = (("/obbligazioni/", "Obbligazione"), ("/etf/", "ETF"), ("/etc-etn/", "ETF"), ("/azioni/", "Azione"),
           ("/cw/", "Derivato"), ("/certificati/", "Derivato"), ("/sedex/", "Derivato"), ("/fondi/", "Fondo"))
PRICE_LABELS = ("Prezzo ultimo contratto", "Ultimo Prezzo", "Prezzo di riferimento", "Prezzo ufficiale")
DATE_LABELS = ("Data - Ora Ultimo Contratto", "Data Ultimo Contratto", "Data e ora", "Data")


def _page(isin: str) -> tuple[str, str]:
    """The URL and the page of the instrument (the search's first link to its «scheda»)."""
    results = get_text(SITE, SEARCH.format(isin=isin))
    link = re.search(r'href="([^"]*scheda/' + re.escape(isin) + r'[^"]*)"', results, re.I)
    if not link:
        raise NotFound(_("nessun risultato"))
    url = link.group(1) if link.group(1).startswith("http") else ROOT + link.group(1)
    return url, get_text(SITE, url)


def _market(url: str) -> str:
    return next((kind for part, kind in MARKETS if part in url), "Azione")


def find(isin: str) -> list[Candidate]:
    url, page = _page(isin)
    name = first_heading(page)
    if not name:
        raise Broken(_("la pagina è cambiata"))
    return [Candidate("", name, _market(url), "Borsa Italiana", isin, source=SITE, price_source=SITE)]


def quote(isin: str) -> Quote:
    url, page = _page(isin)
    price = number(after_label(page, *PRICE_LABELS))
    on = day(after_label(page, *DATE_LABELS))
    if price is None or on is None:
        raise Broken(_("la pagina è cambiata"))
    if _market(url) == "Obbligazione":
        price = price / 100  # % of the face value → per unit of face value
    return Quote(price, on, "EUR")
