"""
Import / export of transactions (CSV, JSON; the manual column-mapping import also reads Excel and .ods).
"""
import csv
import io
from datetime import date, datetime

from app.models.transaction import Transaction
from app.services.parsing import TRANSACTION_TYPES, parse_amount, parse_date
from app.services.periods import month_bounds, year_bounds

EXPORT_FIELDS = [
    "id", "date", "description", "amount", "currency", "type", "category",
    "counterparty", "tags", "is_recurring", "recurrence", "recurrence_end", "notes", "bank_description",
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
    query = Transaction.query
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
        "counterparty": tx.counterparty,
        "tags": list(tx.tags or []),
        "is_recurring": bool(tx.is_recurring),
        "recurrence": tx.recurrence,
        "recurrence_end": tx.recurrence_end.isoformat() if tx.recurrence_end else None,
        "notes": tx.notes,
        "bank_description": tx.bank_description,
    }


def to_csv(transactions) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_FIELDS, delimiter=";")
    writer.writeheader()
    for tx in transactions:
        row = tx_to_dict(tx)
        row["tags"] = ", ".join(row["tags"])
        writer.writerow(row)
    return buffer.getvalue()


def is_tax_relevant(tx: Transaction) -> bool:
    """Income is always declared; expenses only when tagged as deductible."""
    tags = {t.lower() for t in (tx.tags or [])}
    return tx.type == "income" or bool(tags & TAX_TAGS)


# ── Import ─────────────────────────────────────────────────────────────────────

def read_csv(content: str) -> tuple[list[str], list[dict]]:
    """Parse CSV text, sniffing the delimiter. Returns (headers, rows)."""
    content = content.lstrip("\ufeff")
    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    return list(reader.fieldnames or []), list(reader)


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


def read_table(filename: str, raw: bytes) -> tuple[list[str], list[dict], int]:
    """
    Read a CSV or spreadsheet (.xlsx, .xls, .ods) for the manual column mapping.
    Returns (headers, rows as {header: text}, line number of the first data row). Rows above the header
    (bank name, account holder, period) are skipped.
    """
    from app.services import statement_readers as readers

    name = filename.lower()
    if not name.endswith(MAPPING_EXTENSIONS):
        raise TableError("Formato non supportato: carica un file CSV, Excel (.xlsx, .xls) o LibreOffice (.ods).")
    if name.endswith((".csv", ".txt", ".tsv")):
        headers, rows = read_csv(readers.decode_text(raw))
        return headers, rows, 2
    try:
        document = readers.read_document(filename, raw)
    except readers.UnsupportedFile as exc:
        raise TableError(str(exc))
    if document.kind not in ("xlsx", "xls", "odf", "html") or not document.tables:
        raise TableError("Il file non contiene un foglio di calcolo: caricalo in formato CSV, .xlsx, .xls o .ods.")
    # .ods: the first "table" is the text preamble plus every sheet merged; the real first sheet follows
    table = document.tables[1] if document.kind == "odf" and len(document.tables) > 1 else document.tables[0]
    cells = [[_cell_text(c) for c in row] for row in table]
    if not any(any(row) for row in cells):
        raise TableError("Il foglio è vuoto.")
    header_at = _header_index(cells)
    headers, seen = [], set()
    for position, title in enumerate(cells[header_at], start=1):
        title = title or f"Colonna {position}"
        while title in seen:
            title = f"{title} ({position})"
        seen.add(title)
        headers.append(title)
    rows = [dict(zip(headers, row + [""] * (len(headers) - len(row)))) for row in cells[header_at + 1:]]
    while rows and not any(rows[-1].values()):
        rows.pop()
    return headers, rows, header_at + 2


def rows_to_transactions(rows: list[dict], mapping: dict, first_line: int = 2) -> tuple[list[Transaction], list[str]]:
    """
    Build Transaction objects from CSV / spreadsheet rows (`first_line` is the file line of the first row).

    `mapping` maps model fields ("date", "amount", "description", optional "category",
    "type", "counterparty") to CSV column names. When no type column is mapped, the sign
    of the amount decides: negative → expense, positive → income.
    """
    transactions, errors = [], []
    for line_no, row in enumerate(rows, start=first_line):
        if not any((value or "").strip() for value in row.values() if isinstance(value, str)):
            continue  # blank line
        try:
            amount = parse_amount(row.get(mapping["amount"]) or "")
            description = (row.get(mapping["description"]) or "").strip()
            if not description:
                raise ValueError("descrizione mancante")

            tx_type = (row.get(mapping.get("type") or "") or "").strip().lower()
            if tx_type not in TRANSACTION_TYPES:
                tx_type = "expense" if amount < 0 else "income"

            transactions.append(Transaction(
                date=parse_date(row.get(mapping["date"]) or ""),
                description=description,
                amount=abs(amount),
                currency="EUR",
                type=tx_type,
                category=(row.get(mapping.get("category") or "") or "").strip() or None,
                counterparty=(row.get(mapping.get("counterparty") or "") or "").strip() or None,
                tags=[],
                is_recurring=False,
            ))
        except ValueError as exc:
            errors.append(f"Riga {line_no}: {exc}")
    return transactions, errors
