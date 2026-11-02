"""Reading a statement end to end: file → tables → layout → rows, or OCR / AI when needed."""
from __future__ import annotations

import re
from decimal import Decimal

from flask_babel import gettext as _

from app.services import ai_extraction, categories, column_guess, money, ocr
from app.services import statement_readers as readers
from app.services import structured_statements as structured
from app.services.parsing import clean_text, normalize, to_date, to_decimal, valid_amount

from .categorize import search_text
from .layouts import AUTO, BANKS, DETECTION_ORDER, FORMAT_LAYOUTS, BankLayout, detect_layout
from .model import AIRequired, BalanceCheck, StatementImportError, StatementPreview, StatementRow
from .rows import enrich, parse_rows
from .text_layout import parse_text_lines, rebuild_columns


def analyze_statement(filename: str, raw: bytes, bank: str = AUTO) -> StatementPreview:
    """
    Read a statement with the rule-based readers. Files they cannot read raise AIRequired (never an
    automatic AI call): the user decides whether to read them with an AI model (analyze_with_ai).
    """
    try:
        statement = structured.parse(filename, raw)
    except structured.StructuredFileError as exc:
        raise StatementImportError(str(exc))
    if statement is not None:
        return _structured_preview(statement)
    try:
        document = readers.read_document(filename, raw)
    except readers.NeedsOCR as exc:
        preview = _read_with_ocr(filename, raw, bank)
        if preview:
            return preview
        raise AIRequired(str(exc), "scan" if readers.is_pdf(raw) else "photo") from exc
    except readers.UnsupportedFile as exc:
        raise StatementImportError(str(exc))

    try:
        rows, pending, layout_bank = _extract_rows(document, filename, bank)
    except StatementImportError as exc:
        raise AIRequired(str(exc), "layout")
    rows.sort(key=lambda r: r.date)
    return StatementPreview(bank=layout_bank, rows=enrich(rows, layout_bank.key), pending_skipped=pending)


def _structured_preview(statement: structured.Statement) -> StatementPreview:
    """An OFX / QIF / CAMT statement as the usual preview: types, categories, merchants and duplicates as for any bank."""
    rows = [StatementRow(date=m.date, description=m.description, amount=m.amount, details=m.details,
                         currency=m.currency, counterparty=m.counterparty) for m in statement.movements]
    layout = FORMAT_LAYOUTS[statement.format]
    enrich(rows, layout.key)
    known = {name.casefold(): name for name in categories.known_categories()}
    for row, movement in zip(rows, statement.movements):
        if movement.transfer:
            row.type, row.category = "transfer", "Giroconto"
        elif movement.category and row.type != "transfer":  # the file's own category, when it is one of ours
            parts = [movement.category, *reversed(movement.category.split(":"))]
            match = next((known[p.strip().casefold()] for p in parts if p.strip().casefold() in known), None)
            row.category = match or row.category
    check = None
    if statement.opening is not None and statement.closing is not None:
        check = BalanceCheck(opening=statement.opening, closing=statement.closing,
                             movements_total=sum((r.amount for r in rows), Decimal(0)))
    return StatementPreview(bank=layout, rows=rows, pending_skipped=statement.skipped, unread=statement.unread,
                            balance_check=check)


_DATED_LINE = re.compile(r"^\s*\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}")


def _read_with_ocr(filename: str, raw: bytes, bank: str) -> StatementPreview | None:
    """A scan or photo read by the light OCR and the usual column rebuilding; None → ask about the AI reader."""
    if not ocr.available():
        return None
    try:
        document = ocr.read(raw)
        if document is None:
            return None
        rows, pending, layout_bank = _extract_rows(document, filename, bank)
    except (StatementImportError, readers.UnsupportedFile, OSError, ValueError):
        return None
    dated = sum(1 for line in document.text_lines if _DATED_LINE.match(line))
    rows.sort(key=lambda r: r.date)
    return StatementPreview(bank=layout_bank, rows=enrich(rows, layout_bank.key), pending_skipped=pending,
                            ocr=True, ocr_doubtful=len(rows) < 0.9 * dated)


# ── A CSV / spreadsheet with the columns chosen by the user (Esporta → Importa con mappatura) ─────────

_TYPE_WORDS = {
    "expense": {"expense", "uscita", "uscite", "addebito", "addebiti", "dare", "spesa"},
    "income": {"income", "entrata", "entrate", "accredito", "accrediti", "avere"},
    "transfer": {"transfer", "giroconto", "trasferimento"},
}


def _explicit_type(value: str | None) -> str | None:
    word = normalize(value)
    return next((kind for kind, words in _TYPE_WORDS.items() if word in words), None)


class _UnreadRow(Exception):
    """A row of a mapped file that cannot be imported; the message says why."""


def _mapped_amount(cell, columns: dict) -> Decimal | None:
    if columns["amount"]:
        return to_decimal(cell("amount"))
    debit, credit = to_decimal(cell("debit")), to_decimal(cell("credit"))  # money in minus money out
    return None if debit is None and credit is None else abs(credit or 0) - abs(debit or 0)


def _mapped_row(cell, columns: dict, line: int) -> tuple[StatementRow, str | None, str | None]:
    """A row of a mapped file, its explicit type and its category; _UnreadRow when it cannot be read."""
    tx_date, amount = to_date(cell("date")), _mapped_amount(cell, columns)
    counterparty = clean_text(cell("counterparty"))
    description = clean_text(cell("description")) or counterparty
    if tx_date is None:
        raise _UnreadRow(_("Riga %(line)s: data non riconosciuta («%(value)s»)", line=line, value=cell("date")))
    if not valid_amount(amount):
        raise _UnreadRow(_("Riga %(line)s: importo mancante o non valido", line=line))
    if not description:
        raise _UnreadRow(_("Riga %(line)s: descrizione mancante", line=line))
    kind = _explicit_type(cell("type"))
    if kind in ("expense", "income"):  # the type column wins over a missing sign
        amount = -abs(amount) if kind == "expense" else abs(amount)
    row = StatementRow(date=tx_date, description=description, amount=money.cents(amount), counterparty=counterparty)
    return row, kind, clean_text(cell("category"))


def _apply_file_overrides(rows: list[StatementRow], extras: list[tuple[str | None, str | None]]) -> None:
    """After the automatic categories: the file's transfers and its own categories win over the guessed ones."""
    for row, (kind, category) in zip(rows, extras):
        if kind == "transfer":
            row.type, row.category = "transfer", "Giroconto"
        if category:
            row.category = category


def preview_from_mapping(headers: list[str], rows: list[dict], mapping: dict, first_line: int = 2) -> StatementPreview:
    """
    The rows of a mapped file as an editable preview. The mapping is first checked against the values (a date
    column without dates is swapped for the one with them, with a note); rows that still cannot be read are
    listed instead of failing the whole import.
    """
    checked = column_guess.fix(mapping, headers, rows)
    columns = checked.mapping
    if not columns["date"] or not (columns["amount"] or (columns["debit"] and columns["credit"])):
        raise StatementImportError(_("Non trovo le colonne di data e importo: sceglile a mano."))

    parsed, unread, extras = [], [], []
    for line, row in enumerate(rows, start=first_line):
        if not any(isinstance(v, str) and v.strip() for v in row.values()):
            continue

        def cell(name: str, row=row) -> str:
            return (row.get(columns[name]) or "").strip() if columns.get(name) else ""

        try:
            statement_row, kind, category = _mapped_row(cell, columns, line)
        except _UnreadRow as exc:
            unread.append(str(exc))
            continue
        parsed.append(statement_row)
        extras.append((kind, category))
    if not parsed:
        raise StatementImportError(_("Nessuna riga leggibile con queste colonne.") + (" " + unread[0] if unread else ""))

    enrich(parsed, "generic")
    _apply_file_overrides(parsed, extras)
    order = sorted(range(len(parsed)), key=lambda i: parsed[i].date)
    return StatementPreview(bank=BANKS["generic"], rows=[parsed[i] for i in order], pending_skipped=0,
                            notes=checked.notes, unread=unread)


def text_for_ai(filename: str, raw: bytes) -> str | None:
    """Plain text of a text-based document, sent to the model when there is no image/PDF to show it."""
    try:
        document = readers.read_document(filename, raw)
    except readers.UnsupportedFile:
        return None
    return "\n".join(document.text_lines) or None


def _bank_from_name(name: str) -> str:
    text = search_text(name)
    return next((k for k in DETECTION_ORDER if any(m in text for m in BANKS[k].markers)), "generic")


def analyze_with_ai(filename: str, raw: bytes, bank: str = AUTO, model: str | None = None) -> StatementPreview:
    """Read the movements with an AI model (the configured one, or `model`) and validate what it returned."""
    return preview_from_ai(filename, read_with_ai(filename, raw, model), bank)


def read_with_ai(filename: str, raw: bytes, model: str | None = None,
                 progress: ai_extraction.Progress | None = None) -> ai_extraction.AIExtraction:
    """The slow part of analyze_with_ai: the model reading the document (see ai_jobs for the background run)."""
    try:
        return ai_extraction.extract(filename, raw, text_for_ai(filename, raw), model, progress)
    except ai_extraction.AIExtractionError as exc:
        raise StatementImportError(_("Lettura AI non riuscita: %(exc)s", exc=exc))


def preview_from_ai(filename: str, result: ai_extraction.AIExtraction, bank: str = AUTO) -> StatementPreview:
    """Validate what the model returned and build the editable preview."""
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
            date=tx_date, description=description, amount=money.cents(amount),
            details=clean_text(item.get("details")),
        ))
    if not rows:
        raise StatementImportError(_("Lettura AI: nessun movimento riconosciuto nel documento."))

    bank_key = bank if bank != AUTO else _bank_from_name(f"{result.bank_name} {filename}")
    rows.sort(key=lambda r: r.date)
    check = None
    if result.has_balances:
        check = BalanceCheck(
            opening=money.cents(str(result.opening_balance)),
            closing=money.cents(str(result.closing_balance)),
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

    raise error or StatementImportError(_("Nessun movimento trovato nel file."))
