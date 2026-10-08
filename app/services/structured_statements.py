"""
Statement files in the banks' interchange formats (F6), read without guessing columns:

- OFX / QFX (Open Financial Exchange, the "Money / Quicken" download): version 1 is SGML, where most tags are never
  closed, version 2 is XML; both are read tag by tag from the <STMTTRN> blocks.
- QIF (Quicken Interchange Format): one field per line ("D" date, "T" amount, "P" payee, "M" memo, "L" category),
  records ended by "^". The dates have no fixed order: day and month are told apart by the file's own dates.
- CAMT.053 / CAMT.052 (ISO 20022, the SEPA bank-to-customer statement): XML read with the standard library; only
  booked entries count, and the opening and closing balances give the usual balance check.

`parse` returns None when the file is not one of them, so the other readers can try.
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from flask_babel import gettext as _

from app.services.parsing import clean_text, to_decimal, valid_amount
from app.services.money import CENT

FORMATS = {"ofx": "OFX", "qif": "QIF", "camt": "CAMT.053 (ISO 20022)"}
QIF_ACCOUNT_TYPES = ("bank", "ccard", "cash", "oth a", "oth l")


class StructuredFileError(ValueError):
    """A file in one of these formats that cannot be read (user-facing message)."""


@dataclass
class Movement:
    date: date
    amount: Decimal                 # signed: negative = money out
    description: str
    details: str | None = None
    counterparty: str | None = None   # a named party (CAMT); OFX/QIF payees go through the merchant reader
    currency: str = "EUR"
    category: str | None = None     # the file's own category (QIF "L")
    transfer: bool = False          # QIF "L[Account]": a transfer between own accounts


@dataclass
class Statement:
    format: str                     # key of FORMATS
    movements: list[Movement]
    skipped: int = 0                # entries not booked yet (CAMT "PDNG")
    unread: list[str] = field(default_factory=list)
    opening: Decimal | None = None
    closing: Decimal | None = None


def detect(raw: bytes) -> str | None:
    head = raw[:4096].lstrip(b"\xef\xbb\xbf \t\r\n").upper()
    if head.startswith(b"OFXHEADER") or b"<OFX>" in head or head.startswith(b"<?OFX") or b"<?OFX " in head:
        return "ofx"
    if head.startswith(b"!TYPE:") or head.startswith(b"!ACCOUNT") or head.startswith(b"!OPTION"):
        return "qif"
    if b"URN:ISO:STD:ISO:20022:TECH:XSD:CAMT.05" in raw[:8192].upper():
        return "camt"
    return None


def parse(filename: str, raw: bytes) -> Statement | None:
    kind = detect(raw)
    if kind is None:
        return None
    statement = {"ofx": _ofx, "qif": _qif, "camt": _camt}[kind](_text(raw) if kind != "camt" else raw)
    if not statement.movements:
        raise StructuredFileError(_("Il file %(format)s non contiene movimenti contabilizzati.", format=FORMATS[kind])
                                  + (" " + statement.unread[0] if statement.unread else ""))
    statement.movements.sort(key=lambda m: m.date)
    return statement


def _text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")  # pragma: no cover - latin-1 decodes any byte


def _amount(text: str | None) -> Decimal | None:
    if not text:
        return None
    text = text.strip()
    if re.fullmatch(r"[+-]?\d+([.,]\d+)?", text):  # no thousands separator: the only mark is the decimal one
        try:
            return Decimal(text.replace(",", ".")).quantize(CENT)
        except InvalidOperation:  # pragma: no cover - the pattern only lets numbers through
            return None
    amount = to_decimal(text)
    return amount.quantize(CENT) if amount is not None else None


# ── OFX / QFX ──────────────────────────────────────────────────────────────────

_OFX_BLOCK = re.compile(r"<STMTTRN>(.*?)(?=</STMTTRN>|<STMTTRN>|</BANKTRANLIST>|\Z)", re.S | re.I)


def _ofx_field(block: str, tag: str) -> str | None:
    match = re.search(rf"<{tag}>([^<\r\n]*)", block, re.I)
    return clean_text(html.unescape(match.group(1))) if match else None


def _ofx_date(value: str | None) -> date | None:
    match = re.match(r"(\d{4})(\d{2})(\d{2})", value or "")
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))) if match else None
    except ValueError:
        return None


def _ofx(text: str) -> Statement:
    currency = (_ofx_field(text, "CURDEF") or "EUR").upper()
    movements, unread = [], []
    for number, match in enumerate(_OFX_BLOCK.finditer(text), start=1):
        block = match.group(1)
        when, amount = _ofx_date(_ofx_field(block, "DTPOSTED")), _amount(_ofx_field(block, "TRNAMT"))
        name, memo = _ofx_field(block, "NAME") or _ofx_field(block, "PAYEE"), _ofx_field(block, "MEMO")
        if when is None or not valid_amount(amount):
            unread.append(_("Movimento %(number)s: data o importo non validi", number=number))
            continue
        description = name or memo or _ofx_field(block, "TRNTYPE") or "?"
        movements.append(Movement(date=when, amount=amount, description=description,
                                  details=memo if memo and memo != description else None,
                                  currency=currency if re.fullmatch(r"[A-Z]{3}", currency) else "EUR"))
    closing = _amount(_ofx_field(text.split("<LEDGERBAL>", 1)[1], "BALAMT")) if "<LEDGERBAL>" in text.upper() else None
    return Statement("ofx", movements, unread=unread, closing=closing)


# ── QIF ────────────────────────────────────────────────────────────────────────

def _qif_dates(values: list[str]) -> list[date | None]:
    """The dates of the file, reading day and month in the order that makes all of them valid (day first if both do)."""
    parts = []
    for value in values:
        numbers = [int(n) for n in re.findall(r"\d+", value or "")]
        parts.append(numbers if len(numbers) == 3 else None)
    month_first = any(p and len(str(p[0])) < 4 and p[1] > 12 for p in parts) and \
        not any(p and len(str(p[0])) < 4 and p[0] > 12 for p in parts)

    def build(p):
        if p is None:
            return None
        if p[0] > 31:  # 2026-06-05
            year, month, day = p
        else:
            day, month = (p[1], p[0]) if month_first else (p[0], p[1])
            year = p[2]
        year = year + (2000 if year < 70 else 1900) if year < 100 else year
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return [build(p) for p in parts]


def _qif(text: str) -> Statement:
    kind = re.search(r"^!Type:(.*)$", text, re.M | re.I)
    if kind and kind.group(1).strip().lower() not in QIF_ACCOUNT_TYPES:
        raise StructuredFileError(_("Il file QIF è di tipo «%(kind)s»: si importano solo conti, carte e contanti.",
                                    kind=kind.group(1).strip()))
    records, current = [], {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("!"):
            continue
        if line == "^":
            if current:
                records.append(current)
            current = {}
            continue
        code, value = line[0].upper(), line[1:].strip()
        if code in "DTUPMLN" and code not in current:  # the first one wins (split lines "S"/"$" are ignored)
            current[code] = value
    if current:
        records.append(current)

    dates = _qif_dates([r.get("D") for r in records])
    movements, unread = [], []
    for number, (record, when) in enumerate(zip(records, dates), start=1):
        amount = _amount(record.get("T") or record.get("U"))
        if when is None or not valid_amount(amount):
            unread.append(_("Movimento %(number)s: data o importo non validi", number=number))
            continue
        payee, memo = clean_text(record.get("P")), clean_text(record.get("M"))
        category = clean_text(record.get("L"))
        transfer = bool(category and category.startswith("["))
        movements.append(Movement(date=when, amount=amount, description=payee or memo or "?",
                                  details=memo if payee and memo and memo != payee else None,
                                  category=None if transfer else category, transfer=transfer))
    return Statement("qif", movements, unread=unread)


# ── CAMT.053 / CAMT.052 ────────────────────────────────────────────────────────

def _find_text(element, path: str) -> str | None:
    found = element.find(path)
    return clean_text(found.text) if found is not None and found.text else None


def _signed(element) -> Decimal | None:
    amount = _amount(_find_text(element, "{*}Amt"))
    if amount is None:
        return None
    return -abs(amount) if _find_text(element, "{*}CdtDbtInd") == "DBIT" else abs(amount)


def _camt(raw: bytes) -> Statement:
    head = raw[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in raw.upper():  # no DTDs or entities in a bank statement
        raise StructuredFileError(_("Il file XML contiene una dichiarazione DOCTYPE o ENTITY: non viene letto."))
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise StructuredFileError(_("Il file CAMT non è un XML valido: %(exc)s", exc=exc))

    movements, unread, skipped = [], [], 0
    for number, entry in enumerate(root.iterfind(".//{*}Ntry"), start=1):
        status = _find_text(entry, "{*}Sts/{*}Cd") or _find_text(entry, "{*}Sts") or "BOOK"
        if status.upper() != "BOOK":
            skipped += 1
            continue
        amount = _signed(entry)
        day = _find_text(entry, "{*}BookgDt/{*}Dt") or (_find_text(entry, "{*}BookgDt/{*}DtTm") or "")[:10] \
            or _find_text(entry, "{*}ValDt/{*}Dt")
        try:
            when = date.fromisoformat(day) if day else None
        except ValueError:
            when = None
        if when is None or not valid_amount(amount):
            unread.append(_("Movimento %(number)s: data o importo non validi", number=number))
            continue
        party = "Cdtr" if amount < 0 else "Dbtr"
        counterparty = (_find_text(entry, f".//{{*}}RltdPties/{{*}}{party}/{{*}}Nm")
                        or _find_text(entry, f".//{{*}}RltdPties/{{*}}{party}/{{*}}Pty/{{*}}Nm"))
        remittance = clean_text(" ".join(e.text for e in entry.iterfind(".//{*}RmtInf/{*}Ustrd") if e.text))
        info = _find_text(entry, "{*}AddtlNtryInf") or _find_text(entry, ".//{*}AddtlTxInf")
        description = counterparty or remittance or info or "?"
        details = next((d for d in (remittance, info) if d and d != description), None)
        currency = (entry.find("{*}Amt").get("Ccy") or "EUR").upper()
        movements.append(Movement(date=when, amount=amount, description=description, details=details,
                                  counterparty=counterparty, currency=currency))

    balances = {}
    statements = root.findall(".//{*}Stmt") + root.findall(".//{*}Rpt")
    if len(statements) == 1:
        for balance in statements[0].iterfind("{*}Bal"):
            code = _find_text(balance, "{*}Tp/{*}CdOrPrtry/{*}Cd")
            if code in ("OPBD", "PRCD", "CLBD") and code not in balances:
                balances["OPBD" if code == "PRCD" else code] = _signed(balance)
    return Statement("camt", movements, skipped=skipped, unread=unread,
                     opening=balances.get("OPBD"), closing=balances.get("CLBD"))
