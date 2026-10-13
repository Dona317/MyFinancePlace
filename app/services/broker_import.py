"""
The operations of a broker statement (F19c): purchases and sales read from the CSV or Excel the broker exports,
shown for review, then saved as the holdings' operations (services.portfolio_ops).

- Degiro's «Transactions» export (English or Italian headers) is recognized by its columns: quantity signed (negative
  = sold), the value in euro and the costs of each trade.
- Bonds are quoted in % of the nominal (BTP at 100,15): the price is turned into euro per euro of nominal, as the
  price sites do (instrument_sources.borsaitaliana).
- Any other broker: the columns are found by their titles (date, ISIN or ticker, name, quantity, price, commission,
  buy/sell or amount).

Every row gets a fingerprint, so importing the same statement again adds nothing. The holding is found by ISIN, then
ticker, then name; a row about an instrument not owned yet creates it.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal

from flask_babel import gettext as _

from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import transfer
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

    def as_dict(self) -> dict:
        data = asdict(self)
        data.update(on=self.on.isoformat(), units=str(self.units), price=str(self.price), fee=str(self.fee))
        return data


@dataclass
class Preview:
    rows: list[BrokerRow]
    unread: list[int]   # lines that are not a trade (deposits, dividends, cash sweeps…) or could not be read
    layout: str         # "degiro" | "generico"


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


def _columns(headers: list[str]) -> dict[str, str | None]:
    found, taken = {}, set()
    for name in ("isin", "ticker", "fee", "date", "units", "price", "value", "side", "name"):
        found[name] = _column(headers, name, taken)
        if found[name]:
            taken.add(found[name])
    if not found["date"] or not found["units"] or not (found["isin"] or found["ticker"] or found["name"]):
        raise transfer.TableError(_("Non trovo le colonne delle operazioni: servono almeno data, quantità e titolo "
                                    "(ISIN, ticker o nome)."))
    if not found["price"] and not found["value"]:
        raise transfer.TableError(_("Non trovo il prezzo né il controvalore delle operazioni."))
    return found


def _layout(headers: list[str]) -> str:
    keys = {_key(h) for h in headers}
    return "degiro" if {"isin", "borsa di riferimento"} <= keys or {"isin", "reference exchange"} <= keys else "generico"


def _side(text: str | None) -> int | None:
    word = normalize(text or "")
    if not word:
        return None
    if word in SELL_WORDS or word.startswith(("vend", "sell", "sale")):
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
    if value and units:  # the value in euro is the truth when the price is in another currency (Degiro)
        euro = abs(value) / abs(units)
        price = euro if price is None or abs(euro - price) / euro > Decimal("0.005") else price
    if price is None or price <= 0:
        return None
    if guess_class(name) == "Obbligazione" and abs(units) >= 1000 and price >= 20:
        price = price / 100  # bonds are quoted in % of the nominal: the units are euro of nominal
    fee = abs(to_decimal(cell("fee")) or Decimal(0))
    return BrokerRow(line, on, name, isin, ticker, units, price, fee, "")


def _match(row: BrokerRow, holdings: list[Holding]) -> int | None:
    for test in (lambda h: row.isin and h.isin == row.isin,
                 lambda h: row.ticker and (h.ticker or "").upper().split(".")[0] == row.ticker.split(".")[0],
                 lambda h: normalize(h.name) == normalize(row.name)):
        found = next((h for h in holdings if test(h)), None)
        if found is not None:
            return found.id
    return None


def read(filename: str, raw: bytes) -> Preview:
    """The trades of a broker statement, matched to the holdings, the ones already imported marked."""
    headers, records, first_line = transfer.read_table(filename, raw)
    cols, layout = _columns(headers), _layout(headers)
    rows, unread, seen = [], [], {}
    for offset, record in enumerate(records):
        row = _row(record, cols, first_line + offset)
        if row is None:
            unread.append(first_line + offset)
            continue
        base = fingerprint(row.on, row.isin, row.ticker, row.name, row.units, row.price, 0)
        occurrence = seen.get(base, 0)
        seen[base] = occurrence + 1
        row.ref = fingerprint(row.on, row.isin, row.ticker, row.name, row.units, row.price, occurrence)
        rows.append(row)
    if not rows:
        raise transfer.TableError(_("Nessuna operazione di compravendita trovata nel file."))
    holdings = Holding.query.all()
    known = {ref for (ref,) in Transaction.query.with_entities(Transaction.import_ref)
             .filter(Transaction.import_ref.in_([r.ref for r in rows]))}
    for row in rows:
        row.holding_id = _match(row, holdings)
        row.duplicate = row.ref in known
    rows.sort(key=lambda r: (r.on, r.line))  # oldest first: a sale finds the units bought before it
    return Preview(rows, unread, layout)


def guess_class(name: str) -> str:
    text = normalize(name)
    if re.search(r"\b(etf|ucits|etc|etn|ishares|xtrackers|vanguard|amundi|spdr|lyxor)\b", text):
        return "ETF"
    if re.search(r"\b(btp|bot|cct|ctz|bond|obbligaz|treasury|bund)\b", text):
        return "Obbligazione"
    return "Azione"
