"""
Import / export of transactions (CSV, JSON).
"""
import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.models.transaction import Transaction

EXPORT_FIELDS = [
    "id", "date", "description", "amount", "currency", "type", "category",
    "counterparty", "tags", "is_recurring", "recurrence", "recurrence_end", "notes",
]

TAX_TAGS = {"deducibile", "detraibile", "fiscale"}

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y")


# ── Export ─────────────────────────────────────────────────────────────────────

def period_bounds(period: str, today: date | None = None) -> tuple[date | None, date | None]:
    """Translate an export period keyword into [start, end) dates (None = unbounded)."""
    today = today or date.today()
    if period == "year":
        return date(today.year, 1, 1), date(today.year + 1, 1, 1)
    if period == "last_year":
        return date(today.year - 1, 1, 1), date(today.year, 1, 1)
    if period == "month":
        start = date(today.year, today.month, 1)
        end = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)
        return start, end
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

def parse_date(value: str) -> date:
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"data non riconosciuta: '{value}'")


def parse_amount(value: str) -> Decimal:
    """Accept both '1.234,56' (Italian) and '1,234.56' / '1234.56' formats."""
    raw = value.strip().replace("€", "").replace(" ", "")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation:
        raise ValueError(f"importo non valido: '{value}'")


def read_csv(content: str) -> tuple[list[str], list[dict]]:
    """Parse CSV text, sniffing the delimiter. Returns (headers, rows)."""
    content = content.lstrip("\ufeff")
    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    return list(reader.fieldnames or []), list(reader)


def rows_to_transactions(rows: list[dict], mapping: dict) -> tuple[list[Transaction], list[str]]:
    """
    Build Transaction objects from CSV rows.

    `mapping` maps model fields ("date", "amount", "description", optional "category",
    "type", "counterparty") to CSV column names. When no type column is mapped, the sign
    of the amount decides: negative → expense, positive → income.
    """
    transactions, errors = [], []
    for line_no, row in enumerate(rows, start=2):  # line 1 is the header
        try:
            amount = parse_amount(row.get(mapping["amount"]) or "")
            description = (row.get(mapping["description"]) or "").strip()
            if not description:
                raise ValueError("descrizione mancante")

            tx_type = (row.get(mapping.get("type") or "") or "").strip().lower()
            if tx_type not in ("income", "expense", "transfer"):
                tx_type = "expense" if amount < 0 else "income"

            transactions.append(Transaction(
                date=parse_date(row.get(mapping["date"]) or ""),
                description=description[:255],
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
