"""
Look-through of the funds («spacchettamento», F57): what an ETF or a fund really holds, by country, sector, currency
and company, read from the holdings file the user downloads from the issuer's site (iShares, Vanguard, Xtrackers,
Amundi, SPDR…) or typed by hand (the top 10 countries and sectors). Nothing is fetched from the internet.

The reader is tolerant: it finds the header row among the lines above it (fund name, «Fund Holdings as of…»), picks
the columns by name (English and Italian), reads numbers in both formats (4.63, 4,63, 0.0463 when the weights are
fractions), aggregates the rows by country (ISO code, from the names Babel knows in English and Italian), sector
(the usual Italian names), currency and asset class, and keeps the 25 largest companies.

The portfolio's exposure is Σ value of the holding × weight. A holding without look-through data counts with what
its form says (region, sector, quote currency, asset class; a share is its own company); what is left is
«Senza dati». The overlap of two funds is the sum, over the companies both hold, of the smaller weight.
"""
from __future__ import annotations

import html
import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from itertools import combinations

from babel import Locale
from flask_babel import gettext as _

from app.extensions import db
from app.models.wealth import Holding, HoldingExposure
from app.services import asset_classes, fund_facts, statement_readers
from app.services.i18n import N_

KINDS = ("country", "sector", "currency", "holding", "asset_class")
TOP_COMPANIES = 25   # companies kept from a file
TOP_CHART = 10       # countries and sectors on the charts, then «Altri»
TOP_TABLE = 20       # companies in the portfolio's table
MANUAL_ROWS = 10     # countries and sectors typed by hand
MANUAL = N_("a mano")
UNCOVERED = N_("Senza dati")
OTHERS = N_("Altri")
FUNDS = {"ETF", "Fondo comune", "Fondo assicurativo", "Fondo Pensione"}  # their quote currency says nothing

# New sector names (the others are composition.SECTORS)
N_("Beni di consumo discrezionali")
N_("Beni di consumo di base")
N_("Servizi di comunicazione")


class LookThroughError(ValueError):
    """The file or the typed data cannot be used; the message is shown to the user."""


# ── Text keys ──────────────────────────────────────────────────────────────────

def _key(text) -> str:
    """Lower case, no accents, «&» as «and», punctuation as spaces (the «%» stays): «Weight (%)» → «weight %»."""
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    text = text.replace("&", " and ").replace("'", " ")
    return " ".join(re.sub(r"[^a-z0-9%]+", " ", text).split())


# Header names of each column, most specific first (compared as _key)
COLUMNS = {
    "weight": ["weight %", "weight", "weighting", "weighting %", "% weight", "ponderazione %", "ponderazione",
               "peso %", "peso", "% peso", "% of funds", "% of fund", "% of net assets", "% of market value",
               "% of nav", "% nav", "percent of fund", "percent of net assets", "% del fondo", "% patrimonio",
               "% del patrimonio", "% patrimonio netto", "% sul patrimonio", "% sul totale", "percentuale",
               "allocation %", "% allocation", "fund weight", "weight of fund", "market value %"],
    "name": ["name", "nome", "holding name", "holding", "security name", "security", "security description",
             "description", "descrizione", "denominazione", "constituent", "constituent name", "company",
             "company name", "societa", "titolo", "nome del titolo", "nome titolo", "instrument", "strumento",
             "issuer name", "emittente"],
    "sector": ["sector", "settore", "gics sector", "settore gics", "sector classification", "industry classification",
               "industry", "industria", "sector name"],
    "country": ["location", "localita", "country", "paese", "nazione", "country of risk", "location of risk",
                "trade country name", "country name", "country of domicile", "country of issue", "paese di rischio",
                "area geografica", "region", "geography"],
    "currency": ["market currency", "valuta di mercato", "currency", "valuta", "local currency", "trading currency",
                 "currency code", "valuta locale", "currency of denomination"],
    "asset_class": ["asset class", "classe di attivo", "classe di attivita", "asset type", "type of security",
                    "security type", "tipo di titolo", "tipologia", "tipo strumento", "instrument type"],
    "value": ["market value", "valore di mercato", "market value eur", "market value usd", "market value base",
              "controvalore", "valore", "value", "notional value", "valore nozionale"],
}
WEIGHT_WORDS = ("weight", "ponderazione", "peso", "% of", "percent")


def _columns(header: list) -> dict[str, int]:
    """The index of each column found in a header row: exact names first, then a weight column by its words."""
    keys = [_key(cell) for cell in header]
    found: dict[str, int] = {}
    for field_name, names in COLUMNS.items():
        for name in names:
            if name in keys and keys.index(name) not in found.values():
                found[field_name] = keys.index(name)
                break
    if "weight" not in found:
        for i, k in enumerate(keys):
            if i not in found.values() and any(word in k for word in WEIGHT_WORDS):
                found["weight"] = i
                break
    return found


# ── Numbers and dates ──────────────────────────────────────────────────────────

def number(value) -> float | None:
    """A number from a cell: 4.63, «4,63», «1,234.56», «1.234,56», «4.63%», «(0.12)»; None when not one."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        result = float(value)
        return result if math.isfinite(result) else None
    text = str(value).strip().replace("%", "").replace(" ", "").replace(" ", "").replace("€", "").replace("$", "")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    elif text.count(",") > 1:
        text = text.replace(",", "")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    else:
        text = text.replace(",", ".")
    if not re.fullmatch(r"[+-]?\d+(\.\d+)?([eE][+-]?\d+)?", text):
        return None
    result = float(text)
    return -result if negative else result


MONTHS = {"jan": 1, "gen": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "mag": 5, "jun": 6, "giu": 6, "jul": 7,
          "lug": 7, "aug": 8, "ago": 8, "sep": 9, "set": 9, "oct": 10, "ott": 10, "nov": 11, "dec": 12, "dic": 12}


def _date_in(value) -> date | None:
    """The first date in a cell: a date value, 2026-11-07, 07/11/2026, 07.11.2026, «Nov 07, 2026», «07/nov/2026»,
    «7 novembre 2026»."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "")
    found = None
    if m := re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text):
        found = (int(m[1]), int(m[2]), int(m[3]))
    elif m := re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", text):
        day, month = int(m[1]), int(m[2])
        if month > 12 >= day:  # month first (US)
            day, month = month, day
        found = (int(m[3]), month, day)
    elif m := re.search(r"\b(\d{1,2})[\s./-]+([A-Za-z]{3})[a-z]*\.?[\s./-]+(\d{4})\b", text):
        found = (int(m[3]), MONTHS.get(m[2].lower()), int(m[1]))
    elif m := re.search(r"\b([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\b", text):
        found = (int(m[3]), MONTHS.get(m[1].lower()), int(m[2]))
    if not found or not found[1]:
        return None
    try:
        return date(*found)
    except ValueError:
        return None


# ── Names: countries, sectors, asset classes, companies ────────────────────────

NOT_TERRITORIES = {"ZZ", "UN", "QO", "XA", "XB", "EZ"}
COUNTRY_ALIASES = {
    "usa": "US", "us": "US", "u s": "US", "united states of america": "US", "stati uniti d america": "US",
    "america": "US", "uk": "GB", "great britain": "GB", "england": "GB", "gran bretagna": "GB", "inghilterra": "GB",
    "hong kong": "HK", "macau": "MO", "macao": "MO", "korea": "KR", "korea south": "KR", "korea republic of": "KR",
    "republic of korea": "KR", "corea": "KR", "taiwan province of china": "TW", "czech republic": "CZ",
    "repubblica ceca": "CZ", "russian federation": "RU", "the netherlands": "NL", "holland": "NL", "olanda": "NL",
    "turkey": "TR", "viet nam": "VN", "ivory coast": "CI", "china mainland": "CN", "mainland china": "CN",
    "european union": "EU", "unione europea": "EU", "iran islamic republic of": "IR", "slovak republic": "SK",
}


@lru_cache(maxsize=1)
def _country_index() -> dict[str, str]:
    index = {}
    for language in ("en", "it"):
        for code, name in Locale.parse(language).territories.items():
            if len(code) == 2 and code.isalpha() and code not in NOT_TERRITORIES:
                index[_key(name)] = code
    index.update(COUNTRY_ALIASES)
    return index


@lru_cache(maxsize=1)
def _country_codes() -> frozenset[str]:
    return frozenset(c for c in Locale.parse("en").territories if len(c) == 2 and c.isalpha()) - NOT_TERRITORIES


def country_code(text) -> str | None:
    """The ISO code of a country named in English or Italian («Stati Uniti», «United States», «US»)."""
    raw = str(text or "").strip()
    if re.fullmatch(r"[A-Za-z]{2}", raw) and raw.upper() in _country_codes():
        return raw.upper()
    return _country_index().get(_key(raw))


def country_label(name: str) -> str:
    """A stored country (ISO code) in the interface's language; a region or another name translated or as it is."""
    if re.fullmatch(r"[A-Z]{2}", name or ""):
        return fund_facts.country_name(name)
    return _(name) if name else name


SECTOR_NAMES = {
    "Tecnologia": ["information technology", "technology", "tech", "it", "tecnologia", "tecnologia dell informazione",
                   "informatica", "semiconductors", "software"],
    "Finanza": ["financials", "financial", "finance", "financial services", "finanza", "finanziari", "finanziario",
                "servizi finanziari", "banks", "banche"],
    "Salute": ["health care", "healthcare", "health", "salute", "sanita", "assistenza sanitaria"],
    "Energia": ["energy", "energia"],
    "Utilities": ["utilities", "utility", "servizi di pubblica utilita", "servizi pubblici", "pubblica utilita"],
    "Industria": ["industrials", "industrial", "industriali", "industria", "beni industriali"],
    "Beni di consumo discrezionali": ["consumer discretionary", "consumer cyclical", "consumer cyclicals",
                                      "beni voluttuari", "consumi discrezionali", "beni di consumo discrezionali",
                                      "beni di consumo voluttuari"],
    "Beni di consumo di base": ["consumer staples", "consumer defensive", "consumer non cyclicals",
                                "beni di prima necessita", "beni di consumo di base", "consumi di base",
                                "beni di consumo primari"],
    "Servizi di comunicazione": ["communication", "communications", "communication services",
                                 "telecommunication services", "telecommunications", "telecommunication",
                                 "comunicazione", "servizi di comunicazione", "telecomunicazioni",
                                 "servizi di telecomunicazione", "media"],
    "Materie prime": ["materials", "basic materials", "materiali", "materie prime", "materiali di base"],
    "Immobiliare": ["real estate", "immobiliare", "beni immobili", "reit", "reits"],
    "Liquidità": ["cash and or derivatives", "cash and derivatives", "cash", "liquidita", "liquidita e o derivati",
                  "liquidita e derivati", "cash and cash equivalents", "derivatives", "derivati", "money market"],
    "Obbligazioni governative": ["treasuries", "treasury", "government", "governativi", "titoli di stato",
                                 "government bonds", "sovereign", "obbligazioni governative"],
    "Obbligazioni societarie": ["corporate", "corporates", "corporate bonds", "obbligazioni societarie",
                                "societari"],
}
SECTOR_INDEX = {key: name for name, keys in SECTOR_NAMES.items() for key in keys}

ASSET_CLASS_NAMES = {
    asset_classes.EQUITY: ["equity", "equities", "stock", "stocks", "common stock", "azioni", "azionario", "shares"],
    asset_classes.BONDS: ["fixed income", "bond", "bonds", "obbligazioni", "obbligazionario", "reddito fisso"],
    asset_classes.CASH: ["cash", "money market", "liquidita", "monetario", "cash collateral and margins", "fx",
                         "currency", "valuta", "cash and or derivatives"],
    asset_classes.REAL_ESTATE: ["real estate", "reit", "immobiliare"],
    asset_classes.COMMODITIES: ["commodity", "commodities", "materie prime"],
}
ASSET_CLASS_INDEX = {key: name for name, keys in ASSET_CLASS_NAMES.items() for key in keys}


def sector_name(text) -> str | None:
    raw = " ".join(str(text or "").split())
    if not raw or raw in ("-", "—"):
        return None
    return SECTOR_INDEX.get(_key(raw), raw)


def _asset_class_name(text) -> str | None:
    raw = " ".join(str(text or "").split())
    if not raw or raw in ("-", "—"):
        return None
    return ASSET_CLASS_INDEX.get(_key(raw), raw)


def _currency(text) -> str | None:
    raw = str(text or "").strip().upper()
    return raw if re.fullmatch(r"[A-Z]{3}", raw) else None


COMPANY_NOISE = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|sa|ag|nv|se|spa|ab|asa|"
                           r"as|oyj|kgaa|class [a-z]|cl [a-z]|cls [a-z]|ord|shs|reg|adr|the|group|holdings?|"
                           r"registered|common|stock|non voting|pref|preference)\b")


def company_key(name: str) -> str:
    """The company behind a security's name: «APPLE INC», «Apple Inc.» and «Apple» are the same; so are the
    classes of one company (Alphabet A and C)."""
    key = " ".join(COMPANY_NOISE.sub(" ", _key(name)).split())
    return key or _key(name)


# ── Reading a file ─────────────────────────────────────────────────────────────

ISSUERS = [("iShares", r"ishares|blackrock"), ("Vanguard", r"vanguard"), ("Xtrackers", r"xtrackers|dws"),
           ("Amundi", r"amundi|lyxor"), ("SPDR", r"spdr|state street|ssga"), ("Invesco", r"invesco"),
           ("WisdomTree", r"wisdomtree"), ("VanEck", r"vaneck")]


@dataclass
class Parsed:
    """What a holdings file says: {kind: {name: weight %}}, its date, its source and how many rows it read."""
    exposures: dict[str, dict[str, float]] = field(default_factory=dict)
    as_of: date | None = None
    source: str = ""
    rows: int = 0


def _rows_of(filename: str, raw: bytes) -> list[list[list]]:
    """The tables of the file: spreadsheets (XLSX, XLS, ODS, the XML «Excel» of iShares, HTML saved as .xls), CSV."""
    if b"urn:schemas-microsoft-com:office:spreadsheet" in raw[:4096]:
        return [_spreadsheet_xml(statement_readers.decode_text(raw))]
    try:
        document = statement_readers.read_document(filename, raw)
    except statement_readers.UnsupportedFile as exc:
        raise LookThroughError(str(exc)) from None
    return document.tables


def _spreadsheet_xml(text: str) -> list[list]:
    """The rows of the first sheet of an XML Spreadsheet 2003 (what iShares downloads as «.xls»)."""
    sheet = re.split(r"</(?:ss:)?Worksheet>", text, maxsplit=1)[0]
    rows = []
    for row in re.findall(r"<(?:ss:)?Row\b[^>]*>(.*?)</(?:ss:)?Row>", sheet, flags=re.S):
        cells = re.findall(r"<(?:ss:)?Cell\b[^>]*?(?:/>|>(.*?)</(?:ss:)?Cell>)", row, flags=re.S)
        rows.append([html.unescape(re.sub(r"<[^>]+>", "", cell)).strip() for cell in cells])
    return rows


def _header(table: list[list]) -> tuple[int, dict[str, int]] | None:
    """The first row (of the first 60) that names a security column and a weight (or value) column."""
    for i, row in enumerate(table[:60]):
        if sum(1 for cell in row if str(cell or "").strip()) < 2:
            continue
        columns = _columns(row)
        if "name" in columns and ("weight" in columns or "value" in columns):
            return i, columns
    return None


def _issuer(filename: str, preamble: list[list], holding: Holding | None) -> str:
    text = " ".join([filename] + [str(c) for row in preamble for c in row if c is not None]).lower()
    for name, pattern in ISSUERS:
        if re.search(pattern, text):
            return name
    return (holding.issuer if holding is not None and holding.issuer else "") or _("Emittente")


def read_file(filename: str, raw: bytes, holding: Holding | None = None) -> Parsed:
    """Read the holdings file of a fund; LookThroughError when it has no table with names and weights."""
    if not raw:
        raise LookThroughError(_("Il file è vuoto."))
    for table in _rows_of(filename or "", raw):
        found = _header(table)
        if found:
            start, columns = found
            break
    else:
        raise LookThroughError(_("Non trovo la tabella delle partecipazioni: servono almeno le colonne del nome "
                                 "e del peso (%) dei titoli."))
    preamble = table[:start]
    records = []
    for row in table[start + 1:]:
        def cell(field_name, row=row):
            i = columns.get(field_name)
            return row[i] if i is not None and i < len(row) else None
        name = " ".join(str(cell("name") or "").split())
        weight = number(cell("weight")) if "weight" in columns else None
        value = number(cell("value"))
        if not name or (weight is None and value is None):
            continue  # blank lines, totals without a name, the notes at the end
        records.append((name, weight, value, cell("sector"), cell("country"), cell("currency"), cell("asset_class")))
    if not records:
        raise LookThroughError(_("La tabella delle partecipazioni non ha righe con un peso."))

    if "weight" in columns and any(r[1] is not None for r in records):
        weights = [r[1] or 0.0 for r in records]
        positive = sum(w for w in weights if w > 0)
        if 0 < positive <= 1.5:  # fractions (0.0463), not percentages
            weights = [w * 100 for w in weights]
    else:  # no weight column: from the market values
        total = sum(r[2] for r in records if r[2] and r[2] > 0)
        weights = [(r[2] or 0.0) / total * 100 if total else 0.0 for r in records]

    sums: dict[str, dict[str, float]] = {kind: defaultdict(float) for kind in KINDS}
    companies: dict[str, list] = {}
    for (name, _w, _v, sector, country, currency, asset_class), weight in zip(records, weights):
        if not weight:
            continue
        sector, asset_class = sector_name(sector), _asset_class_name(asset_class)
        if country is not None and (code := country_code(country) or _plain(country)):
            sums["country"][code] += weight
        if sector:
            sums["sector"][sector] += weight
        if code := _currency(currency):
            sums["currency"][code] += weight
        if asset_class:
            sums["asset_class"][asset_class] += weight
        if sector != "Liquidità" and asset_class != asset_classes.CASH:
            entry = companies.setdefault(company_key(name), [name, 0.0, 0.0])
            entry[1] += weight
            if weight > entry[2]:  # the name of its largest line
                entry[0], entry[2] = name, weight
    top = sorted(companies.values(), key=lambda e: -e[1])[:TOP_COMPANIES]
    sums["holding"] = {name: weight for name, weight, _largest in top}
    extension = (filename.rsplit(".", 1)[-1].upper() if "." in (filename or "") else "") or _("file")
    return Parsed(exposures={k: dict(v) for k, v in sums.items() if v}, as_of=_file_date(preamble),
                  source=f"{_issuer(filename or '', preamble, holding)} {extension}", rows=len(records))


DATE_WORDS = re.compile(r"as of|as at|holdings|\bal\b|\bdata\b|\bdate\b|aggiornat|riferimento|\bper il\b", re.I)


def _file_date(preamble: list[list]) -> date | None:
    """The date of the data: on a line that says so («Fund Holdings as of», «Dati al»), else the first one."""
    rows = sorted(preamble, key=lambda row: not DATE_WORDS.search(" ".join(str(c) for c in row if c is not None)))
    return next((d for row in rows for c in row if (d := _date_in(c))), None)


def _plain(text) -> str | None:
    """A country the file names that is not one Babel knows («Other», «Europe»): kept as written; «-» is none."""
    raw = " ".join(str(text or "").split())
    return raw if raw and raw not in ("-", "—", "--", "n/a", "N/A") else None


# ── Saving ─────────────────────────────────────────────────────────────────────

def save(holding: Holding, exposures: dict[str, dict[str, float]], as_of: date, source: str) -> int:
    """Replace the holding's rows of the kinds given; how many rows were written."""
    kinds = [k for k in KINDS if exposures.get(k)]
    if kinds:
        HoldingExposure.query.filter(HoldingExposure.holding_id == holding.id,
                                     HoldingExposure.kind.in_(kinds)).delete(synchronize_session=False)
    written = 0
    for kind in kinds:
        for name, weight in exposures[kind].items():
            rounded = Decimal(str(round(weight, 4)))
            if rounded:
                db.session.add(HoldingExposure(holding_id=holding.id, kind=kind, name=name[:500], weight=rounded,
                                               as_of=as_of, source=source))
                written += 1
    db.session.flush()
    return written


def import_file(holding: Holding, filename: str, raw: bytes, as_of: date | None = None) -> Parsed:
    """Read the file and save what it says: the date typed, else the file's, else today."""
    parsed = read_file(filename, raw, holding)
    parsed.as_of = as_of or parsed.as_of or date.today()
    save(holding, parsed.exposures, parsed.as_of, parsed.source)
    return parsed


def manual(holding: Holding, rows: dict[str, list[tuple[str, str]]], as_of: date | None = None) -> int:
    """The countries and sectors typed by hand: {kind: [(name, weight text)]}; empty rows are skipped."""
    exposures: dict[str, dict[str, float]] = {}
    for kind, entries in rows.items():
        if kind not in ("country", "sector"):
            continue
        sums: dict[str, float] = defaultdict(float)
        for name, weight_text in entries:
            name = " ".join((name or "").split())
            if not name and not (weight_text or "").strip():
                continue
            weight = number(weight_text)
            if not name or weight is None or not 0 < weight <= 100:
                raise LookThroughError(_("Ogni riga ha bisogno di un nome e di un peso tra 0 e 100 (es. 62,5)."))
            if kind == "country":
                code = country_code(name)
                if code is None:
                    raise LookThroughError(_("Paese non riconosciuto: «%(name)s».", name=name))
                sums[code] += weight
            else:
                sums[sector_name(name)] += weight
        if sum(sums.values()) > 100.5:
            raise LookThroughError(_("I pesi superano il 100 %%."))
        if sums:
            exposures[kind] = dict(sums)
    if not exposures:
        raise LookThroughError(_("Scrivi almeno un paese o un settore con il suo peso."))
    return save(holding, exposures, as_of or date.today(), MANUAL)


def clear(holding: Holding) -> int:
    return HoldingExposure.query.filter(HoldingExposure.holding_id == holding.id).delete(synchronize_session=False)


# ── One holding ────────────────────────────────────────────────────────────────

def _by_holding(holding_ids) -> dict[int, dict[str, dict[str, float]]]:
    data: dict[int, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    if holding_ids:
        for row in HoldingExposure.query.filter(HoldingExposure.holding_id.in_(list(holding_ids))):
            data[row.holding_id][row.kind][row.name] = float(row.weight)
    return data


def summary(holding: Holding) -> dict:
    """The holding's look-through for its page: the date, the sources, each kind largest first (labels shown)."""
    rows = HoldingExposure.query.filter(HoldingExposure.holding_id == holding.id).all()
    result = {"as_of": max((r.as_of for r in rows), default=None),
              "sources": sorted({r.source for r in rows if r.source}), "count": len(rows)}
    for kind in KINDS:
        ordered = sorted((r for r in rows if r.kind == kind), key=lambda r: -r.weight)
        label = country_label if kind == "country" else (lambda n: _(n) if n else n)
        result[kind] = [(label(r.name), float(r.weight)) for r in ordered]
    result["manual"] = {kind: [(fund_facts.country_name(r.name) if kind == "country" and len(r.name) == 2 else r.name,
                                float(r.weight)) for r in sorted((r for r in rows if r.kind == kind),
                                                                 key=lambda r: -r.weight)][:MANUAL_ROWS]
                        for kind in ("country", "sector")}
    return result


# ── The portfolio ──────────────────────────────────────────────────────────────

def _fallback(h: Holding, kind: str) -> str | None:
    """What the holding's form says when it has no look-through data of a kind."""
    if kind == "country":
        if h.region == "Italia":
            return "IT"
        if h.region:
            return h.region
        if h.asset_class in ("Azione", "Obbligazione"):  # a share or a bond: the country of its ISIN
            return fund_facts.domicile_code(h)
        return None
    if kind == "sector":
        if h.sector:
            return h.sector
        estimated = asset_classes.of(h)
        return estimated if estimated not in (asset_classes.EQUITY, asset_classes.OTHER, asset_classes.BALANCED) \
            else None
    if kind == "currency":
        return None if h.asset_class in FUNDS else (h.currency or "EUR")
    if kind == "asset_class":
        return asset_classes.of(h)
    return None


def _ranked(sums: dict[str, float], total: float, top: int | None, label) -> list[dict]:
    """Largest first, `top` named then «Altri», «Senza dati» last: [{name, value, pct}]."""
    uncovered = sums.pop(UNCOVERED, 0.0)
    merged: dict[str, float] = defaultdict(float)
    for name, value in sums.items():
        merged[label(name)] += value  # «Italia» typed as a region and IT from a file are one bar
    ordered = sorted(((n, v) for n, v in merged.items() if abs(v) > 0.005), key=lambda item: -item[1])
    if top is not None and len(ordered) > top + 1:
        ordered = ordered[:top] + [(_(OTHERS), sum(v for _n, v in ordered[top:]))]
    if uncovered > 0.005:
        ordered.append((_(UNCOVERED), uncovered))
    return [{"name": n, "value": round(v, 2), "pct": round(v / total * 100, 1) if total else 0.0,
             "uncovered": n == _(UNCOVERED)} for n, v in ordered]


def portfolio(holdings: list[Holding]) -> dict:
    """The look-through of the holdings: by country, sector, currency (the charts), asset class, the top companies
    with the funds that hold them, the overlaps between funds, and how much of the value has look-through data."""
    holdings = [h for h in holdings if h.value > 0]
    total = sum(h.value for h in holdings)
    data = _by_holding({h.id for h in holdings})
    result = {"total": round(total, 2)}
    labels = {"country": country_label, "sector": lambda n: _(n), "currency": lambda n: n,
              "asset_class": lambda n: _(n)}
    for kind, label in labels.items():
        sums: dict[str, float] = defaultdict(float)
        for h in holdings:
            weights = data[h.id].get(kind) if h.id in data else None
            if weights:
                for name, weight in weights.items():
                    sums[name] += h.value * weight / 100
                rest = h.value * (1 - sum(weights.values()) / 100)
                if rest > 0:
                    sums[UNCOVERED] += rest
            else:
                sums[_fallback(h, kind) or UNCOVERED] += h.value
        result[kind] = _ranked(sums, total, TOP_CHART if kind in ("country", "sector") else None, label)
    covered = sum(h.value for h in holdings if h.id in data and data[h.id])
    result["covered_pct"] = round(covered / total * 100, 1) if total else 0.0
    result["funds"] = [h for h in holdings if h.id in data and data[h.id]]
    result["companies"] = _companies(holdings, data, total)
    result["overlaps"] = overlaps(holdings, data)
    return result


def _companies(holdings, data, total) -> list[dict]:
    """The largest underlying companies: their share of the portfolio and the holdings they come from."""
    companies: dict[str, dict] = {}
    for h in holdings:
        weights = data[h.id].get("holding") if h.id in data else None
        if weights:
            lines = weights.items()
        elif h.asset_class == "Azione":  # a share is its own company
            lines = [(h.name, 100.0)]
        else:
            continue
        for name, weight in lines:
            entry = companies.setdefault(company_key(name), {"name": name, "value": 0.0, "via": []})
            entry["value"] += h.value * weight / 100
            entry["via"].append((h.name, weight))
    ordered = sorted(companies.values(), key=lambda e: -e["value"])[:TOP_TABLE]
    for entry in ordered:
        entry["value"] = round(entry["value"], 2)
        entry["pct"] = round(entry["value"] / total * 100, 2) if total else 0.0
        entry["via"].sort(key=lambda item: -item[1])
    return ordered


def overlaps(holdings, data=None) -> list[dict]:
    """Each pair of funds with companies in common: Σ min(weight in one, weight in the other), largest first."""
    data = data if data is not None else _by_holding({h.id for h in holdings})
    funds = []
    for h in holdings:
        weights = data[h.id].get("holding") if h.id in data else None
        if weights:
            keyed: dict[str, float] = defaultdict(float)
            for name, weight in weights.items():
                keyed[company_key(name)] += weight
            funds.append((h, keyed))
    pairs = []
    for (a, wa), (b, wb) in combinations(funds, 2):
        common = set(wa) & set(wb)
        if common:
            pairs.append({"a": a, "b": b, "overlap": round(sum(min(wa[k], wb[k]) for k in common), 2),
                          "common": len(common)})
    return sorted(pairs, key=lambda p: -p["overlap"])
