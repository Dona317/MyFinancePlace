"""
Bank statement import (Excel / CSV) → transactions.

Supported layouts (auto-detected from the header columns, or from the bank's name above the header / in the filename):
  • Fineco         — "Data_Operazione | Data_Valuta | Entrate | Uscite | Descrizione | Descrizione_Completa | Stato | Moneymap"
  • Intesa Sanpaolo — "Data | Operazione | Dettagli | Conto o carta | Contabilizzazione | Categoria | Valuta | Importo"
                      (older exports: "Data contabile | Data valuta | Descrizione | Accrediti | Addebiti | Descrizione estesa")
  • UniCredit      — "Data Registrazione | Data Valuta | Descrizione | Importo (EUR)"
  • BPER Banca     — "Data contabile | Data valuta | Causale ABI | Descrizione | Importo | Divisa"
  • Poste Italiane — BancoPosta "Data Contabile | Data Valuta | Addebiti (euro) | Accrediti (euro) | Descrizione operazioni"
  • ING            — "Data contabile | Data valuta | Uscite | Entrate | Causale | Descrizione operazione"
  • Revolut        — "Type | Product | Started Date | Completed Date | Description | Amount | Fee | Currency | State | Balance"
                      rows whose State is not COMPLETED (pending, reverted, declined) are excluded; a non-zero Fee
                      becomes a separate "Commissione Revolut" expense, so the category of the payment stays clean
                      and the fees add up under "Commissioni"
  • N26            — "Booking Date | Value Date | Partner Name | Partner Iban | Type | Payment Reference | Account Name |
                      Amount (EUR) | Original Amount | Original Currency | Exchange Rate"
                      (older exports: "Date | Payee | Account number | Transaction type | Payment reference | Amount (EUR) | …")
  • Generic        — any statement whose header has a date, a description and either a signed amount
                      or separate credit/debit columns (Banca Sella, Mediolanum, BCC, …)

Accepted files: Excel (.xlsx/.xls), CSV, TXT, PDF (text-based), Word (.docx and 97-2003 .doc), RTF, OpenDocument (.ods/.odt).

Pipeline:  readers.read_document() → candidate tables → detect_layout() → parse_rows() → enrich() (category, dedup)
  • Structured tables (spreadsheets, Word/ODF tables, ruled PDF tables, delimited text) are tried first.
  • Column layouts without a real table (PDF text, fixed-width TXT) are rebuilt from the header positions.
  • Last resort: lines shaped like "date … description … amount".
  • Scans, photos and layouts none of the above can read raise AIRequired: after the user confirms,
    analyze_with_ai() reads them with a model (services/ai_extraction.py); the result is validated and
    balance-checked before the preview.
Bank export preamble rows (account holder, period, balances) and footer rows are skipped automatically.
"""
from .build import bank_causale, build_transaction  # noqa: F401
from .categorize import (  # noqa: F401
    _RULE_PATTERNS,
    _TRANSFER_PATTERN,
    CATEGORY_RULES,
    TRANSFER_KEYWORDS,
    categorize,
    is_transfer,
    search_text,
)
from .layouts import (  # noqa: F401
    AUTO,
    BANKS,
    DETECTION_ORDER,
    FORMAT_LAYOUTS,
    HEADER_SCAN_ROWS,
    PENDING_STATUSES,
    BankLayout,
    Layout,
    _match_columns,
    detect_layout,
    header_key,
    identify_bank,
    layout_for_headers,
    layout_named,
)
from .model import (  # noqa: F401
    AIRequired,
    BalanceCheck,
    StatementImportError,
    StatementPreview,
    StatementRow,
)
from .pipeline import (  # noqa: F401
    _DATED_LINE,
    _TYPE_WORDS,
    _bank_from_name,
    _explicit_type,
    _extract_rows,
    _read_with_ocr,
    _structured_preview,
    analyze_statement,
    analyze_with_ai,
    preview_from_ai,
    preview_from_mapping,
    read_with_ai,
    text_for_ai,
)
from .rows import _cell, already_imported, enrich, fingerprint, parse_rows  # noqa: F401
from .text_layout import (  # noqa: F401
    AMOUNT_FIELDS,
    AMOUNT_PATTERN,
    AMOUNT_TOKEN,
    DATE_TOKEN,
    INCOME_HINTS,
    PAGE_FOOTER,
    TEXT_LINE,
    _find_header,
    _header_cells,
    _HeaderCell,
    parse_text_lines,
    rebuild_columns,
)
from .transfers import already_complete, complete, flag_pairs, other_half  # noqa: F401
