"""OpenFIGI (Bloomberg's open symbology, free, no key for a few requests): ISIN → tickers and exchanges."""
from __future__ import annotations

from flask_babel import gettext as _

from .base import Broken, Candidate, NotFound, post_json

SITE = "openfigi"
URL = "https://api.openfigi.com/v3/mapping"
# OpenFIGI exchange codes → Yahoo's suffix, so the price can then be read from Yahoo
EXCHANGES = {"IM": (".MI", "Milano"), "GY": (".DE", "Xetra"), "GR": (".DE", "Xetra"), "GF": (".F", "Francoforte"),
             "LN": (".L", "Londra"), "NA": (".AS", "Amsterdam"), "FP": (".PA", "Parigi"), "SW": (".SW", "Zurigo"),
             "SM": (".MC", "Madrid"), "US": ("", "USA"), "UN": ("", "NYSE"), "UW": ("", "Nasdaq")}


def asset_class(item: dict) -> str | None:
    sector, kind = (item.get("marketSector") or "").lower(), (item.get("securityType") or "").lower()
    if "option" in kind or "future" in kind or "warrant" in kind:
        return "Derivato"
    if sector in ("govt", "corp", "muni", "mtge"):
        return "Obbligazione"
    if "etp" in kind or "etf" in kind:
        return "ETF"
    if "fund" in kind:
        return "Fondo"
    if sector == "equity":
        return "Azione"
    return None


def find(isin: str) -> list[Candidate]:
    answer = post_json(SITE, URL, [{"idType": "ID_ISIN", "idValue": isin}])
    if not isinstance(answer, list) or not answer or not isinstance(answer[0], dict):
        raise Broken(_("risposta inattesa"))
    rows = answer[0].get("data")
    if not rows:
        raise NotFound(_("nessun risultato"))
    found, seen = [], set()
    for item in rows:
        exchange = EXCHANGES.get(item.get("exchCode") or "")
        kind = asset_class(item)
        ticker = (item.get("ticker") or "").strip().replace(" ", "-")
        if not exchange or not kind or not ticker:
            continue
        symbol = ticker + exchange[0]
        if symbol in seen:
            continue
        seen.add(symbol)
        found.append(Candidate(symbol, item.get("name") or ticker, kind, exchange[1], isin, source=SITE))
    if not found:
        raise NotFound(_("nessuna quotazione su una borsa conosciuta"))
    return found
