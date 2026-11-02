"""Bank statement layouts: the columns of each bank's export and how a header is recognized."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from flask_babel import gettext as _

from app.services import structured_statements as structured
from app.services.parsing import normalize

from .categorize import search_text
from .model import StatementImportError

HEADER_SCAN_ROWS = 40
PENDING_STATUSES = ("non contabilizzat", "autorizzat", "in attesa", "pending", "da contabilizzare")


# ── Bank layouts ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BankLayout:
    key: str
    name: str
    markers: tuple[str, ...]              # text in the preamble / filename identifying the bank
    # Header names only this bank uses; a tuple entry needs all of its names ("started date" + "completed date")
    signature: tuple[str | tuple[str, ...], ...]
    columns: dict[str, tuple[str, ...]]   # field → accepted (normalized) header names, by priority
    # When set, only rows whose status is one of these are booked (Revolut: "completed"); the others
    # (pending, reverted, declined) are skipped like the "non contabilizzato" rows of the Italian banks
    booked_statuses: tuple[str, ...] = ()

    def signature_in(self, headers: list[str]) -> bool:
        present = set(headers)
        return any(set(sig) <= present if isinstance(sig, tuple) else sig in present for sig in self.signature)


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
    "unicredit": BankLayout(
        key="unicredit",
        name="UniCredit",
        markers=("unicredit",),
        signature=(("data registrazione", "importo eur"),),
        columns={
            "date":        ("data registrazione", "data operazione", "data contabile", "data"),
            "description": ("descrizione", "descrizione operazione"),
            "details":     ("causale",),
            "amount":      ("importo eur", "importo euro", "importo"),
            "credit":      ("entrate", "accrediti", "avere"),
            "debit":       ("uscite", "addebiti", "dare"),
            "currency":    ("divisa",),
        },
    ),
    "bper": BankLayout(
        key="bper",
        name="BPER Banca",
        markers=("bper", "banca popolare dell emilia romagna", "banco di sardegna"),
        signature=("causale abi",),
        columns={
            "date":        ("data contabile", "data operazione", "data"),
            "description": ("descrizione", "descrizione operazione"),
            "details":     ("causale abi", "causale"),
            "amount":      ("importo", "importo eur"),
            "credit":      ("avere", "accrediti", "entrate"),
            "debit":       ("dare", "addebiti", "uscite"),
            "currency":    ("divisa",),
        },
    ),
    "poste": BankLayout(
        key="poste",
        name="Poste Italiane (BancoPosta)",
        markers=("bancoposta", "poste italiane", "postepay"),
        signature=("descrizione operazioni",),
        columns={
            "date":        ("data contabile", "data operazione", "data"),
            "description": ("descrizione operazioni", "descrizione"),
            "amount":      ("importo", "importo euro"),
            "credit":      ("accrediti euro", "accrediti"),
            "debit":       ("addebiti euro", "addebiti"),
        },
    ),
    "ing": BankLayout(
        key="ing",
        name="ING",
        markers=(" ing ", "conto arancio"),  # padded: "ing" alone, not inside "booking"
        signature=(("descrizione operazione", "causale", "entrate", "uscite"),),
        columns={
            "date":        ("data contabile", "data operazione", "data"),
            "description": ("descrizione operazione", "descrizione"),
            "details":     ("causale",),
            "amount":      ("importo",),
            "credit":      ("entrate",),
            "debit":       ("uscite",),
        },
    ),
    "revolut": BankLayout(
        key="revolut",
        name="Revolut",
        markers=("revolut",),
        signature=(("started date", "completed date"), ("product", "state", "fee")),
        columns={
            # Started Date is always filled; Completed Date is empty on pending and reverted rows
            "date":        ("started date", "completed date", "date"),
            "description": ("description",),
            # "Type" (CARD_PAYMENT, ATM, TOPUP…) is left out: as a detail it would mislead the keyword
            # categorization (the "ATM" of a cash withdrawal is not the Milan transit company)
            "amount":      ("amount",),
            "fee":         ("fee",),
            "currency":    ("currency",),
            "status":      ("state",),
        },
        booked_statuses=("completed",),
    ),
    "n26": BankLayout(
        key="n26",
        name="N26",
        markers=("n26",),
        signature=("partner name", "partner iban", "payment reference", ("payee", "transaction type")),
        columns={
            "date":        ("booking date", "date", "value date"),
            "description": ("partner name", "payee"),
            "details":     ("payment reference", "type", "transaction type"),
            "amount":      ("amount eur", "amount"),
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

# Interchange formats (structured_statements): no columns to find, any bank
FORMAT_LAYOUTS = {key: BankLayout(key=key, name=name, markers=(), signature=(), columns={})
                  for key, name in structured.FORMATS.items()}


def layout_named(key: str) -> BankLayout:
    """The bank or file format a preview was read with (saved in the preview payload)."""
    return BANKS.get(key) or FORMAT_LAYOUTS.get(key) or BANKS["generic"]


AUTO = "auto"
DETECTION_ORDER = ("fineco", "intesa", "unicredit", "bper", "poste", "ing", "revolut", "n26", "generic")

# ── Layout detection ───────────────────────────────────────────────────────────

def header_key(value) -> str:
    """A header cell as compared with the layouts: lowercase, no accents, words and numbers only."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    return normalize("".join(c for c in text if not unicodedata.combining(c)))


def _match_columns(headers: list[str], layout: BankLayout) -> dict[str, int] | None:
    """Map layout fields to column indexes; None if the header lacks the required columns."""
    mapping: dict[str, int] = {}
    used: set[int] = set()
    for field_name in ("date", "description", "amount", "credit", "debit", "details",
                       "category", "currency", "status", "fee"):
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


def identify_bank(rows: list[list], filename: str) -> str | None:
    """The bank named in the filename or in `rows` (the callers pass only the rows above the header:
    a "Ricarica Revolut" movement in a Fineco statement must not make it a Revolut file)."""
    preamble = search_text(filename, *(str(c) for row in rows[:HEADER_SCAN_ROWS] for c in row if c))
    for key in DETECTION_ORDER:
        if any(marker in preamble for marker in BANKS[key].markers):
            return key
    return None


def layout_for_headers(headers: list[str], bank: str = AUTO, identified: str | None = None) -> tuple[str, dict] | None:
    """
    Pick the layout matching a header row. With automatic detection:
      1. the bank named above the header or in the filename, if its columns match;
      2. a bank whose signature columns are present (e.g. Revolut's "Started Date" + "Completed Date");
      3. the generic layout, so a plain "Data | Descrizione | Importo" file is not mislabelled as a specific bank.
    """
    if bank != AUTO:
        keys = [bank]
    else:
        if identified:
            columns = _match_columns(headers, BANKS[identified])
            if columns:
                return identified, columns
        for key in DETECTION_ORDER:
            columns = _match_columns(headers, BANKS[key])
            if columns and BANKS[key].signature_in(headers):
                return key, columns
        keys = ["generic", *DETECTION_ORDER]
    for key in keys:
        columns = _match_columns(headers, BANKS[key])
        if columns:
            return key, columns
    return None


def detect_layout(rows: list[list], filename: str = "", bank: str = AUTO) -> Layout:
    if bank != AUTO and bank not in BANKS:
        raise StatementImportError(_("Banca non supportata: %(bank)s", bank=bank))

    for index, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        headers = [header_key(c) for c in row]
        identified = identify_bank(rows[:index], filename) if bank == AUTO else None
        found = layout_for_headers(headers, bank, identified)
        if found:
            key, columns = found
            return Layout(bank=BANKS[key], header_row=index, columns=columns, headers=headers)

    expected = "Data, Descrizione e Importo (oppure Entrate/Uscite)"
    raise StatementImportError(_("Intestazione dei movimenti non trovata: servono almeno le colonne %(expected)s.", expected=expected))
