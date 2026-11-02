"""
Price sources of the user's own (F22): for a fund or a policy that none of the sites knows, an address with {ISIN},
{TICKER} or {DATA} and where to read the price in what it returns:

- JSON: a path of keys and positions, «data.price» or «quotes.0.nav» (and, if given, the path of its date);
- HTML: the text after a label («Prezzo ultimo contratto»), or a regular expression with the price in its first group;
- CSV: the column, by name or number, of the last row.

Only http and https addresses on the internet (never this computer or the local network), at most 2 MB, one request a
second per source, and nothing sent but the ISIN or the ticker in the address.
"""
from __future__ import annotations

import csv
import io
import ipaddress
import re
import socket
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date

from flask_babel import gettext as _

from app.services import settings_store

from . import base
from .base import Broken, NotFound, Quote

SETTING = "prices.custom_sources"
PREFIX = "custom:"
FORMATS = ("json", "html", "csv")
MAX_BYTES = 2_000_000
MAX_SOURCES = 20
NAME = re.compile(r"^[\w .\-]{1,40}$")


@dataclass
class CustomSource:
    name: str
    url: str
    format: str = "json"
    path: str = ""            # JSON keys, the HTML label or regular expression, the CSV column
    date_path: str = ""       # JSON only: where the date of the price is (empty: today)
    currency: str = "EUR"
    divide_100: bool = False  # bonds quoted in % of the face value

    @property
    def key(self) -> str:
        return PREFIX + self.name


def all_sources() -> list[CustomSource]:
    saved = settings_store.get_json(SETTING, [], expect=list)
    fields = set(CustomSource.__dataclass_fields__)
    return [CustomSource(**{k: v for k, v in row.items() if k in fields}) for row in saved
            if isinstance(row, dict) and row.get("name") and row.get("url")]


def get(name: str) -> CustomSource | None:
    return next((s for s in all_sources() if s.name == name), None)


def labels() -> dict[str, str]:
    """{«custom:name»: name} for the choice of a holding's price source."""
    return {s.key: s.name for s in all_sources()}


def validate(source: CustomSource) -> CustomSource:
    source.name = " ".join((source.name or "").split())
    if not NAME.match(source.name):
        raise ValueError(_("Nome della fonte: fino a 40 lettere, cifre, spazi, punti o trattini."))
    source.url = (source.url or "").strip()
    parsed = urllib.parse.urlparse(source.url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(_("Indirizzo: deve iniziare con https:// (o http://)."))
    if not any(token in source.url for token in ("{ISIN}", "{TICKER}")):
        raise ValueError(_("Indirizzo: metti {ISIN} o {TICKER} dove va il codice del titolo."))
    if source.format not in FORMATS:
        raise ValueError(_("Formato: JSON, HTML o CSV."))
    source.path = (source.path or "").strip()
    if not source.path:
        raise ValueError(_("Indica dove leggere il prezzo (percorso, etichetta o colonna)."))
    if source.format == "html" and source.path.startswith("re:"):
        try:
            re.compile(source.path[3:])
        except re.error:
            raise ValueError(_("Espressione regolare non valida.")) from None
    source.date_path = (source.date_path or "").strip()
    source.currency = (source.currency or "EUR").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", source.currency):
        raise ValueError(_("Valuta: il codice di tre lettere (EUR, USD, GBP…)."))
    return source


def save(source: CustomSource, replacing: str | None = None) -> None:
    validate(source)
    rest = [s for s in all_sources() if s.name not in (source.name, replacing)]
    if len(rest) >= MAX_SOURCES:
        raise ValueError(_("Al massimo %(count)s fonti personalizzate.", count=MAX_SOURCES))
    settings_store.set_json(SETTING, [asdict(s) for s in [*rest, source]])


def delete(name: str) -> None:
    settings_store.set_json(SETTING, [asdict(s) for s in all_sources() if s.name != name])


# ── Reading ────────────────────────────────────────────────────────────────────

def address(source: CustomSource, isin: str | None, ticker: str | None, today: date | None = None) -> str:
    if "{ISIN}" in source.url and not isin:
        raise ValueError(_("serve l'ISIN"))
    if "{TICKER}" in source.url and not ticker:
        raise ValueError(_("serve il ticker"))
    quote = urllib.parse.quote
    return (source.url.replace("{ISIN}", quote(isin or "")).replace("{TICKER}", quote(ticker or ""))
            .replace("{DATA}", (today or date.today()).isoformat()))


def check_public(url: str) -> None:
    """Never this computer or the local network: every address the name points to must be on the internet."""
    host = urllib.parse.urlparse(url).hostname or ""
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError:
        raise NotFound(_("indirizzo «%(host)s» non trovato", host=host)) from None
    for raw in addresses:
        ip = ipaddress.ip_address(raw.split("%")[0])
        if not ip.is_global:
            raise ValueError(_("l'indirizzo «%(host)s» è nella rete locale: non consentito", host=host))


def download(source: CustomSource, url: str) -> str:
    check_public(url)
    base._wait(source.key)
    request = urllib.request.Request(url, headers={"User-Agent": base.AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=base.TIMEOUT) as response:  # noqa: S310 - checked above
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise Broken(_("risposta troppo grande"))
    return body.decode("utf-8", errors="replace")


def _walk(data, path: str):
    for part in [p for p in re.split(r"[.\[\]]", path) if p]:
        if isinstance(data, list) and part.lstrip("-").isdigit() and -len(data) <= int(part) < len(data):
            data = data[int(part)]
        elif isinstance(data, dict) and part in data:
            data = data[part]
        else:
            raise Broken(_("«%(path)s» non trovato nella risposta", path=path))
    return data


def _from_json(source: CustomSource, text: str) -> tuple[str, str | None]:
    import json

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise Broken(_("risposta non leggibile")) from None
    raw_day = str(_walk(data, source.date_path)) if source.date_path else None
    return str(_walk(data, source.path)), raw_day


def _from_html(source: CustomSource, text: str) -> tuple[str, str | None]:
    if source.path.startswith("re:"):
        found = re.search(source.path[3:], text, re.S)
        if not found:
            raise Broken(_("l'espressione non trova nulla nella pagina"))
        return (found.group(1) if found.groups() else found.group(0)), None
    value = base.after_label(text, source.path)
    if value is None:
        raise Broken(_("«%(path)s» non trovato nella pagina", path=source.path))
    return value, None


def _from_csv(source: CustomSource, text: str) -> tuple[str, str | None]:
    sample = text[:2000]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    rows = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter) if any(cell.strip() for cell in row)]
    if len(rows) < 2:
        raise Broken(_("il CSV non ha righe"))
    header = [cell.strip().lower() for cell in rows[0]]
    column = int(source.path) - 1 if source.path.isdigit() else (
        header.index(source.path.lower()) if source.path.lower() in header else -1)
    if not 0 <= column < len(rows[-1]):
        raise Broken(_("colonna «%(path)s» non trovata", path=source.path))
    return rows[-1][column], None


READERS = {"json": _from_json, "html": _from_html, "csv": _from_csv}


def read(source: CustomSource, text: str, today: date | None = None) -> Quote:
    raw, raw_day = READERS[source.format](source, text)
    price = base.number(raw)
    if price is None or price <= 0:
        raise Broken(_("«%(value)s» non è un prezzo", value=raw[:40]))
    if source.divide_100:
        price = price / 100
    return Quote(price, base.day(raw_day) or today or date.today(), source.currency)


def quote(source: CustomSource, isin: str | None, ticker: str | None) -> Quote:
    return read(source, download(source, address(source, isin, ticker)))
