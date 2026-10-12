"""
What the instrument sources share (F19): the network (one request a second per site at most, a browser-like user
agent, nothing sent but the ISIN), the shape of a result, and small readers for HTML pages.

The pages of justETF, Borsa Italiana and Morningstar are web pages, not APIs: when a site changes its layout the reader
raises Broken («la pagina è cambiata») and the other sources go on.
"""
from __future__ import annotations

import html
import json
import re
import threading
import time
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask_babel import gettext as _

TIMEOUT = 15
MIN_INTERVAL = 1.0  # seconds between two requests to the same site
AGENT = "Mozilla/5.0 (compatible; MyFinancePlace)"
_last: dict[str, float] = {}
_lock = threading.Lock()


class NotFound(ValueError):
    """The site does not know the instrument."""


class Broken(ValueError):
    """The site answered, but not as expected: its page or API changed."""


@dataclass
class Candidate:
    """An instrument found by a search: what fills the holding's form."""
    symbol: str
    name: str
    asset_class: str
    exchange: str | None = None
    isin: str | None = None
    source: str = "yahoo"
    price_source: str = "auto"  # where its price is read from, when chosen
    currency: str | None = None

    def as_dict(self) -> dict:
        return {"symbol": self.symbol, "name": self.name, "asset_class": self.asset_class, "exchange": self.exchange,
                "isin": self.isin, "source": self.source, "price_source": self.price_source, "currency": self.currency}


@dataclass
class Quote:
    price: Decimal
    on: date
    currency: str = "EUR"


def _wait(site: str) -> None:
    with _lock:
        pause = _last.get(site, 0.0) + MIN_INTERVAL - time.monotonic()
        if pause > 0:
            time.sleep(pause)
        _last[site] = time.monotonic()


def fetch(url: str, payload: bytes | None = None, content_type: str | None = None) -> str:
    headers = {"User-Agent": AGENT, "Accept": "application/json, text/html, */*", "Accept-Language": "it-IT,it;q=0.9"}
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST" if payload else "GET")
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - fixed https endpoints
        return response.read().decode("utf-8", errors="replace")


def get_text(site: str, url: str) -> str:
    _wait(site)
    return fetch(url)


def get_json(site: str, url: str):
    try:
        return json.loads(get_text(site, url))
    except json.JSONDecodeError:
        raise Broken(_("risposta non leggibile")) from None


def post_json(site: str, url: str, body) -> object:
    _wait(site)
    try:
        return json.loads(fetch(url, json.dumps(body).encode(), "application/json"))
    except json.JSONDecodeError:
        raise Broken(_("risposta non leggibile")) from None


# ── Reading pages ──────────────────────────────────────────────────────────────

def text_of(fragment: str) -> str:
    """The visible text of an HTML fragment, spaces collapsed."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def first_heading(page: str) -> str | None:
    found = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S | re.I)
    return text_of(found.group(1)) or None if found else None


def after_label(page: str, *labels: str, window: int = 400) -> str | None:
    """The first piece of text that follows one of the labels (the value of a «label: value» row of a table)."""
    for label in labels:
        found = re.search(re.escape(label), page, re.I)
        if found:
            rest = page[found.end():found.end() + window]
            for piece in re.split(r"<[^>]+>", rest):
                piece = " ".join(html.unescape(piece).split()).strip(": ")
                if piece:
                    return piece
    return None


def number(text: str | None) -> Decimal | None:
    """«1.234,56», «1,234.56», «99,85 %» or «123.4» → Decimal."""
    if not text:
        return None
    raw = re.sub(r"[^\d,.\-]", "", text)
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".") if raw.rfind(",") > raw.rfind(".") else raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def day(text: str | None) -> date | None:
    """«09/10/2026», «09/10/26 - 17.35.00» or «2026-10-09» → date."""
    if not text:
        return None
    found = re.search(r"(\d{4})-(\d{2})-(\d{2})|(\d{1,2})/(\d{1,2})/(\d{2,4})", text)
    if not found:
        return None
    if found.group(1):
        return date(int(found.group(1)), int(found.group(2)), int(found.group(3)))
    year = int(found.group(6))
    year += 2000 if year < 100 else 0
    try:
        return datetime(year, int(found.group(5)), int(found.group(4))).date()
    except ValueError:
        return None
