"""
Light OCR for scanned PDFs and photos (RapidOCR: ONNX models of ~16 MB, CPU only, offline).

It turns each page into positioned words, the same shape the PDF reader produces from a text PDF, so the
usual column rebuilding reads the table: no language model is needed for most scans. When the package is
missing or finds nothing, the caller falls back to the AI reader.
"""
from __future__ import annotations

import io
from statistics import median

from app.services import statement_readers as readers

RENDER_SCALE = 2          # PDF pages rendered at 144 dpi: enough for statement fonts, fast on a CPU
LINE_TOLERANCE = 0.6      # words whose tops differ by less than 60% of a text line are on the same line
_engine = None


def available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True


def _ocr():
    global _engine
    if _engine is None:  # loading the models takes a second: once per process
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


def _images(raw: bytes) -> list[bytes]:
    if not readers.is_pdf(raw):
        from PIL import Image, ImageOps

        image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))  # phone photos: honour the rotation flag
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        return [buffer.getvalue()]
    import pypdfium2 as pdfium

    pages = []
    for page in pdfium.PdfDocument(raw):
        buffer = io.BytesIO()
        page.render(scale=RENDER_SCALE).to_pil().save(buffer, format="PNG")
        pages.append(buffer.getvalue())
    return pages


def read(raw: bytes) -> readers.Document | None:
    """The scan or photo as a Document of positioned words; None when nothing could be read."""
    document = readers.Document(kind="ocr")
    widths = []
    for number, image in enumerate(_images(raw)):
        boxes, _elapsed = _ocr()(image)
        words = []
        heights = []
        for box, text, _confidence in boxes or []:
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            words.append(readers.Word(text, min(xs), max(xs), min(ys), number))
            heights.append(max(ys) - min(ys))
            widths.append((max(xs) - min(xs)) / max(len(text), 1))
        if not words:
            continue
        lines = readers.group_lines(words, tolerance=median(heights) * LINE_TOLERANCE)
        document.lines.extend(lines)
        document.text_lines.extend(" ".join(w.text for w in line) for line in lines)
    if not document.lines:
        return None
    document.char_width = median(widths)
    return document
