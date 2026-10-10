"""From the table's rows to statement rows: amounts, dates, pending ones, fees, duplicates."""
from __future__ import annotations

import hashlib
import re
from decimal import Decimal

from app.models.transaction import Transaction
from app.services import duplicates, history_classifier, merchant
from app.services.parsing import clean_text, normalize, to_date, to_decimal, valid_amount

from .categorize import categorize, is_transfer
from .layouts import PENDING_STATUSES, Layout
from .model import StatementRow
from .transfers import flag_pairs


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
        booked = layout.bank.booked_statuses
        if any(p in status for p in PENDING_STATUSES) or (booked and status not in booked):
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
        currency = currency if re.fullmatch(r"[A-Z]{3}", currency) else "EUR"
        parsed.append(StatementRow(
            date=tx_date,
            description=description,
            amount=amount,
            details=details,
            bank_category=clean_text(_cell(row, columns, "category")),
            currency=currency,
        ))
        fee = to_decimal(_cell(row, columns, "fee"))
        if valid_amount(fee):  # charged on top of the amount: a separate expense (see the module docstring)
            parsed.append(StatementRow(
                date=tx_date, description=f"Commissione {layout.bank.name}: {description}",
                amount=-abs(fee), details=details, currency=currency,
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
    query = (Transaction.query.with_entities(Transaction.import_ref, Transaction.counter_import_ref)
             .filter(Transaction.import_ref.in_(refs) | Transaction.counter_import_ref.in_(refs)))
    return {ref for pair in query for ref in pair} & set(refs)


def enrich(rows: list[StatementRow], bank_key: str) -> list[StatementRow]:
    """Assign type, category and import_ref, and flag rows that were already imported."""
    seen: dict[str, int] = {}
    history = history_classifier.index()  # read once for the whole statement
    for row in rows:
        if is_transfer(row.description, row.details):
            row.type, row.category = "transfer", "Giroconto"
        else:
            row.type = "expense" if row.amount < 0 else "income"
            row.category = categorize(row.description, row.details, row.bank_category, row.amount > 0, history)
            # the merchant named in the causale, unless a column of the file already gave it
            row.counterparty = row.counterparty or merchant.extract(row.description, row.details)

        base = fingerprint(row, 0, bank_key)
        occurrence = seen.get(base, 0)
        seen[base] = occurrence + 1
        row.import_ref = fingerprint(row, occurrence, bank_key)

    existing = already_imported([r.import_ref for r in rows])
    for row in rows:
        row.duplicate = row.import_ref in existing
    flag_pairs(rows)
    duplicates.flag_similar_rows([r for r in rows if not r.duplicate and not r.pairs_with])
    return rows
