"""Statements without a real table (PDF text, fixed-width TXT): columns rebuilt from the header."""
from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median

from app.services.parsing import normalize, to_date, to_decimal
from app.services.statement_readers import Word

from .layouts import AUTO, HEADER_SCAN_ROWS, header_key, identify_bank, layout_for_headers
from .model import StatementRow

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
    texts = [[w.text for w in line] for line in scan]
    for index, line in enumerate(scan):
        identified = identify_bank(texts[:index], filename) if bank == AUTO else None
        for gap in (char_width * 1.2, None):
            cells = _header_cells(line, gap)
            found = layout_for_headers([header_key(c.text) for c in cells], bank, identified)
            if found:
                return index, cells, found[1]
    return None


def _line_spacing_limit(lines: list[list[Word]]) -> float:
    """The largest vertical gap between a movement's lines: about twice the usual line spacing."""
    spacings = [
        b[0].top - a[0].top
        for a, b in zip(lines, lines[1:])
        if a and b and a[0].page == b[0].page and b[0].top > a[0].top
    ]
    return (median(spacings) * 2.2) if spacings else float("inf")


def _is_noise_line(text: str, header_line: str) -> bool:
    """A repeated page header, a page footer or a line without letters or digits."""
    return normalize(text) == header_line or bool(PAGE_FOOTER.match(text)) or not re.search(r"[A-Za-z0-9]", text)


def _place_words(line: list[Word], cells: list[Word], amount_cols: list[int], text_cols: list[int], amount_region: float) -> list[str]:
    """The line's words in the header's columns: amounts to the nearest amount column, text to the column it starts in."""
    row = [""] * len(cells)
    for word in line:
        if AMOUNT_TOKEN.match(word.text) and word.center >= amount_region:
            col = min(amount_cols, key=lambda i: min(abs(word.x1 - cells[i].x1), abs(word.center - cells[i].center)))
        else:
            starts_before = [i for i in text_cols if cells[i].x0 <= word.center]
            col = starts_before[-1] if starts_before else text_cols[0]
        row[col] = f"{row[col]} {word.text}".strip()
    return row


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
    header_line = normalize(" ".join(c.text for c in cells))
    amount_cols = sorted({columns[f] for f in AMOUNT_FIELDS if f in columns})
    text_cols = [i for i in range(len(cells)) if i not in amount_cols]
    amount_region = min(cells[i].x0 for i in amount_cols) - char_width * 10
    date_col, description_col = columns["date"], columns["description"]
    max_gap = _line_spacing_limit(lines[header_index + 1:])

    table: list[list] = [[" ".join(w.text for w in line)] for line in lines[:header_index]]
    table.append([c.text for c in cells])
    current: list | None = None
    previous_top, previous_page = None, None

    for line in lines[header_index + 1:]:
        if not line or _is_noise_line(" ".join(w.text for w in line), header_line):
            current = None
            continue
        row = _place_words(line, cells, amount_cols, text_cols, amount_region)
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
