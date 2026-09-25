"""
Short-lived storage for uploaded statements waiting for the user's decision (e.g. "read it with AI?").
Files live in <instance>/pending_uploads/<token> and are removed after use or after MAX_AGE_SECONDS.
"""
import json
import re
import secrets
import time
from pathlib import Path

from flask import current_app

MAX_AGE_SECONDS = 2 * 3600
TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,64}$")


def _folder() -> Path:
    folder = Path(current_app.instance_path) / "pending_uploads"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _paths(token: str) -> tuple[Path, Path]:
    if not TOKEN.match(token or ""):
        raise KeyError(token)
    folder = _folder()
    return folder / f"{token}.bin", folder / f"{token}.json"


def purge_expired() -> None:
    limit = time.time() - MAX_AGE_SECONDS
    for path in _folder().iterdir():
        if path.stat().st_mtime < limit:
            path.unlink(missing_ok=True)


def save(filename: str, raw: bytes, **meta) -> str:
    purge_expired()
    token = secrets.token_urlsafe(24)
    data_path, meta_path = _paths(token)
    data_path.write_bytes(raw)
    meta_path.write_text(json.dumps({"filename": filename, **meta}))
    return token


def load(token: str) -> tuple[bytes, dict]:
    """Return (raw bytes, metadata); KeyError when the token is unknown or expired."""
    data_path, meta_path = _paths(token)
    if not data_path.exists() or time.time() - data_path.stat().st_mtime > MAX_AGE_SECONDS:
        raise KeyError(token)
    return data_path.read_bytes(), json.loads(meta_path.read_text())


def delete(token: str) -> None:
    try:
        for path in _paths(token):
            path.unlink(missing_ok=True)
    except KeyError:
        pass
