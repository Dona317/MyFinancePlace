"""
Bank statement import (Excel / CSV) → transactions.

Supported layouts:
  • Fineco         — "Data_Operazione | Data_Valuta | Entrate | Uscite | Descrizione | Descrizione_Completa | Stato | Moneymap"
  • Intesa Sanpaolo — "Data | Operazione | Dettagli | Conto o carta | Contabilizzazione | Categoria | Valuta | Importo"
                      (older exports: "Data contabile | Data valuta | Descrizione | Accrediti | Addebiti | Descrizione estesa")
  • Generic        — any statement whose header has a date, a description and either a signed amount
                      or separate credit/debit columns (UniCredit, BPER, Revolut, N26, …)

Accepted files: Excel (.xlsx/.xls), CSV, TXT, PDF (text-based), Word (.docx), RTF, OpenDocument (.ods/.odt).

Pipeline:  readers.read_document() → candidate tables → detect_layout() → parse_rows() → enrich() (category, dedup)
  • Structured tables (spreadsheets, Word/ODF tables, ruled PDF tables, delimited text) are tried first.
  • Column layouts without a real table (PDF text, fixed-width TXT) are rebuilt from the header positions.
  • Last resort: lines shaped like "date … description … amount".
  • Scans, photos and layouts none of the above can read raise AIRequired: after the user confirms,
    analyze_with_ai() reads them with a model (services/ai_extraction.py); the result is validated and
    balance-checked before the preview.
Bank export preamble rows (account holder, period, balances) and footer rows are skipped automatically.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from statistics import median

from app.models.transaction import Transaction
from app.services import ai_extraction, duplicates
from app.services import statement_readers as readers
from app.services.parsing import TRANSACTION_TYPES, clean_text, normalize, to_date, to_decimal, valid_amount
from app.services.statement_readers import Word

HEADER_SCAN_ROWS = 40
PENDING_STATUSES = ("non contabilizzat", "autorizzat", "in attesa", "pending", "da contabilizzare")


# ── Bank layouts ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BankLayout:
    key: str
    name: str
    markers: tuple[str, ...]              # text in the preamble / filename identifying the bank
    signature: tuple[str, ...]            # header names only this bank uses
    columns: dict[str, tuple[str, ...]]   # field → accepted (normalized) header names, by priority


BANKS = {
    "fineco": BankLayout(
        key="fineco",
        name="Fineco",
        markers=("fineco",),
        signature=("moneymap", "descrizione completa"),
        columns={
            "date":        ("data operazione", "data"),
            "description": ("descrizione completa", "descrizione"),
            "details":     ("descrizione",),
            "credit":      ("entrate",),
            "debit":       ("uscite",),
            "category":    ("moneymap",),
            "status":      ("stato",),
        },
    ),
    "intesa": BankLayout(
        key="intesa",
        name="Intesa Sanpaolo",
        markers=("intesa", "sanpaolo", "isybank"),
        signature=("contabilizzazione", "conto o carta"),
        columns={
            "date":        ("data contabile", "data operazione", "data"),
            # "Dettagli" / "Descrizione estesa" name the merchant; "Operazione" is only the kind
            # ("Pagamento tramite POS"), so it becomes the detail line
            "description": ("dettagli", "descrizione estesa", "operazione", "descrizione"),
            "details":     ("operazione", "descrizione"),
            "amount":      ("importo",),
            "credit":      ("accrediti",),
            "debit":       ("addebiti",),
            "category":    ("categoria",),
            "currency":    ("valuta",),
            "status":      ("contabilizzazione",),
        },
    ),
    "generic": BankLayout(
        key="generic",
        name="Altra banca (generico)",
        markers=(),
        signature=(),
        columns={
            "date": (
                "data operazione", "data contabile", "data registrazione", "data movimento", "data",
                "booking date", "transaction date", "started date", "completed date", "date",
            ),
            "description": (
                "descrizione operazione", "descrizione", "causale", "operazione", "dettaglio",
                "description", "details", "payee", "beneficiario",
            ),
            "details":  ("descrizione estesa", "descrizione completa", "dettagli", "note", "reference"),
            "amount":   ("importo eur", "importo euro", "importo", "ammontare", "amount eur", "amount"),
            "credit":   ("entrate", "accrediti", "avere", "credit", "money in"),
            "debit":    ("uscite", "addebiti", "dare", "debit", "money out"),
            "category": ("categoria", "category"),
            "currency": ("divisa", "currency"),
            "status":   ("stato", "state", "status"),
        },
    ),
}

AUTO = "auto"
DETECTION_ORDER = ("fineco", "intesa", "generic")


# ── Auto-categorization ────────────────────────────────────────────────────────

# First match wins; keywords are matched as whole words, case-insensitive.
CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Stipendio",    ("stipendio", "emolumenti", "retribuzione", "salario", "busta paga", "cedolino")),
    ("Alimentari",   ("esselunga", "coop", "conad", "carrefour", "lidl", "eurospin", "pam", "penny", "aldi",
                      "supermercato", "supermercati", "iper", "despar", "famila", "bennet", "naturasi",
                      "alimentari", "spesa")),
    ("Trasporto",    ("eni", "enilive", "q8", "tamoil", "esso", "shell", "carburante", "carburanti", "benzina",
                      "trenitalia", "italo", "atm", "atac", "autostrade", "telepass", "uber", "taxi", "freenow",
                      "ryanair", "easyjet", "ita airways", "flixbus",
                      "parcheggio", "trasporti")),
    ("Abbonamenti",  ("netflix", "spotify", "prime video", "amazon prime", "disney", "dazn", "now tv", "icloud",
                      "apple com bill", "youtube", "tim", "vodafone", "windtre", "iliad", "fastweb", "ho mobile",
                      "abbonamento", "abbonamenti")),
    ("Casa",         ("affitto", "condominio", "enel", "a2a", "hera", "iren", "edison", "sorgenia", "bolletta",
                      "tari", "ikea", "leroy merlin", "casa", "utenze")),
    ("Salute",       ("farmacia", "ospedale", "medico", "dentista", "asl", "ticket", "sanitaria", "salute")),
    ("Svago",        ("ristorante", "pizzeria", "trattoria", "bar", "cinema", "just eat", "deliveroo", "glovo",
                      "mcdonald", "burger king", "starbucks", "booking com", "airbnb", "svago", "tempo libero", "viaggi")),
    ("Investimenti", ("compravendita titoli", "acquisto titoli", "etf", "fondi", "pac", "dossier titoli",
                      "investimenti")),
    ("Commissioni",  ("commissioni", "commissione", "canone", "imposta di bollo", "spese tenuta conto",
                      "competenze")),
    ("Rimborsi",     ("rimborso", "storno")),
]

TRANSFER_KEYWORDS = ("giroconto", "trasferimento tra conti", "ricarica carta", "girofondi")

_RULE_PATTERNS = [
    (category, re.compile(r"\b(" + "|".join(re.escape(k) for k in keywords) + r")\b"))
    for category, keywords in CATEGORY_RULES
]
_TRANSFER_PATTERN = re.compile(r"\b(" + "|".join(re.escape(k) for k in TRANSFER_KEYWORDS) + r")\b")


def _search_text(*parts: str | None) -> str:
    """Normalized text padded with spaces, so keywords can be matched as whole words."""
    return f" {normalize(' '.join(p for p in parts if p))} "


def categorize(description: str, details: str | None = None, bank_category: str | None = None) -> str:
    """App category for a statement row: keyword rules first, then the bank's own category, else "Altro"."""
    text = _search_text(description, details)
    for category, pattern in _RULE_PATTERNS:
        if pattern.search(text):
            return category
    if bank_category:
        bank_text = _search_text(bank_category)
        for category, pattern in _RULE_PATTERNS:
            if pattern.search(bank_text):
                return category
        return bank_category.strip()
    return "Altro"


def is_transfer(description: str, details: str | None = None) -> bool:
    return bool(_TRANSFER_PATTERN.search(_search_text(description, details)))


# ── Reading files ──────────────────────────────────────────────────────────────

class StatementImportError(ValueError):
    """Raised with a user-facing (Italian) message when a statement cannot be read."""


# ── Layout detection ───────────────────────────────────────────────────────────

def _match_columns(headers: list[str], layout: BankLayout) -> dict[str, int] | None:
    """Map layout fields to column indexes; None if the header lacks the required columns."""
    mapping: dict[str, int] = {}
    used: set[int] = set()
    for field_name in ("date", "description", "amount", "credit", "debit", "details",
                       "category", "currency", "status"):
        for alias in layout.columns.get(field_name, ()):
            index = next((i for i, h in enumerate(headers) if h == alias and i not in used), None)
            if index is not None:
                mapping[field_name] = index
                used.add(index)
                break
    has_amount = "amount" in mapping or ("credit" in mapping and "debit" in mapping)
    if "date" in mapping and "description" in mapping and has_amount:
        return mapping
    return None


@dataclass
class Layout:
    bank: BankLayout
    header_row: int
    columns: dict[str, int]
    headers: list[str] = field(default_factory=list)


def _identify_bank(rows: list[list], filename: str) -> str | None:
    preamble = _search_text(filename, *(str(c) for row in rows[:HEADER_SCAN_ROWS] for c in row if c))
    for key in DETECTION_ORDER:
        if any(marker in preamble for marker in BANKS[key].markers):
            return key
    return None


def layout_for_headers(headers: list[str], bank: str = AUTO, identified: str | None = None) -> tuple[str, dict] | None:
    """
    Pick the layout matching a header row. With automatic detection a bank-specific layout is used only
    when the bank was identified (name in the file) or its signature columns are present; otherwise the
    generic layout, so a plain "Data | Descrizione | Importo" file is not mislabelled as a specific bank.
    """
    if bank != AUTO:
        keys = [bank]
    elif identified:
        keys = [identified, "generic"]
    else:
        for key in DETECTION_ORDER:
            columns = _match_columns(headers, BANKS[key])
            if columns and any(sig in headers for sig in BANKS[key].signature):
                return key, columns
        keys = ["generic", *DETECTION_ORDER]
    for key in keys:
        columns = _match_columns(headers, BANKS[key])
        if columns:
            return key, columns
    return None


def detect_layout(rows: list[list], filename: str = "", bank: str = AUTO) -> Layout:
    if bank != AUTO and bank not in BANKS:
        raise StatementImportError(f"Banca non supportata: {bank}")

    identified = _identify_bank(rows, filename) if bank == AUTO else None
    for index, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        headers = [normalize(c) for c in row]
        found = layout_for_headers(headers, bank, identified)
        if found:
            key, columns = found
            return Layout(bank=BANKS[key], header_row=index, columns=columns, headers=headers)

    expected = "Data, Descrizione e Importo (oppure Entrate/Uscite)"
    raise StatementImportError(f"Intestazione dei movimenti non trovata: servono almeno le colonne {expected}.")


# ── Column layouts without a table (PDF text, fixed-width TXT) ─────────────────

AMOUNT_TOKEN = re.compile(r"^\(?[-+]?(?:€)?\d{1,3}(?:[.,' ]\d{3})*[.,]\d{2}[-+]?\)?$|^\(?[-+]?(?:€)?\d+[.,]\d{2}[-+]?\)?$")
PAGE_FOOTER = re.compile(r"^(pag(ina)?|page)\.?\s*\d+", re.IGNORECASE)
AMOUNT_FIELDS = ("amount", "credit", "debit")


@dataclass
class _HeaderCell:
    text: str
    x0: float
    x1: float

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2


def _header_cells(line: list[Word], gap: float | None) -> list[_HeaderCell]:
    """Merge words closer than `gap` into one header cell ("Data" + "Operazione"); None = one cell per word."""
    cells: list[_HeaderCell] = []
    for word in line:
        if cells and gap is not None and word.x0 - cells[-1].x1 <= gap:
            cells[-1] = _HeaderCell(f"{cells[-1].text} {word.text}", cells[-1].x0, word.x1)
        else:
            cells.append(_HeaderCell(word.text, word.x0, word.x1))
    return cells


def _find_header(lines: list[list[Word]], char_width: float, bank: str, filename: str):
    scan = lines[:HEADER_SCAN_ROWS * 3]
    identified = _identify_bank([[w.text for w in line] for line in scan], filename) if bank == AUTO else None
    for index, line in enumerate(scan):
        for gap in (char_width * 1.2, None):
            cells = _header_cells(line, gap)
            found = layout_for_headers([normalize(c.text) for c in cells], bank, identified)
            if found:
                return index, cells, found[1]
    return None


def rebuild_columns(lines: list[list[Word]], char_width: float, bank: str = AUTO, filename: str = "") -> list[list] | None:
    """
    Rebuild a table from positioned words, using the header line's cell positions as column guides:
      • amounts go to the nearest amount column (Importo / Entrate / Uscite / Dare / Avere …)
      • other words go to the last text column that starts before them
      • a line without a date continues the previous movement's description (wrapped text)
    Repeated page headers, page footers and total/balance lines are skipped.
    """
    found = _find_header(lines, char_width, bank, filename)
    if not found:
        return None
    header_index, cells, columns = found
    header_key = normalize(" ".join(c.text for c in cells))
    amount_cols = sorted({columns[f] for f in AMOUNT_FIELDS if f in columns})
    text_cols = [i for i in range(len(cells)) if i not in amount_cols]
    amount_region = min(cells[i].x0 for i in amount_cols) - char_width * 10
    date_col, description_col = columns["date"], columns["description"]

    spacings = [
        b[0].top - a[0].top
        for a, b in zip(lines[header_index + 1:], lines[header_index + 2:])
        if a and b and a[0].page == b[0].page and b[0].top > a[0].top
    ]
    max_gap = (median(spacings) * 2.2) if spacings else float("inf")

    table: list[list] = [[" ".join(w.text for w in line)] for line in lines[:header_index]]
    table.append([c.text for c in cells])
    current: list | None = None
    previous_top, previous_page = None, None

    for line in lines[header_index + 1:]:
        if not line:
            current = None
            continue
        text = " ".join(w.text for w in line)
        if normalize(text) == header_key or PAGE_FOOTER.match(text) or not re.search(r"[A-Za-z0-9]", text):
            current = None
            continue

        row = [""] * len(cells)
        for word in line:
            if AMOUNT_TOKEN.match(word.text) and word.center >= amount_region:
                col = min(amount_cols, key=lambda i: min(abs(word.x1 - cells[i].x1), abs(word.center - cells[i].center)))
            else:
                starts_before = [i for i in text_cols if cells[i].x0 <= word.center]
                col = starts_before[-1] if starts_before else text_cols[0]
            row[col] = f"{row[col]} {word.text}".strip()

        page, top = line[0].page, line[0].top
        if to_date(row[date_col]) is not None:
            table.append(row)
            current = row
        elif (
            current is not None and not any(row[i] for i in amount_cols)
            and page == previous_page and top - previous_top <= max_gap
        ):
            extra = " ".join(row[i] for i in text_cols if row[i])
            current[description_col] = f"{current[description_col]} {extra}".strip()
        else:
            current = None  # totals, balances, notes
        previous_top, previous_page = top, page
    return table


DATE_TOKEN = r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2}"
AMOUNT_PATTERN = r"[-+]?€?\s?\d{1,3}(?:[.,]\d{3})*[.,]\d{2}[-+]?|[-+]?€?\s?\d+[.,]\d{2}[-+]?"
TEXT_LINE = re.compile(
    rf"^\s*(?P<date>{DATE_TOKEN})\s+(?:(?:{DATE_TOKEN})\s+)?(?P<description>.+?)\s+"
    rf"(?P<amount>{AMOUNT_PATTERN})(?:\s+(?P<balance>{AMOUNT_PATTERN}))?\s*$"
)
INCOME_HINTS = re.compile(r"\b(stipendio|accredito|a vostro favore|bonifico da|ricevuto|rimborso|interessi creditori|entrata)\b", re.I)


def parse_text_lines(lines: list[str]) -> list[StatementRow]:
    """
    Last resort for statements without a recognizable header: lines like
    "05/06/2026  NETFLIX.COM  -17,99  [balance]". Unsigned amounts count as expenses unless the
    description suggests income; the user can still change the type in the preview.
    """
    rows: list[StatementRow] = []
    for line in lines:
        match = TEXT_LINE.match(line)
        if not match:
            if rows and line.strip() and not re.search(AMOUNT_PATTERN, line) and not PAGE_FOOTER.match(line.strip()):
                last = rows[-1]
                last.description = f"{last.description} {line.strip()}"
            continue
        tx_date = to_date(match.group("date"))
        raw_amount = match.group("amount").replace(" ", "")
        amount = to_decimal(raw_amount)
        if tx_date is None or not amount:
            continue
        description = " ".join(match.group("description").split())
        explicit_sign = raw_amount.lstrip("€")[:1] in "+-" or raw_amount.endswith(("-", "+"))
        if not explicit_sign and not INCOME_HINTS.search(description):
            amount = -abs(amount)
        rows.append(StatementRow(date=tx_date, description=description, amount=amount))
    return rows


# ── Row parsing ────────────────────────────────────────────────────────────────

@dataclass
class StatementRow:
    date: date
    description: str
    amount: Decimal          # signed: negative = money out
    details: str | None = None
    bank_category: str | None = None
    currency: str = "EUR"
    type: str = "expense"
    category: str = "Altro"
    import_ref: str = ""
    duplicate: bool = False
    similar_to: str | None = None   # description of an existing transaction this row may duplicate

    @property
    def causale(self) -> str | None:
        return bank_causale({"description": self.description, "details": self.details})

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "description": self.description,
            "amount": str(self.amount),
            "details": self.details,
            "bank_category": self.bank_category,
            "currency": self.currency,
            "type": self.type,
            "category": self.category,
            "import_ref": self.import_ref,
            "duplicate": self.duplicate,
        }


def _cell(row: list, columns: dict[str, int], name: str):
    index = columns.get(name)
    if index is None or index >= len(row):
        return None
    value = row[index]
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def parse_rows(rows: list[list], layout: Layout) -> tuple[list[StatementRow], int]:
    """
    Convert the rows below the header into StatementRows.
    Returns (rows, skipped) where skipped counts pending (not yet booked) movements.
    Lines without a valid date or amount (totals, balances, blank lines) are ignored.
    """
    columns = layout.columns
    parsed: list[StatementRow] = []
    skipped = 0
    for row in rows[layout.header_row + 1:]:
        tx_date = to_date(_cell(row, columns, "date"))
        if tx_date is None:
            continue

        if "amount" in columns:
            amount = to_decimal(_cell(row, columns, "amount"))
        else:
            credit = to_decimal(_cell(row, columns, "credit")) or Decimal(0)
            debit = to_decimal(_cell(row, columns, "debit")) or Decimal(0)
            amount = abs(credit) - abs(debit) if (credit or debit) else None
        if not valid_amount(amount):
            continue

        status = (clean_text(_cell(row, columns, "status")) or "").lower()
        if any(p in status for p in PENDING_STATUSES):
            skipped += 1
            continue

        description = clean_text(_cell(row, columns, "description"))
        details = clean_text(_cell(row, columns, "details"))
        if details == description:
            details = None
        if not description:
            description, details = details, None
        if not description:
            continue

        currency = (clean_text(_cell(row, columns, "currency")) or "EUR").upper()
        parsed.append(StatementRow(
            date=tx_date,
            description=description,
            amount=amount,
            details=details,
            bank_category=clean_text(_cell(row, columns, "category")),
            currency=currency if re.fullmatch(r"[A-Z]{3}", currency) else "EUR",
        ))
    return parsed, skipped


def fingerprint(row: StatementRow, occurrence: int, bank_key: str) -> str:
    """
    Stable id of a statement row; `occurrence` distinguishes identical rows in the same file.
    The bank is part of the key: the same charge on two different banks' accounts (e.g. Netflix
    on the same day) is two real movements, not a duplicate.
    """
    key = f"{bank_key}|{row.date.isoformat()}|{row.amount:.2f}|{normalize(row.description)}|{occurrence}"
    return hashlib.sha256(key.encode()).hexdigest()


def already_imported(refs: list[str]) -> set[str]:
    """The statement-row fingerprints among `refs` that are already saved as transactions."""
    if not refs:
        return set()
    query = Transaction.query.with_entities(Transaction.import_ref).filter(Transaction.import_ref.in_(refs))
    return {ref for (ref,) in query}


def enrich(rows: list[StatementRow], bank_key: str) -> list[StatementRow]:
    """Assign type, category and import_ref, and flag rows that were already imported."""
    seen: dict[str, int] = {}
    for row in rows:
        if is_transfer(row.description, row.details):
            row.type, row.category = "transfer", "Giroconto"
        else:
            row.type = "expense" if row.amount < 0 else "income"
            row.category = categorize(row.description, row.details, row.bank_category)

        base = fingerprint(row, 0, bank_key)
        occurrence = seen.get(base, 0)
        seen[base] = occurrence + 1
        row.import_ref = fingerprint(row, occurrence, bank_key)

    existing = already_imported([r.import_ref for r in rows])
    for row in rows:
        row.duplicate = row.import_ref in existing
    duplicates.flag_similar_rows([r for r in rows if not r.duplicate])
    return rows


@dataclass
class BalanceCheck:
    """Opening balance + extracted movements must equal the closing balance printed on the statement."""
    opening: Decimal
    closing: Decimal
    movements_total: Decimal

    @property
    def difference(self) -> Decimal:
        return self.closing - (self.opening + self.movements_total)

    @property
    def ok(self) -> bool:
        return abs(self.difference) <= Decimal("0.01")


@dataclass
class StatementPreview:
    bank: BankLayout
    rows: list[StatementRow]
    pending_skipped: int
    ai_model: str | None = None              # set when the movements were read by an AI model
    balance_check: BalanceCheck | None = None
    discarded: int = 0                       # AI rows dropped because the date/amount was invalid

    @property
    def new_rows(self) -> list[StatementRow]:
        return [r for r in self.rows if not r.duplicate]

    @property
    def duplicates(self) -> int:
        return sum(1 for r in self.rows if r.duplicate)

    @property
    def total_income(self) -> Decimal:
        return sum((r.amount for r in self.new_rows if r.type == "income"), Decimal(0))

    @property
    def total_expenses(self) -> Decimal:
        return sum((-r.amount for r in self.new_rows if r.type == "expense"), Decimal(0))

    @property
    def period(self) -> tuple[date, date] | None:
        if not self.rows:
            return None
        dates = [r.date for r in self.rows]
        return min(dates), max(dates)


class AIRequired(StatementImportError):
    """
    The rule-based reader could not read the file, but an AI model could try: the caller must ask the
    user before sending the document to a model. `kind` is "scan", "photo" or "layout".
    """

    def __init__(self, reason: str, kind: str):
        super().__init__(reason)
        self.reason, self.kind = reason, kind

    @property
    def needs_vision(self) -> bool:
        return self.kind in ("scan", "photo")


def analyze_statement(filename: str, raw: bytes, bank: str = AUTO) -> StatementPreview:
    """
    Read a statement with the rule-based readers. Files they cannot read raise AIRequired (never an
    automatic AI call): the user decides whether to read them with an AI model (analyze_with_ai).
    """
    try:
        document = readers.read_document(filename, raw)
    except readers.NeedsOCR as exc:
        raise AIRequired(str(exc), "scan" if readers.is_pdf(raw) else "photo") from exc
    except readers.UnsupportedFile as exc:
        raise StatementImportError(str(exc))

    try:
        rows, pending, layout_bank = _extract_rows(document, filename, bank)
    except StatementImportError as exc:
        raise AIRequired(str(exc), "layout")
    rows.sort(key=lambda r: r.date)
    return StatementPreview(bank=layout_bank, rows=enrich(rows, layout_bank.key), pending_skipped=pending)


def text_for_ai(filename: str, raw: bytes) -> str | None:
    """Plain text of a text-based document, sent to the model when there is no image/PDF to show it."""
    try:
        document = readers.read_document(filename, raw)
    except readers.UnsupportedFile:
        return None
    return "\n".join(document.text_lines) or None


def _bank_from_name(name: str) -> str:
    text = _search_text(name)
    return next((k for k in DETECTION_ORDER if any(m in text for m in BANKS[k].markers)), "generic")


def analyze_with_ai(filename: str, raw: bytes, bank: str = AUTO, model: str | None = None) -> StatementPreview:
    """Read the movements with an AI model (the configured one, or `model`) and validate what it returned."""
    try:
        result = ai_extraction.extract(filename, raw, text_for_ai(filename, raw), model)
    except ai_extraction.AIExtractionError as exc:
        raise StatementImportError(f"Lettura AI non riuscita: {exc}")

    rows: list[StatementRow] = []
    discarded = 0
    for item in result.movements:
        tx_date = to_date(item.get("date"))
        amount = to_decimal(item.get("amount"))
        description = clean_text(item.get("description"))
        if tx_date is None or not valid_amount(amount) or not description:
            discarded += 1
            continue
        rows.append(StatementRow(
            date=tx_date, description=description, amount=amount.quantize(Decimal("0.01")),
            details=clean_text(item.get("details")),
        ))
    if not rows:
        raise StatementImportError("Lettura AI: nessun movimento riconosciuto nel documento.")

    bank_key = bank if bank != AUTO else _bank_from_name(f"{result.bank_name} {filename}")
    rows.sort(key=lambda r: r.date)
    check = None
    if result.has_balances:
        check = BalanceCheck(
            opening=Decimal(str(result.opening_balance)).quantize(Decimal("0.01")),
            closing=Decimal(str(result.closing_balance)).quantize(Decimal("0.01")),
            movements_total=sum((r.amount for r in rows), Decimal(0)),
        )
    return StatementPreview(
        bank=BANKS[bank_key], rows=enrich(rows, bank_key), pending_skipped=0,
        ai_model=result.model, balance_check=check, discarded=discarded,
    )


def _extract_rows(document: readers.Document, filename: str, bank: str) -> tuple[list[StatementRow], int, BankLayout]:
    """Try each view of the document, from the most to the least structured; first one with movements wins."""
    candidates = list(document.tables)
    if document.lines:
        rebuilt = rebuild_columns(document.lines, document.char_width, bank, filename)
        if rebuilt:
            candidates.append(rebuilt)

    error: StatementImportError | None = None
    for table in candidates:
        try:
            layout = detect_layout(table, filename, bank)
        except StatementImportError as exc:
            error = error or exc
            continue
        rows, pending = parse_rows(table, layout)
        if rows:
            return rows, pending, layout.bank

    if document.text_lines and bank in (AUTO, "generic"):
        rows = parse_text_lines(document.text_lines)
        if rows:
            return rows, 0, BANKS["generic"]

    raise error or StatementImportError("Nessun movimento trovato nel file.")


def bank_causale(row: dict) -> str | None:
    """The bank's full original text for a statement row: description plus its detail column."""
    description, details = clean_text(row.get("description")), clean_text(row.get("details"))
    if not description:
        return details
    if details and details.lower() not in description.lower():
        return f"{description} ({details})"
    return description


def build_transaction(base: dict, bank_key: str, fields: dict | None = None, ai: bool = False) -> Transaction:
    """
    Transaction from a statement row (a StatementRow.to_dict()). `fields` are the values as edited in the
    preview (default: the row as read); `base` is empty for rows added by hand. `ai` tags rows read by an
    AI model. Raises ValueError on invalid input.
    The original import_ref and the bank's causale are kept even when the user corrects the row:
    re-importing the same statement still recognizes it, and the bank's text stays on record.
    """
    fields = base if fields is None else fields
    tx_date = to_date(fields.get("date"))
    amount = to_decimal(fields.get("amount"))
    description = clean_text(fields.get("description"))
    tx_type = fields.get("type")
    if tx_date is None or not valid_amount(amount) or not description or tx_type not in TRANSACTION_TYPES:
        raise ValueError("incomplete row")
    tags = ["importato", bank_key] + (["ai"] if ai else []) + ([] if base else ["manuale"])
    if fields.get("aicat"):
        tags.append("categoria-ai")  # category suggested by the AI and accepted unchanged: worth a later review
    return Transaction(
        date=tx_date,
        description=description,
        amount=abs(amount).quantize(Decimal("0.01")),
        currency=base.get("currency") or "EUR",
        type=tx_type,
        category=clean_text(fields.get("category")) or "Altro",
        counterparty=clean_text(fields.get("counterparty")),
        tags=tags,
        is_recurring=False,
        notes=base.get("details"),
        import_ref=base.get("import_ref"),
        bank_description=bank_causale(base) if base else None,
    )
