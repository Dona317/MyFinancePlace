"""
«Incolla il link» (23 Nov 2026, F112): the past closes of an instrument read from the page of a site the user pastes,
saved with the instrument in the market data store — shared by every archive, like the closes — so the daily update
reads it again; and justETF as the third automatic source of the
filler (after Yahoo and Stooq) for the instruments with an ISIN.

    a link ──▶ the site and the ISIN in it
                 ├─ justETF: its chart data (daily closes in euro, weekends dropped)
                 ├─ Borsa Italiana, Morningstar, any page with an ISIN in it: the same ISIN read from justETF
                 └─ Investing.com: no link reading, its «Dati storici» CSV loaded instead

Only the ISIN is sent, to justETF's fixed address: the link pasted is never opened.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app.services import market_data, settings_store
from app.services.i18n import gettext as _

KEY = "history_links"
TIMEOUT = 25
JUSTETF_CHART = ("https://www.justetf.com/api/etfs/{isin}/performance-chart?locale=it&currency={currency}"
                 "&valuesType=MARKET_VALUE&reduceData=false&includeDividends=false&features=DIVIDENDS"
                 "&dateFrom={start}&dateTo={end}")
CURRENCIES = ("EUR", "USD", "GBP", "CHF")  # what justETF quotes in (London's pence are not among them)
ISIN = re.compile(r"(?<![A-Z0-9])([A-Z]{2}[A-Z0-9]{9}[0-9])(?![A-Z0-9])")
SITES = {  # the end of the host → (key, name)
    "justetf.com": ("justetf", "justETF"),
    "borsaitaliana.it": ("borsaitaliana", "Borsa Italiana"),
    "morningstar.it": ("morningstar", "Morningstar"),
    "morningstar.com": ("morningstar", "Morningstar"),
    "investing.com": ("investing", "Investing.com"),
}


@dataclass(frozen=True)
class Link:
    url: str
    site: str        # SITES key ("other" for any other site)
    name: str        # the site, as shown
    isin: str        # what is read, from justETF

    @property
    def direct(self) -> bool:
        """Read from the site itself (justETF) rather than the same ISIN from justETF."""
        return self.site == "justetf"


def recognise(url: str) -> Link:
    """The site and the ISIN of a pasted link; a message saying what to do when it cannot be read."""
    url = (url or "").strip()
    parts = urllib.parse.urlsplit(url if "://" in url else f"https://{url}")
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or "." not in host:
        raise ValueError(_("Non sembra un link: incolla l'indirizzo della pagina del titolo (https://…)."))
    site, name = next((v for end, v in SITES.items() if host == end or host.endswith("." + end)), ("other", host))
    if site == "investing":
        raise ValueError(_("Investing.com non si legge da un link: nella pagina «Dati storici» del titolo scarica il "
                           "CSV e caricalo con «Carica lo storico» (Portfolio → Prezzi)."))
    found = ISIN.search(urllib.parse.unquote(f"{parts.path}?{parts.query}").upper())
    if not found or not _isin_ok(found.group(1)):
        raise ValueError(_("Nel link di %(site)s non trovo un codice ISIN: apri la pagina del titolo (quella con "
                           "l'ISIN nell'indirizzo, come su justETF o Borsa Italiana) e incolla quel link.", site=name))
    return Link(url, site, name, found.group(1))


def _isin_ok(code: str) -> bool:
    """The ISIN check digit (Luhn on the letters as numbers)."""
    digits = "".join(str(int(c, 36)) for c in code[:-1])
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch) * (2 if i % 2 == 0 else 1)
        total += n - 9 if n > 9 else n
    return (10 - total % 10) % 10 == int(code[-1])


# ── justETF ────────────────────────────────────────────────────────────────────

def parse_justetf(data: dict, code: str = "EUR") -> market_data.Daily:
    """The daily values of justETF's chart, in the currency asked: weekends (the Friday repeated) left out."""
    points = {}
    for row in (data or {}).get("series") or []:
        try:
            day = date.fromisoformat(str(row.get("date")))
            value = Decimal(str((row.get("value") or {}).get("raw")))
        except (ValueError, TypeError, InvalidOperation):
            continue
        if day.weekday() < 5 and value > 0:
            points[day] = (day, value, None)
    return market_data.Daily(code, None, None, [points[d] for d in sorted(points)])  # no exchange: justETF's own price


def _json(address: str) -> dict:
    request = urllib.request.Request(address, headers={"User-Agent": "Mozilla/5.0 MyFinancePlace",
                                                       "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - fixed https endpoint
        return json.loads(response.read().decode("utf-8", errors="replace"))


def read_justetf(isin: str, start: date, end: date, code: str = "EUR", fetch=None) -> market_data.Daily:
    daily = parse_justetf((fetch or _json)(JUSTETF_CHART.format(isin=isin, currency=code, start=start.isoformat(),
                                                                end=end.isoformat())), code)
    if not daily.points:
        raise ValueError("justETF: nessuna chiusura")
    return daily


def quoted_in(symbol: str) -> str | None:
    """The currency to read an instrument in from justETF: the one its closes already have (EUR for a new one);
    None when justETF does not quote in it (London's pence): its closes would not match."""
    row = next((r for r in market_data.overview() if r["symbol"] == symbol), None) if market_data.available() else None
    code = (row or {}).get("currency") or "EUR"
    return code if code in CURRENCIES else None


# ── The links saved with the instruments ───────────────────────────────────────

def links() -> dict[str, str]:
    """{symbol: link pasted}, of every archive (the market data store); the links an archive kept in its own
    settings before (23 Nov 2026) moved there the first time."""
    legacy = settings_store.get_json(KEY, {}, expect=dict)
    if legacy:
        for symbol, url in legacy.items():
            market_data.set_link(symbol, url)
        settings_store.set_json(KEY, {})
    return market_data.links()


def isin_of(symbol: str) -> str | None:
    url = links().get(symbol)
    return recognise(url).isin if url else None


def forget(symbol: str) -> None:
    if symbol in links():
        market_data.set_link(symbol, None)


def sources_for(target) -> list[tuple[str, object]]:
    """justETF as a source of the filler for one instrument: the ISIN of its link, else its own ISIN."""
    try:
        isin = isin_of(target.symbol)
    except ValueError:  # a link saved before, no longer readable: its own ISIN
        isin = None
    isin = isin or (target.isin or "").strip().upper() or None
    code = quoted_in(target.symbol) if isin else None
    if not code:
        return []
    return [("justetf", lambda _symbol, start, end: read_justetf(isin, start, end, code))]


@dataclass
class Applied:
    link: Link
    added: int
    first: date | None
    last: date | None


def apply(symbol: str, url: str, today: date | None = None, fetch=None) -> Applied:
    """Save the link with the instrument and read its whole history now (from when the instrument is needed)."""
    from app.services import history_filler  # the filler uses this module too

    today = today or date.today()
    link = recognise(url)
    target = next((t for t in history_filler.targets(today, resolve=False) if t.symbol == symbol), None)
    if target is None:
        raise ValueError(_("«%(symbol)s» non è tra i titoli in portafoglio.", symbol=symbol))
    if target.isin and target.isin.strip().upper() != link.isin:
        raise ValueError(_("Il link è dell'ISIN %(link)s, ma %(symbol)s ha ISIN %(own)s: controlla di aver aperto "
                           "la pagina giusta.", link=link.isin, symbol=symbol, own=target.isin))
    code = quoted_in(symbol)
    if not code:
        raise ValueError(_("%(symbol)s è quotato in pence (GBp): justETF non lo dà in questa valuta, caricane lo "
                           "storico da un file CSV.", symbol=symbol))
    daily = read_justetf(link.isin, target.start - timedelta(days=7), today, code, fetch=fetch)
    added = market_data.store(symbol, daily, link.isin, target.name, source="justetf")
    market_data.set_link(symbol, link.url)
    days = [p[0] for p in daily.points]
    return Applied(link, added, min(days), max(days))
