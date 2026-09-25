"""
Reading values typed by people or exported by banks: dates, amounts and free text.
Shared by the CSV import, the bank-statement import and the transaction forms.
"""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y")
MAX_AMOUNT = Decimal("9" * 36 + ".99")  # transactions.amount is Numeric(38, 2): no practical limit
TRANSACTION_TYPES = ("income", "expense", "transfer")


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
        raise ValueError(f"importo non valido: '{value}'") from None


def to_date(value) -> date | None:
    """A date from a cell (date, datetime or text, possibly with a time); None if it isn't one."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return parse_date(str(value).split(" ")[0])
    except ValueError:
        return None


def to_decimal(value) -> Decimal | None:
    """
    A signed amount from a cell: numbers, "1.234,56", "€ 12,00", "12,00-" and "(12,00)" (negative).
    None when it isn't a finite number ("NaN" and "Infinity" are not amounts).
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        amount = Decimal(str(value))
        return amount if amount.is_finite() else None
    text = str(value).replace("EUR", "").replace("€", "").strip()
    negative = text.endswith("-") or (text.startswith("(") and text.endswith(")"))
    text = text.strip("()+ ").rstrip("-")
    if not text:
        return None
    try:
        amount = parse_amount(text)
    except (ValueError, InvalidOperation):
        return None
    if not amount.is_finite():
        return None
    return -abs(amount) if negative else amount


def valid_amount(amount: Decimal | None) -> bool:
    """A usable movement amount: finite, not zero, and small enough for the database column."""
    return amount is not None and amount.is_finite() and Decimal(0) < abs(amount) <= MAX_AMOUNT


def clean_text(value) -> str | None:
    """Text with its whitespace collapsed; None when empty."""
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def normalize(value) -> str:
    """Lowercase words and numbers only: "Data_Operazione" → "data operazione"."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())
