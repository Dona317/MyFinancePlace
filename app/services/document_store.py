"""
Files of the document archive, kept under <instance>/documents with a random name
(the original name stays in the database, so two files called "fattura.pdf" never clash).
"""
import contextlib
import mimetypes
import secrets
from pathlib import Path

from flask import current_app

DOC_TYPES = ["Fattura", "Scontrino", "Estratto conto", "Contratto", "Polizza", "CU / 730", "Ricevuta", "Altro"]
INLINE_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp"}  # safe to show in the browser


def folder() -> Path:
    path = Path(current_app.instance_path) / "documents"
    path.mkdir(parents=True, exist_ok=True)
    return path


def path_of(stored_name: str) -> Path:
    path = (folder() / stored_name).resolve()
    if path.parent != folder().resolve():  # never outside the archive folder
        raise FileNotFoundError(stored_name)
    return path


def new_name(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    suffix = suffix if suffix[1:].isalnum() and len(suffix) <= 10 else ""
    return secrets.token_hex(16) + suffix


def save(filename: str, raw: bytes) -> tuple[str, str]:
    """Store the bytes; returns (stored name, mimetype)."""
    stored = new_name(filename)
    path_of(stored).write_bytes(raw)
    mimetype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return stored, mimetype


def write(stored_name: str, raw: bytes) -> None:
    """Put back a file under its stored name (restore from a backup)."""
    path_of(stored_name).write_bytes(raw)


def read(stored_name: str) -> bytes | None:
    try:
        return path_of(stored_name).read_bytes()
    except (FileNotFoundError, OSError):
        return None


def remove(stored_name: str) -> None:
    with contextlib.suppress(FileNotFoundError):
        path_of(stored_name).unlink(missing_ok=True)
