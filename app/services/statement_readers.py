"""
Readers that turn any supported bank-statement file into data the importer can analyze.

Supported: Excel (.xlsx, .xls, HTML saved as .xls), CSV, TXT (delimited or fixed-width), PDF (text-based),
Word (.docx, 97-2003 .doc), RTF, OpenDocument (.ods, .odt). Images and scanned PDFs raise NeedsOCR, which the importer
hands to the AI reader when one is configured (services/ai_extraction.py).

Every reader returns a `Document` with up to three views of the file, from most to least structured:
  • tables — explicit tables (spreadsheet sheets, Word/ODF tables, ruled PDF tables, delimited text)
  • lines  — words with their horizontal position, for statements laid out in columns without a real
             table (PDF text, fixed-width TXT); bank_import rebuilds the columns from the header positions
  • text_lines — plain text, for the last-resort "date … amount" line parser
"""
import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from statistics import median
from xml.etree import ElementTree
from flask_babel import gettext as _

OLE2_MAGIC = b"\xd0\xcf\x11\xe0"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".webp")


def is_pdf(raw: bytes) -> bool:
    return raw[:5] == b"%PDF-"


def is_image(raw: bytes) -> bool:
    """JPEG, PNG, GIF or WebP, recognized from the first bytes (the extension can be wrong)."""
    return (raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n" or raw[:4] == b"GIF8"
            or (raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"))


class UnsupportedFile(ValueError):
    """Raised with a user-facing (Italian) message when a file cannot be read."""


class NeedsOCR(UnsupportedFile):
    """The file is an image or a scanned PDF: only AI/OCR reading can extract its movements."""


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    page: int = 0

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Document:
    kind: str
    tables: list[list[list]] = field(default_factory=list)
    lines: list[list[Word]] = field(default_factory=list)
    text_lines: list[str] = field(default_factory=list)
    char_width: float = 1.0


# ── Entry point ────────────────────────────────────────────────────────────────

def read_document(filename: str, raw: bytes) -> Document:
    if not raw:
        raise UnsupportedFile(_("Il file è vuoto."))
    name = filename.lower()

    if is_pdf(raw):
        return _read_pdf(raw)
    if raw[:2] == b"PK":
        return _read_zip_document(raw)
    if raw[:4] == OLE2_MAGIC:
        if name.endswith((".doc", ".dot")) or _is_word_binary(raw):
            return _read_doc(raw)
        return _read_xls(raw)
    if name.endswith(IMAGE_EXTENSIONS) or is_image(raw):
        raise NeedsOCR(_("Le immagini non sono supportate: scarica dall'home banking il PDF, l'Excel o il CSV dei movimenti."))

    text = decode_text(raw)
    if raw[:5] == b"{\\rtf":
        return text_document("rtf", _rtf_to_text(text))
    if text.lstrip()[:1] == "<":
        return Document(kind="html", tables=[_html_rows(text)])
    return text_document("csv" if name.endswith(".csv") else "txt", text)


def decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


# ── Spreadsheets ───────────────────────────────────────────────────────────────

def _read_xlsx(raw: bytes) -> Document:
    import openpyxl
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:
        raise UnsupportedFile(_("Impossibile leggere il file Excel: %(exc)s", exc=exc))
    return Document(kind="xlsx", tables=[[list(row) for row in workbook.active.iter_rows(values_only=True)]])


def _read_xls(raw: bytes) -> Document:
    import xlrd
    try:
        book = xlrd.open_workbook(file_contents=raw)
    except Exception as exc:
        raise UnsupportedFile(_("Impossibile leggere il file Excel: %(exc)s", exc=exc))
    sheet = book.sheet_by_index(0)
    rows = []
    for r in range(sheet.nrows):
        row = []
        for c in range(sheet.ncols):
            cell = sheet.cell(r, c)
            if cell.ctype == xlrd.XL_CELL_DATE:
                row.append(xlrd.xldate_as_datetime(cell.value, book.datemode))
            else:
                row.append(cell.value)
        rows.append(row)
    return Document(kind="xls", tables=[rows])


def _read_zip_document(raw: bytes) -> Document:
    """.xlsx, .docx, .ods and .odt are all zip archives: tell them apart by their contents."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = set(archive.namelist())
            if "xl/workbook.xml" in names:
                return _read_xlsx(raw)
            if "word/document.xml" in names:
                return _read_docx(raw)
            if "content.xml" in names:
                return _read_odf(archive.read("content.xml"))
    except zipfile.BadZipFile:
        pass
    raise UnsupportedFile(_("Formato non riconosciuto: carica un file Excel, CSV, TXT, PDF, Word o OpenDocument."))


# ── HTML (bank "Excel" exports that are really HTML tables) ─────────────────────

def _html_rows(text: str) -> list[list[str]]:
    from html.parser import HTMLParser

    class TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows, self.row, self.cell = [], None, None

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.row = []
            elif tag in ("td", "th") and self.row is not None:
                self.cell = []

        def handle_endtag(self, tag):
            if tag in ("td", "th") and self.row is not None and self.cell is not None:
                self.row.append(" ".join("".join(self.cell).split()))
                self.cell = None
            elif tag == "tr" and self.row is not None:
                self.rows.append(self.row)
                self.row = None

        def handle_data(self, data):
            if self.cell is not None:
                self.cell.append(data)

    parser = TableParser()
    parser.feed(text)
    if not parser.rows:
        raise UnsupportedFile(_("Il file non contiene tabelle leggibili."))
    return parser.rows


# ── Plain text (CSV, TXT, RTF, Word paragraphs) ─────────────────────────────────

def text_document(kind: str, text: str) -> Document:
    """Delimited table (if any) + fixed-width positioned lines + plain lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    document = Document(kind=kind, text_lines=text.split("\n"), char_width=1.0)

    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        rows = [row for row in csv.reader(io.StringIO(text), dialect)]
    except csv.Error:
        # The sniffer gives up on short files with a preamble ("BPER Banca" above the header)
        delimiter = _common_delimiter(sample)
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter)) if delimiter else []
    if sum(1 for row in rows if len(row) >= 3) >= 2:
        document.tables.append(rows)
    if "\t" in text:
        document.tables.append([line.split("\t") for line in document.text_lines])

    # Fixed-width layout: character offsets act as x coordinates, one line per row
    for number, line in enumerate(document.text_lines):
        words = [Word(m.group(), m.start(), m.end(), number) for m in re.finditer(r"\S+", line.expandtabs(8))]
        document.lines.append(words)
    return document


def _common_delimiter(sample: str) -> str | None:
    """The delimiter that splits the most lines into the same number (≥ 2) of separators."""
    lines = [line for line in sample.split("\n")[:50] if line.strip()]
    best, best_score = None, 1
    for delimiter in ";,\t|":
        counts = [line.count(delimiter) for line in lines]
        common = max(set(counts), key=counts.count) if counts else 0
        score = counts.count(common) if common >= 2 else 0
        if score > best_score:
            best, best_score = delimiter, score
    return best


def _rtf_to_text(rtf: str) -> str:
    """Minimal RTF → text: keeps paragraphs, tabs and table cells, drops formatting."""
    text = re.sub(r"\{\\\*[^{}]*\}", "", rtf)                      # ignorable destinations
    text = re.sub(r"\{\\(fonttbl|colortbl|stylesheet|info)[^{}]*(\{[^{}]*\}[^{}]*)*\}", "", text)
    text = re.sub(r"\\(par|line|row)\b ?", "\n", text)
    text = re.sub(r"\\(tab|cell)\b ?", "\t", text)
    text = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes.fromhex(m.group(1)).decode("cp1252"), text)
    text = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)
    text = text.replace("\\{", "{").replace("\\}", "}").replace("\\\\", "\\")
    return re.sub(r"[{}]", "", text)


# ── Word (.docx) ───────────────────────────────────────────────────────────────

def _read_docx(raw: bytes) -> Document:
    import docx
    try:
        document = docx.Document(io.BytesIO(raw))
    except Exception as exc:
        raise UnsupportedFile(_("Impossibile leggere il documento Word: %(exc)s", exc=exc))

    paragraphs = [p.text for p in document.paragraphs]
    preamble = [[p] for p in paragraphs[:15] if p.strip()]
    tables = []
    for table in document.tables:
        rows = []
        for row in table.rows:
            cells, previous = [], None
            for cell in row.cells:  # merged cells are repeated by python-docx: keep one copy
                if cell._tc is not previous:
                    cells.append(cell.text)
                previous = cell._tc
            rows.append(cells)
        tables.append(rows)

    result = text_document("docx", "\n".join(paragraphs))
    if tables:
        merged = preamble + [row for table in tables for row in table]
        result.tables = [merged] + [preamble + t for t in tables] + result.tables
    return result


# ── Word 97-2003 (.doc) ────────────────────────────────────────────────────────
#
# A .doc is an OLE2 container. Its "WordDocument" stream starts with the FIB (file information block),
# which points to the piece table (CLX) in the "0Table"/"1Table" stream; the piece table says where each
# run of characters of the main text is stored (8-bit cp1252 or UTF-16). Table cells end with \x07, and
# every row ends with one more \x07. Pure Python (olefile), so no antiword/LibreOffice is needed.

DOC_UNREADABLE = "Impossibile leggere il documento Word 97-2003 (.doc): aprilo in Word e salvalo come .docx o PDF."


def _is_word_binary(raw: bytes) -> bool:
    import olefile
    try:
        with olefile.OleFileIO(raw) as ole:
            return ole.exists("WordDocument")
    except Exception:
        return False


def _read_doc(raw: bytes) -> Document:
    return text_document("doc", "\n".join(doc_text_lines(raw)))


def doc_text_lines(raw: bytes) -> list[str]:
    """The main text of a Word 97-2003 document, one line per paragraph and one tab-separated line per table row."""
    import struct

    import olefile
    try:
        ole = olefile.OleFileIO(raw)
    except Exception:
        raise UnsupportedFile(DOC_UNREADABLE)
    with ole:
        if not ole.exists("WordDocument"):
            raise UnsupportedFile(DOC_UNREADABLE)
        word = ole.openstream("WordDocument").read()
        if len(word) < 0x200 or struct.unpack_from("<H", word, 0)[0] != 0xA5EC:
            raise UnsupportedFile(DOC_UNREADABLE)
        flags = struct.unpack_from("<H", word, 0x0A)[0]
        if flags & 0x0100:
            raise UnsupportedFile(_("Il documento Word è protetto da password: salvalo senza password e riprova."))
        if struct.unpack_from("<H", word, 0x02)[0] < 101:  # Word 6/95: different structures
            raise UnsupportedFile(DOC_UNREADABLE)
        table_name = "1Table" if flags & 0x0200 else "0Table"
        if not ole.exists(table_name):
            raise UnsupportedFile(DOC_UNREADABLE)
        table = ole.openstream(table_name).read()

    try:
        csw = struct.unpack_from("<H", word, 0x20)[0]
        lw_start = 0x22 + csw * 2 + 2
        cslw = struct.unpack_from("<H", word, lw_start - 2)[0]
        ccp_text = struct.unpack_from("<i", word, lw_start + 12)[0]         # FibRgLw97.ccpText
        blob = lw_start + cslw * 4 + 2                                     # FibRgFcLcb97
        fc_clx, lcb_clx = struct.unpack_from("<II", word, blob + 33 * 8)  # fcClx / lcbClx
        text = _doc_pieces(word, table[fc_clx:fc_clx + lcb_clx], ccp_text)
    except (struct.error, ValueError):
        raise UnsupportedFile(DOC_UNREADABLE)
    return _doc_lines(text)


def _doc_pieces(word: bytes, clx: bytes, ccp_text: int) -> str:
    """Concatenate the pieces of the main text described by the CLX (skipping its Prc formatting blocks)."""
    import struct
    pos = 0
    while pos < len(clx) and clx[pos] == 0x01:              # Prc: 0x01, cbGrpprl, grpprl
        pos += 3 + struct.unpack_from("<h", clx, pos + 1)[0]
    if pos >= len(clx) or clx[pos] != 0x02:
        raise ValueError(_("no piece table"))
    lcb = struct.unpack_from("<I", clx, pos + 1)[0]
    plc = clx[pos + 5:pos + 5 + lcb]
    count = (lcb - 4) // 12
    cps = struct.unpack_from(f"<{count + 1}I", plc, 0)
    parts, total = [], 0
    for i in range(count):
        start, end = cps[i], min(cps[i + 1], ccp_text)
        if end <= start:
            break
        fc = struct.unpack_from("<I", plc, (count + 1) * 4 + i * 8 + 2)[0]
        length = end - start
        if fc & 0x40000000:                                  # compressed: 8-bit cp1252 at fc / 2
            offset = (fc & 0x3FFFFFFF) // 2
            parts.append(word[offset:offset + length].decode("cp1252", errors="replace"))
        else:
            parts.append(word[fc:fc + 2 * length].decode("utf-16-le", errors="replace"))
        total += length
        if total >= ccp_text:
            break
    return "".join(parts)


def _strip_fields(text: str) -> str:
    """Fields are \\x13 code \\x14 result \\x15 (or \\x13 code \\x15): keep only the results."""
    out, stack = [], []   # stack: True while inside the code part of a field
    for char in text:
        if char == "\x13":
            stack.append(True)
        elif char == "\x14" and stack:
            stack[-1] = False
        elif char == "\x15" and stack:
            stack.pop()
        elif not any(stack):
            out.append(char)
    return "".join(out)


def _doc_lines(text: str) -> list[str]:
    text = _strip_fields(text).replace("\x0b", " ").replace("\x0c", "\r").replace("\x1e", "-").replace("\xa0", " ")
    text = re.sub(r"[\x00-\x06\x08\x0e-\x1f]", "", text)
    lines: list[str] = []
    for paragraph in text.split("\r"):
        if "\x07" not in paragraph:
            lines.append(paragraph)
            continue
        # Table rows: n cell marks followed by the row mark (an empty "cell"); find the smallest n that fits
        *cells, trailing = paragraph.split("\x07")
        width = next(
            (n for n in range(1, min(len(cells), 64) + 1)
             if len(cells) % (n + 1) == 0 and all(cells[k] == "" for k in range(n, len(cells), n + 1))),
            None,
        )
        if width is None:
            lines.append("\t".join(cells))
        else:
            lines.extend("\t".join(cells[k:k + width]) for k in range(0, len(cells), width + 1))
        if trailing:
            lines.append(trailing)
    return lines


# ── OpenDocument (.ods / .odt) ─────────────────────────────────────────────────

ODF = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
}


def _read_odf(content: bytes) -> Document:
    root = ElementTree.fromstring(content)
    q = lambda ns, tag: f"{{{ODF[ns]}}}{tag}"  # noqa: E731
    tables = []
    for table in root.iter(q("table", "table")):
        rows = []
        for row in table.iter(q("table", "table-row")):
            cells = []
            for cell in row:
                if cell.tag not in (q("table", "table-cell"), q("table", "covered-table-cell")):
                    continue
                value = (
                    cell.get(q("office", "date-value"))
                    or cell.get(q("office", "value"))
                    or "\n".join("".join(p.itertext()) for p in cell.iter(q("text", "p")))
                )
                repeat = min(int(cell.get(q("table", "number-columns-repeated"), "1")), 50)
                cells.extend([value] * repeat)
            while cells and not cells[-1]:
                cells.pop()
            rows.append(cells)
        tables.append(rows)
    if not tables:
        raise UnsupportedFile(_("Il documento non contiene tabelle con i movimenti."))
    paragraphs = [[p] for p in ("".join(e.itertext()) for e in root.iter(q("text", "p"))) if p.strip()][:10]
    merged = [row for table in tables for row in table]
    return Document(kind="odf", tables=[paragraphs + merged] + tables)


# ── PDF ────────────────────────────────────────────────────────────────────────

def _read_pdf(raw: bytes) -> Document:
    import pdfplumber
    document = Document(kind="pdf")
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            ruled_rows = []
            widths = []
            for page_number, page in enumerate(pdf.pages):
                for table in page.extract_tables():
                    ruled_rows.extend(table)
                words = page.extract_words(x_tolerance=1.5, y_tolerance=2, keep_blank_chars=False)
                for w in words:
                    widths.append((w["x1"] - w["x0"]) / max(len(w["text"]), 1))
                document.lines.extend(group_lines(
                    [Word(w["text"], w["x0"], w["x1"], w["top"], page_number) for w in words]
                ))
                document.text_lines.extend((page.extract_text() or "").split("\n"))
    except Exception as exc:
        raise UnsupportedFile(_("Impossibile leggere il PDF: %(exc)s", exc=exc))

    if not any(line.strip() for line in document.text_lines):
        raise NeedsOCR(
            _("Il PDF non contiene testo (probabilmente è una scansione): scarica dall'home banking "
            "il PDF originale oppure l'Excel/CSV dei movimenti.")
        )
    document.char_width = median(widths) if widths else 4.0
    if ruled_rows:
        preamble = [[line] for line in document.text_lines[:15]]
        document.tables.append(preamble + ruled_rows)
    return document


def group_lines(words: list[Word], tolerance: float = 2.5) -> list[list[Word]]:
    """Cluster words of one page into lines by their vertical position."""
    lines: list[list[Word]] = []
    for word in sorted(words, key=lambda w: (w.top, w.x0)):
        if lines and abs(lines[-1][0].top - word.top) <= tolerance:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: w.x0) for line in lines]
