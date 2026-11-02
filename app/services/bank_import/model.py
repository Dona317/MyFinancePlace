"""What a statement becomes: rows, the balance check, the preview, and the import errors."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from app.services import categories, money
from app.services.parsing import clean_text

if TYPE_CHECKING:  # only an annotation here; layouts imports this module
    from .layouts import BankLayout


# ── Errors ──────────────────────────────────────────────────────────────

class StatementImportError(ValueError):
    """Raised with a user-facing (Italian) message when a statement cannot be read."""


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
    category: str = categories.FALLBACK
    import_ref: str = ""
    duplicate: bool = False
    similar_to: str | None = None   # description of an existing transaction this row may duplicate
    pairs_with: str | None = None   # a giroconto whose other half is saved: it will be joined to it
    own_account_id: int | None = None  # the account whose IBAN the row names (a bonifico between own accounts)
    counterparty: str | None = None  # merchant / payee: from a column, else read from the causale (first tag)

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
            "counterparty": self.counterparty,
            "pairs": bool(self.pairs_with),
            "own_account": self.own_account_id,
        }


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
        return abs(self.difference) <= money.CENT


@dataclass
class StatementPreview:
    bank: BankLayout
    rows: list[StatementRow]
    pending_skipped: int
    ai_model: str | None = None              # set when the movements were read by an AI model
    ocr: bool = False                        # read from a scan or photo by the light OCR
    ocr_doubtful: bool = False               # fewer rows than dated lines: something was probably missed
    notes: list[str] = field(default_factory=list)    # columns corrected in a mapped import
    unread: list[str] = field(default_factory=list)   # "Riga 7: data mancante" — rows of the file not read
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


def bank_causale(row: dict) -> str | None:
    """The bank's full original text for a statement row: description plus its detail column."""
    description, details = clean_text(row.get("description")), clean_text(row.get("details"))
    if not description:
        return details
    if details and details.lower() not in description.lower():
        return f"{description} ({details})"
    return description
