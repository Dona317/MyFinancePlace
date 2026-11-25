"""
The operations of a broker statement (F19c): purchases and sales read from the CSV or Excel the broker exports,
shown for review, then saved as the holdings' operations (services.portfolio_ops).

- Degiro's «Transactions» export (English or Italian headers) is recognized by its columns: quantity signed (negative
  = sold), the value in euro and the costs of each trade.
- Bonds are quoted in % of the nominal (BTP at 100,15): the price is turned into euro per euro of nominal, as the
  price sites do (instrument_sources.borsaitaliana).
- Any other broker: the columns are found by their titles (date, ISIN or ticker, name, quantity, price, commission,
  buy/sell or amount). The guess can be corrected on a mapping screen and saved as a preset (services.import_presets,
  kind "broker"): `read` then takes the mapping instead of guessing.

Every row gets a fingerprint, so importing the same statement again adds nothing. The holding is found by ISIN, then
ticker, then name; a row about an instrument not owned yet creates it.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal

from flask_babel import gettext as _

from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import options, transfer
from app.services.parsing import normalize, to_date, to_decimal

ISIN = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")
# column → title words, strongest first (normalized: lowercase, no punctuation)
COLUMNS = {
    "date": ("data operazione", "data esecuzione", "data", "date", "trade date"),
    "isin": ("isin", "codice isin"),
    "ticker": ("ticker", "simbolo", "symbol"),
    "name": ("prodotto", "product", "titolo", "strumento", "descrizione titolo", "descrizione", "name", "nome"),
    "units": ("quantita", "quantity", "qty", "quote", "nominale", "shares"),
    "price": ("prezzo", "quotazione", "price", "prezzo eseguito", "corso"),
    "value": ("valore", "value", "controvalore", "importo", "amount", "totale", "total"),
    "fee": ("costi di transazione", "transaction and or third party fees", "commissioni", "commissione", "fees",
            "fee", "costi"),
    "side": ("segno", "tipo", "operazione", "side", "buy sell", "type"),
}
# the fields of a trade, in the order of the mapping screen
FIELDS = ("date", "side", "isin", "ticker", "name", "units", "price", "value", "fee")
SELL_WORDS = ("vendita", "sell", "v", "s", "sale", "vend")
BUY_WORDS = ("acquisto", "buy", "a", "b", "purchase", "acq")


@dataclass
class BrokerRow:
    line: int
    on: date
    name: str
    isin: str | None
    ticker: str | None
    units: Decimal       # signed: negative = sold
    price: Decimal       # per unit, in euro
    fee: Decimal
    ref: str
    holding_id: int | None = None
    duplicate: bool = False
    market: Decimal | None = None  # a positions statement: the day's market price in euro, recorded on confirming

    def as_dict(self) -> dict:
        data = asdict(self)
        data.update(on=self.on.isoformat(), units=str(self.units), price=str(self.price), fee=str(self.fee),
                    market=str(self.market) if self.market else None)
        return data


@dataclass
class Preview:
    rows: list[BrokerRow]
    unread: list[int]   # lines that are not a trade (deposits, dividends, cash sweeps…) or could not be read
    layout: str         # "degiro" | "generico"
    headers: list[str] = field(default_factory=list)
    mapping: dict[str, str | None] = field(default_factory=dict)


def _key(header: str) -> str:
    """The title without accents, case and punctuation: «Quantità» → «quantita»."""
    return normalize(unicodedata.normalize("NFKD", header).encode("ascii", "ignore").decode())


def _column(headers: list[str], name: str, taken: set[str]) -> str | None:
    keys = {h: _key(h) for h in headers}
    for word in COLUMNS[name]:
        for header, key in keys.items():
            if header not in taken and key == word:
                return header
    for word in COLUMNS[name]:
        for header, key in keys.items():
            if header not in taken and len(word) > 3 and word in key:
                return header
    return None


def guess(headers: list[str]) -> dict[str, str | None]:
    """Field → column of the file, found by the column titles (None where nothing fits)."""
    found, taken = {}, set()
    for name in ("isin", "ticker", "fee", "date", "units", "price", "value", "side", "name"):
        found[name] = _column(headers, name, taken)
        if found[name]:
            taken.add(found[name])
    return {name: found[name] for name in FIELDS}


def missing(cols: dict[str, str | None]) -> str | None:
    """Why the mapping cannot read the trades (a message for the user), or None when it can."""
    if not cols.get("date") or not cols.get("units") or not (cols.get("isin") or cols.get("ticker") or cols.get("name")):
        return _("Non trovo le colonne delle operazioni: servono almeno data, quantità e titolo (ISIN, ticker o nome).")
    if not cols.get("price") and not cols.get("value"):
        return _("Non trovo il prezzo né il controvalore delle operazioni.")
    return None


def clean(headers: list[str], mapping: dict) -> dict[str, str | None]:
    """A mapping from a form or a preset, kept to the known fields and to the file's columns."""
    return {name: mapping.get(name) if mapping.get(name) in headers else None for name in FIELDS}


def columns(filename: str, raw: bytes) -> tuple[list[str], dict[str, str | None], dict[str, str]]:
    """The file's column titles, the guessed mapping and a sample value of each column (for the mapping screen)."""
    headers, records, _first = transfer.read_table(filename, raw)
    samples = {h: next((str(r.get(h) or "").strip() for r in records if str(r.get(h) or "").strip()), "")
               for h in headers}
    return headers, guess(headers), samples


def _layout(headers: list[str]) -> str:
    keys = {_key(h) for h in headers}
    return "degiro" if {"isin", "borsa di riferimento"} <= keys or {"isin", "reference exchange"} <= keys else "generico"


def _side(text: str | None) -> int | None:
    word = normalize(text or "")
    if not word:
        return None
    if word in SELL_WORDS or word.startswith(("ven", "sell", "sale")):
        return -1
    if word in BUY_WORDS or word.startswith(("acq", "buy", "purch", "sottoscr")):
        return 1
    return None


def fingerprint(on: date, isin: str | None, ticker: str | None, name: str, units: Decimal, price: Decimal,
                occurrence: int) -> str:
    key = f"broker|{on.isoformat()}|{isin or ticker or normalize(name)}|{units:f}|{price:f}|{occurrence}"
    return hashlib.sha256(key.encode()).hexdigest()


def _row(record: dict, cols: dict, line: int) -> BrokerRow | None:
    def cell(name: str) -> str:
        return (record.get(cols[name]) or "").strip() if cols.get(name) else ""

    on, units = to_date(cell("date")), to_decimal(cell("units"))
    isin_text = cell("isin").upper()
    isin = ISIN.search(isin_text).group(1) if ISIN.search(isin_text) else None
    ticker, name = cell("ticker").upper() or None, cell("name") or isin or cell("ticker")
    if on is None or not units or not name:
        return None
    side = _side(cell("side"))
    if side is not None:
        units = abs(units) * side
    price, value = to_decimal(cell("price")), to_decimal(cell("value"))
    terms = options.from_description(name)  # F120: an option, quoted per unit of the underlying
    size = terms["multiplier"] if terms else Decimal(1)
    if value and units:  # the value in euro is the truth when the price is in another currency (Degiro)
        euro = abs(value) / abs(units) / size
        price = euro if price is None or abs(euro - price) / euro > Decimal("0.005") else price
    if price is None or price <= 0:
        return None
    if guess_class(name) == "Obbligazione" and abs(units) >= 1000 and price >= 20:
        price = price / 100  # bonds are quoted in % of the nominal: the units are euro of nominal
    fee = abs(to_decimal(cell("fee")) or Decimal(0))
    return BrokerRow(line, on, name, isin, ticker, units, price, fee, "")


# ── A statement of the positions (22 Nov 2026) ─────────────────────────────────
# Not a list of trades but the securities held on a day (Fineco «Portafoglio di sintesi», a broker's positions
# export): no date column, a quantity and the average cost or the market value of each line. portfolio_reading
# compares it with the recorded positions, as for the state read by the AI model.
POSITION_COLUMNS = {
    "cost": ("p zo medio di carico", "prezzo medio di carico", "pzo medio di carico", "prezzo medio", "prezzo di carico",
             "pmc", "average price", "avg price", "average cost"),
    "cost_value": ("valore di carico", "controvalore di carico", "cost value", "book value"),
    "market": ("p zo di mercato", "prezzo di mercato", "pzo di mercato", "market price", "last price", "prezzo"),
    "market_value": ("valore di mercato", "controvalore di mercato", "market value", "controvalore", "valore"),
    "currency": ("valuta", "divisa", "currency"),
    "rate": ("cambio di carico", "cambio medio di carico", "exchange rate"),
}
FILE_DATE = re.compile(r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)|(?<!\d)(20\d{2})-?(\d{2})-?(\d{2})(?!\d)")


def _position_column(headers: list[str], name: str, taken: set[str]) -> str | None:
    keys = {h: _key(h) for h in headers}
    for exact in (True, False):
        for word in POSITION_COLUMNS[name]:
            for header, key in keys.items():
                if header not in taken and (key == word if exact else (len(word) > 3 and key.startswith(word))):
                    return header
    return None


def file_date(filename: str) -> date | None:
    """The day in a file's name (15112026_Fineco_Portafoglio.xls, positions-2026-11-15.csv), if any."""
    for found in FILE_DATE.finditer(filename or ""):
        day, month, year = (found.group(1), found.group(2), found.group(3)) if found.group(1) else \
            (found.group(6), found.group(5), found.group(4))
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            continue
    return None


def positions(filename: str, raw: bytes) -> list[dict] | None:
    """The lines of a positions statement as {name, isin, ticker, quantity, price, value_eur} (price: the average
    cost of one unit in euro, so the cost of what is held stays right), or None when the file is not one: it has a
    date column, or no quantity, or neither a cost nor a market value."""
    headers, records, _first = transfer.read_table(filename, raw)
    cols = guess(headers)
    if cols["date"] or not cols["units"] or not (cols["isin"] or cols["ticker"] or cols["name"]):
        return None
    taken = {c for c in cols.values() if c}
    found = {}
    for name in ("cost", "cost_value", "market", "market_value", "currency", "rate"):
        found[name] = _position_column(headers, name, taken - ({cols["value"]} if name.endswith("value") else set()))
        if found[name]:
            taken.add(found[name])
    if not (found["cost"] or found["cost_value"] or found["market"] or found["market_value"]):
        return None
    out = []
    for record in records:
        def cell(column):
            return str(record.get(column) or "").strip() if column else ""
        quantity = to_decimal(cell(cols["units"]))
        isin_text = cell(cols["isin"]).upper()
        isin = ISIN.search(isin_text).group(1) if ISIN.search(isin_text) else None
        ticker = cell(cols["ticker"]).upper() or None
        name = cell(cols["name"]) or isin or ticker
        if quantity is None or not name or normalize(name).startswith(("totale", "total")):
            continue
        rate = to_decimal(cell(found["rate"])) if found["rate"] else None
        foreign = cell(found["currency"]).upper() not in ("", "EUR", "€")
        price = to_decimal(cell(found["cost"])) or to_decimal(cell(found["market"]))
        if price and foreign and rate and rate > 0:
            price = price / rate  # Fineco: the exchange rate is units of the currency for one euro
        market_value, market = to_decimal(cell(found["market_value"])), to_decimal(cell(found["market"]))
        if market_value and quantity:  # «Valore di mercato €»: in euro whatever the currency
            market = abs(market_value) / abs(quantity)
        value = None if foreign else (to_decimal(cell(found["cost_value"])) if found["cost"] or not found["market"]
                                      else to_decimal(cell(found["market_value"])))
        out.append({"name": name, "isin": isin or "", "ticker": ticker or "", "quantity": quantity,
                    "price": price or 0, "value_eur": value or 0, "market": market or 0})
    return out or None


def _match(row: BrokerRow, holdings: list[Holding]) -> int | None:
    for test in (lambda h: row.isin and h.isin == row.isin,
                 lambda h: row.ticker and (h.ticker or "").upper().split(".")[0] == row.ticker.split(".")[0],
                 lambda h: normalize(h.name) == normalize(row.name)):
        found = next((h for h in holdings if test(h)), None)
        if found is not None:
            return found.id
    return None


def read(filename: str, raw: bytes, mapping: dict | None = None) -> Preview:
    """The trades of a broker statement, matched to the holdings, the ones already imported marked. The columns are
    `mapping` (field → column title) when given, else guessed from the titles."""
    headers, records, first_line = transfer.read_table(filename, raw)
    cols = clean(headers, mapping) if mapping is not None else guess(headers)
    problem = missing(cols)
    if problem:
        raise transfer.TableError(problem)
    layout = _layout(headers)
    rows, unread = [], []
    for offset, record in enumerate(records):
        row = _row(record, cols, first_line + offset)
        if row is None:
            unread.append(first_line + offset)
            continue
        rows.append(row)
    if not rows:
        raise transfer.TableError(_("Nessuna operazione di compravendita trovata nel file."))
    return finish(rows, unread, layout, headers, cols)


def finish(rows: list[BrokerRow], unread: list[int], layout: str, headers: list[str] | None = None,
           cols: dict | None = None) -> Preview:
    """The trades read (from a file's columns or by an AI model): their fingerprints, the holdings they match and
    the ones already imported, oldest first."""
    seen: dict[str, int] = {}
    for row in rows:
        base = fingerprint(row.on, row.isin, row.ticker, row.name, row.units, row.price, 0)
        occurrence = seen.get(base, 0)
        seen[base] = occurrence + 1
        row.ref = fingerprint(row.on, row.isin, row.ticker, row.name, row.units, row.price, occurrence)
    holdings = Holding.query.all()
    known = {ref for (ref,) in Transaction.query.with_entities(Transaction.import_ref)
             .filter(Transaction.import_ref.in_([r.ref for r in rows]))}
    for row in rows:
        row.holding_id = _match(row, holdings)
        row.duplicate = row.ref in known
    rows.sort(key=lambda r: (r.on, r.line))  # oldest first: a sale finds the units bought before it
    return Preview(rows, unread, layout, headers or [], cols or {})


def guess_class(name: str) -> str:
    if options.from_description(name):
        return "Derivato"
    text = normalize(name)
    if re.search(r"\b(etf|ucits|etc|etn|ishares|xtrackers|vanguard|amundi|spdr|lyxor)\b", text):
        return "ETF"
    if re.search(r"\b(btp|bot|cct|ctz|bond|obbligaz|treasury|bund)\b", text):
        return "Obbligazione"
    return "Azione"


# ── A template to fill in by hand ──────────────────────────────────────────────

TEMPLATE_HEADERS = ["Data operazione", "Segno", "Titolo", "ISIN", "Ticker", "Quantità", "Prezzo", "Commissioni"]
TEMPLATE_ROWS = [  # one purchase of an ETF, a bond quoted in % of the nominal, a sale of shares
    ["15/01/2026", "A", "Vanguard FTSE All-World UCITS ETF Acc", "IE00BK5BQT80", "VWCE.MI", "10", "120,50", "2,95"],
    ["03/02/2026", "A", "BTP 4,40% Mg33", "IT0005518128", "", "5000", "101,20", "5,00"],
    ["20/03/2026", "V", "Enel S.p.A.", "IT0003128367", "ENEL.MI", "100", "7,15", "2,95"],
]


def template(kind: str = "csv") -> bytes:
    """The file to fill in with one's own trades: the columns the import reads by itself (A = acquisto, V = vendita;
    a bond's price in % of the nominal, its quantity the nominal), three example rows to replace."""
    if kind == "xlsx":
        import io

        from openpyxl import Workbook

        book = Workbook()
        sheet = book.active
        sheet.title = "Operazioni"
        sheet.append(TEMPLATE_HEADERS)
        for row in TEMPLATE_ROWS:
            sheet.append(row)
        for column, width in zip("ABCDEFGH", (16, 8, 42, 16, 12, 10, 10, 12)):
            sheet.column_dimensions[column].width = width
        buffer = io.BytesIO()
        book.save(buffer)
        return buffer.getvalue()
    lines = [";".join(TEMPLATE_HEADERS)] + [";".join(row) for row in TEMPLATE_ROWS]
    return ("\ufeff" + "\n".join(lines) + "\n").encode("utf-8")
