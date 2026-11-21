"""
The Enable Banking application the app signs its calls with: its id and its RSA private key (made in the Enable Banking
control panel, https://enablebanking.com/cp/applications).

Where they are, in this order:
  • ENABLE_BANKING_APP_ID + ENABLE_BANKING_KEY_FILE (the path of the .pem): a server keeps them out of the data folder;
  • the file `enable_banking.json` of the instance folder, written from the page Collegamenti bancari: one for the whole
    app (every client archive uses the same application), readable only by its owner, the key encrypted with the
    data key (services.field_crypto).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from flask import current_app

from app.services import field_crypto

from .client import Credentials, load_private_key

FILE = "enable_banking.json"
ENV_ID, ENV_KEY = "ENABLE_BANKING_APP_ID", "ENABLE_BANKING_KEY_FILE"


def _path() -> Path:
    return Path(current_app.instance_path) / FILE


def from_environment() -> bool:
    return bool(os.environ.get(ENV_ID) and os.environ.get(ENV_KEY))


def current() -> Credentials | None:
    """The application's credentials, or None when none are set (or the stored key cannot be read)."""
    if from_environment():
        try:
            pem = Path(os.environ[ENV_KEY]).read_text(encoding="utf-8")
        except OSError:
            return None
        return Credentials(os.environ[ENV_ID].strip(), pem)
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        pem = field_crypto.decrypt(data.get("key"))
    except (OSError, ValueError, AttributeError):
        return None
    if not data.get("app_id") or not pem:
        return None
    return Credentials(str(data["app_id"]), pem)


def save(app_id: str, pem: str) -> Credentials:
    """Keep the application's id and key; ValueError when the id is empty or the key is not an RSA private key."""
    app_id = (app_id or "").strip()
    if not app_id:
        raise ValueError("missing application id")
    load_private_key(pem)
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"app_id": app_id, "key": field_crypto.encrypt(pem)})
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    return Credentials(app_id, pem)


def remove() -> None:
    _path().unlink(missing_ok=True)


def status() -> dict:
    """What the page shows: set or not, where from, the application id."""
    found = current()
    return {"configured": found is not None, "environment": from_environment(),
            "app_id": found.app_id if found else None}
