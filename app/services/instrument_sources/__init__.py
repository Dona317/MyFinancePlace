"""
The sites where instruments are looked up by ISIN and, for bonds, funds and ETFs that Yahoo does not quote, priced
(F19): one reader per site, chosen and ordered in Impostazioni → Fonti dei prezzi. Yahoo itself and Stooq live in
price_feed.
"""
from __future__ import annotations

from app.services import settings_store
from app.services.i18n import _l

from . import borsaitaliana, justetf, morningstar, openfigi
from .base import Broken, Candidate, NotFound, Quote  # noqa: F401

SETTING = "prices.sources"
NAMES = {"yahoo": "Yahoo Finance", "openfigi": "OpenFIGI", "justetf": "justETF", "borsaitaliana": "Borsa Italiana",
         "morningstar": "Morningstar"}
DESCRIPTIONS = {
    "yahoo": _l("azioni, ETF, fondi e derivati di molte borse: ricerca, prezzo e storico"),
    "openfigi": _l("da ISIN a ticker e borsa (Bloomberg), per azioni, ETF, obbligazioni e derivati"),
    "justetf": _l("ETF europei: nome e prezzo in euro"),
    "borsaitaliana": _l("BTP e obbligazioni del MOT, ETF, azioni e certificati di Milano: anche il prezzo"),
    "morningstar": _l("fondi comuni: il NAV (la fonte più fragile)"),
}
DEFAULT_ORDER = ["yahoo", "openfigi", "justetf", "borsaitaliana", "morningstar"]
DEFAULT_OFF = {"morningstar"}
FINDERS = {"openfigi": openfigi.find, "justetf": justetf.find, "borsaitaliana": borsaitaliana.find,
           "morningstar": morningstar.find}
QUOTES = {"justetf": justetf.quote, "borsaitaliana": borsaitaliana.quote, "morningstar": morningstar.quote}


def chosen() -> list[str]:
    """The sites switched on, in the user's order."""
    saved = settings_store.get_json(SETTING, {}, expect=dict)
    order = [s for s in saved.get("order") or [] if s in NAMES]
    order += [s for s in DEFAULT_ORDER if s not in order]
    enabled = saved.get("enabled")
    on = set(enabled) if isinstance(enabled, list) else set(DEFAULT_ORDER) - DEFAULT_OFF
    return [s for s in order if s in on]


def save(order: list[str], enabled: set[str]) -> None:
    clean = [s for s in order if s in NAMES]
    clean += [s for s in DEFAULT_ORDER if s not in clean]
    settings_store.set_json(SETTING, {"order": clean, "enabled": [s for s in clean if s in enabled]})


def settings_rows() -> list[dict]:
    saved = settings_store.get_json(SETTING, {}, expect=dict)
    order = [s for s in saved.get("order") or [] if s in NAMES]
    order += [s for s in DEFAULT_ORDER if s not in order]
    on = set(chosen())
    return [{"key": s, "name": NAMES[s], "description": DESCRIPTIONS[s], "position": i + 1, "on": s in on}
            for i, s in enumerate(order)]
