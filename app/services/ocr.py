"""
Light OCR for scanned PDFs and photos (RapidOCR: ONNX models of ~16 MB, CPU only, offline).

It turns each page into positioned words, the same shape the PDF reader produces from a text PDF, so the
usual column rebuilding reads the table: no language model is needed for most scans. When the package is
missing or finds nothing, the caller falls back to the AI reader.
"""
from __future__ import annotations

import io
import math
from statistics import median

from app.services import statement_readers as readers

RENDER_SCALE = 2          # PDF pages rendered at 144 dpi: enough for statement fonts, fast on a CPU
LINE_TOLERANCE = 0.6      # words whose tops differ by less than 60% of a text line are on the same line
_engine = None


def _module():
    """The OCR package: `rapidocr` (3.x, any Python from 3.8 to 3.13) or the older `rapidocr_onnxruntime` (1.x, not
    on Python 3.13); None when neither is installed."""
    for name in ("rapidocr", "rapidocr_onnxruntime"):
        try:
            return __import__(name)
        except ImportError:
            continue
    return None


def available() -> bool:
    return _module() is not None


def _ocr():
    global _engine
    if _engine is None:  # loading the models takes a second: once per process
        _engine = _module().RapidOCR()
    return _engine


def _boxes(image: bytes) -> list[tuple]:
    """(box, text, confidence) of every piece of text: the 3.x engine answers with an object, the 1.x one with a
    (list, elapsed) pair."""
    result = _ocr()(image)
    if hasattr(result, "txts"):
        if result.boxes is None:
            return []
        return list(zip(result.boxes.tolist(), result.txts, result.scores))
    boxes, _elapsed = result
    return boxes or []


def _skew(found: list[tuple]) -> float:
    """The page's tilt (radians), from the top edge of the longer pieces of text: a phone photo is rarely straight,
    and a tilt of one degree is enough to put the amount of a row on the next line."""
    angles = []
    for box, text, _confidence in found:
        (x0, y0), (x1, y1) = box[0], box[1]
        if len(text) >= 6 and x1 - x0 > 20:
            angles.append(math.atan2(y1 - y0, x1 - x0))
    return median(angles) if angles else 0.0


def _rotate(point, angle: float) -> tuple[float, float]:
    """The point turned back by `angle` around the page's corner: the text lines become horizontal."""
    x, y = point[0], point[1]
    cos, sin = math.cos(-angle), math.sin(-angle)
    return x * cos - y * sin, x * sin + y * cos


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
        words = []
        heights = []
        found = _boxes(image)
        turn = _skew(found)
        for box, text, _confidence in found:
            box = [_rotate(point, turn) for point in box]
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
