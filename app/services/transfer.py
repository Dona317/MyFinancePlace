"""
Import / export of transactions (CSV, JSON; the manual column-mapping import also reads Excel and .ods).
"""
import csv
import io
from datetime import date, datetime

from sqlalchemy.orm import selectinload

from app.models.transaction import Transaction
from app.services import categories, display
from app.services.periods import month_bounds, year_bounds
from flask_babel import gettext as _

EXPORT_FIELDS = [
    "id", "date", "description", "amount", "currency", "type", "category", "main_category",
    "counterparty", "tags", "is_recurring", "recurrence", "recurrence_end", "notes", "bank_description", "splits",
]

TAX_TAGS = {"deducibile", "detraibile", "fiscale"}

# ── Export ─────────────────────────────────────────────────────────────────────

def period_bounds(period: str, today: date | None = None) -> tuple[date | None, date | None]:
    """Translate an export period keyword into [start, end) dates (None = unbounded)."""
    today = today or date.today()
    if period == "year":
        return year_bounds(today.year)
    if period == "last_year":
        return year_bounds(today.year - 1)
    if period == "month":
        return month_bounds(today.year, today.month)
    return None, None


def query_transactions(start: date | None = None, end: date | None = None):
    query = Transaction.query.options(selectinload(Transaction.splits))
    if start:
        query = query.filter(Transaction.date >= start)
    if end:
        query = query.filter(Transaction.date < end)
    return query.order_by(Transaction.date, Transaction.id).all()


def tx_to_dict(tx: Transaction) -> dict:
    return {
        "id": tx.id,
        "date": tx.date.isoformat() if tx.date else None,
        "description": tx.description,
        "amount": float(tx.amount) if tx.amount is not None else None,
        "currency": tx.currency,
        "type": tx.type,
        "category": tx.category,
        "main_category": categories.top(tx.category),  # the same as category unless it is a subcategory
        "counterparty": tx.counterparty,
        "tags": list(tx.tags or []),
        "is_recurring": bool(tx.is_recurring),
        "recurrence": tx.recurrence,
        "recurrence_end": tx.recurrence_end.isoformat() if tx.recurrence_end else None,
        "notes": tx.notes,
        "bank_description": tx.bank_description,
        # a split transaction: its parts (category, amount); [] for the others
        "splits": [{"category": s.category, "amount": float(s.amount)} for s in tx.splits],
    }


def to_csv(transactions) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_FIELDS, delimiter=";")
    writer.writeheader()
    for tx in transactions:
        row = tx_to_dict(tx)
        row["tags"] = ", ".join(row["tags"])
        row["splits"] = "; ".join(f"{s['category']} {display.number(s['amount'])}" for s in row["splits"])
        writer.writerow(row)
    return buffer.getvalue()


def is_tax_relevant(tx: Transaction) -> bool:
    """Income is always declared; expenses only when tagged as deductible."""
    tags = {t.lower() for t in (tx.tags or [])}
    return tx.type == "income" or bool(tags & TAX_TAGS)


# ── Import ─────────────────────────────────────────────────────────────────────

def csv_cells(content: str) -> list[list[str]]:
    """CSV text as rows of cells. The delimiter that splits every line alike wins over the sniffer, which takes
    the decimal comma of "-45,20" for the separator when there is no header."""
    from app.services.statement_readers import common_delimiter

    content = content.lstrip("\ufeff")
    delimiter = common_delimiter(content[:8192])
    if not delimiter:
        try:
            delimiter = csv.Sniffer().sniff(content[:4096], delimiters=";,\t").delimiter
        except csv.Error:
            delimiter = ","
    return [[" ".join(cell.split()) for cell in row] for row in csv.reader(io.StringIO(content), delimiter=delimiter)]


MAPPING_EXTENSIONS = (".csv", ".txt", ".tsv", ".xlsx", ".xlsm", ".xls", ".ods")
HEADER_SCAN_ROWS = 40


class TableError(ValueError):
    """Raised with a user-facing (Italian) message when a file for the manual mapping cannot be read."""


def _cell_text(value) -> str:
    """A spreadsheet cell as the text the mapping import parses: dates as YYYY-MM-DD, 12.0 as 12."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    return " ".join(str(value).split())


def _header_index(rows: list[list[str]]) -> int:
    """The header row: the first one filled almost as much as the widest row (skips titles and preambles)."""
    scan = rows[:HEADER_SCAN_ROWS]
    widest = max((sum(1 for c in row if c) for row in scan), default=0)
    for index, row in enumerate(scan):
        if sum(1 for c in row if c) >= max(2, widest * 0.8):
            return index
    return 0


def _is_data_row(row: list[str]) -> bool:
    """A row holding a date and an amount is a movement, not a header."""
    from app.services.column_guess import is_amount, is_date

    return any(is_date(c) for c in row if c) and any(is_amount(c) for c in row if c)


def read_table(filename: str, raw: bytes) -> tuple[list[str], list[dict], int]:
    """
    Read a CSV or spreadsheet (.xlsx, .xls, .ods) for the manual column mapping.
    Returns (headers, rows as {header: text}, line number of the first data row). Rows above the header
    (bank name, account holder, period) are skipped.
    """
    from app.services import statement_readers as readers

    name = filename.lower()
    if not name.endswith(MAPPING_EXTENSIONS):
        raise TableError(_("Formato non supportato: carica un file CSV, Excel (.xlsx, .xls) o LibreOffice (.ods)."))
    if name.endswith((".csv", ".txt", ".tsv")):
        try:
            cells = csv_cells(readers.decode_text(raw))
        except csv.Error as exc:  # binary data, a broken quote, a cell of megabytes
            raise TableError(_("Il file non è un CSV leggibile (%(exc)s): controlla che sia il file giusto.", exc=exc))
    else:
        try:
            document = readers.read_document(filename, raw)
        except readers.UnsupportedFile as exc:
            raise TableError(str(exc))
        if document.kind not in ("xlsx", "xls", "odf", "html") or not document.tables:
            raise TableError(_("Il file non contiene un foglio di calcolo: caricalo in formato CSV, .xlsx, .xls o .ods."))
        # .ods: the first "table" is the text preamble plus every sheet merged; the real first sheet follows
        table = document.tables[1] if document.kind == "odf" and len(document.tables) > 1 else document.tables[0]
        cells = [[_cell_text(c) for c in row] for row in table]
    if not any(any(row) for row in cells):
        raise TableError(_("Il foglio è vuoto."))
    header_at = _header_index(cells)
    titles = cells[header_at]
    if _is_data_row(titles):  # no header at all: the first row is a movement, the columns get numbered
        titles, header_at = [""] * max(len(row) for row in cells), header_at - 1
    headers, seen = [], set()
    for position, title in enumerate(titles, start=1):
        title = title or f"Colonna {position}"
        while title in seen:
            title = f"{title} ({position})"
        seen.add(title)
        headers.append(title)
    rows = [dict(zip(headers, row + [""] * (len(headers) - len(row)))) for row in cells[header_at + 1:]]
    while rows and not any(rows[-1].values()):
        rows.pop()
    return headers, rows, header_at + 2
