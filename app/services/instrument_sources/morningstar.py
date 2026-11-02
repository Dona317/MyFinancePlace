"""Morningstar: mutual funds by ISIN — the search gives the fund's id, its page the latest NAV and its date."""
from __future__ import annotations

import json
import re

from flask_babel import gettext as _

from .base import Broken, Candidate, NotFound, Quote, day, get_text, number

SITE = "morningstar"
SEARCH = "https://www.morningstar.it/it/util/SecuritySearch.ashx?q={isin}&limit=5"
PAGE = "https://www.morningstar.it/it/funds/snapshot/snapshot.aspx?id={id}"
NAV = re.compile(r"NAV.{0,200}?(\d{1,2}/\d{1,2}/\d{4}).{0,200}?([A-Z]{3})(?:\s|&nbsp;)*([\d.,]+)", re.S)


def _search(isin: str) -> list[tuple[str, dict]]:
    """(name, its data) of each line of the answer «name|{json}|…»."""
    found = []
    for line in get_text(SITE, SEARCH.format(isin=isin)).splitlines():
        parts = line.split("|")
        if len(parts) < 2:
            continue
        try:
            data = json.loads(parts[1])
        except json.JSONDecodeError:
            raise Broken(_("risposta non leggibile")) from None
        if isinstance(data, dict) and data.get("i"):
            found.append((parts[0].strip(), data))
    if not found:
        raise NotFound(_("nessun risultato"))
    return found


def find(isin: str) -> list[Candidate]:
    return [Candidate("", name, "ETF" if data.get("t") == "ETF" else "Fondo", None, isin, source=SITE,
                      price_source=SITE) for name, data in _search(isin)[:3]]


def quote(isin: str) -> Quote:
    _name, data = _search(isin)[0]
    page = get_text(SITE, PAGE.format(id=data["i"]))
    found = NAV.search(page)
    if not found:
        raise Broken(_("la pagina è cambiata"))
    price, on = number(found.group(3)), day(found.group(1))
    if price is None or on is None:
        raise Broken(_("la pagina è cambiata"))
    return Quote(price, on, found.group(2))
