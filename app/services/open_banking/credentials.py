"""
The Enable Banking application the app signs its calls with: its id and its RSA private key (made in the Enable Banking
control panel, https://enablebanking.com/cp/applications).

Where they are, in this order:
  • ENABLE_BANKING_APP_ID + ENABLE_BANKING_KEY_FILE (the path of the .pem): a server keeps them out of the data;
  • the studio database (the primary archive), table app_settings, key `open_banking.credentials`: one for the whole
    app — every client archive uses the same application — the whole value (id and key) encrypted with the data key
    (AES-256-GCM, services.field_crypto: "v1:…"), so it follows a change of key like the card numbers. It is read
    and written straight on the studio database, whichever archive is open.

The key never goes to the browser: the pages show only whether it is set and the application id; the JWT is signed
here, on the server, for each call.
An older version kept them in `enable_banking.json` in the instance folder: read once, moved into the database, deleted.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from flask import current_app

from app.extensions import db
from app.models.setting import AppSetting
from app.services import field_crypto

from . import store
from .client import Credentials, load_private_key

SETTING = "open_banking.credentials"
LEGACY_FILE = "enable_banking.json"
ENV_ID, ENV_KEY = "ENABLE_BANKING_APP_ID", "ENABLE_BANKING_KEY_FILE"


def from_environment() -> bool:
    return bool(os.environ.get(ENV_ID) and os.environ.get(ENV_KEY))


def _stored() -> str | None:
    return store.get(SETTING)


def _write(value: str | None) -> None:
    store.put(SETTING, value)


def _legacy_path() -> Path:
    return Path(current_app.instance_path) / LEGACY_FILE


def _move_legacy_file() -> str | None:
    """The file of the older version, moved into the database (then deleted)."""
    path = _legacy_path()
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    _write(field_crypto.encrypt(text))
    path.unlink()
    return text


def current() -> Credentials | None:
    """The application's credentials, or None when none are set (or the stored key cannot be read)."""
    if from_environment():
        try:
            pem = Path(os.environ[ENV_KEY]).read_text(encoding="utf-8")
        except OSError:
            return None
        return Credentials(os.environ[ENV_ID].strip(), pem)
    try:
        raw = _stored() or _move_legacy_file()
        if raw and raw.startswith(field_crypto.PREFIX):
            raw = field_crypto.decrypt(raw)
        data = json.loads(raw or "")
        pem = field_crypto.decrypt(data.get("key")) if str(data.get("key", "")).startswith(field_crypto.PREFIX) \
            else data.get("key")
    except (OSError, ValueError, AttributeError):
        return None
    if not data.get("app_id") or not pem:
        return None
    return Credentials(str(data["app_id"]), pem, data.get("redirect_url") or None)


def clean_redirect(url: str | None) -> str | None:
    """An https address for the way back from the bank (Enable Banking's Production accepts only https); None when
    empty. ValueError for anything else."""
    url = (url or "").strip()
    if not url:
        return None
    if not url.startswith("https://") or " " in url or len(url) > 300:
        raise ValueError("redirect URL must be https")
    return url


def save(app_id: str, pem: str | None, redirect_url: str | None = None) -> Credentials:
    """Keep the application's id, key and way back (encrypted). An empty key keeps the one saved for the same
    application (to change only the way back). ValueError when the id is empty, the key is not an RSA private key or
    the way back is not https."""
    app_id = (app_id or "").strip()
    if not app_id:
        raise ValueError("missing application id")
    redirect_url = clean_redirect(redirect_url)
    if not (pem or "").strip():
        kept = None if from_environment() else current()
        if kept is None or kept.app_id != app_id:
            raise ValueError("missing private key")
        pem = kept.private_key_pem
    load_private_key(pem)
    _write(field_crypto.encrypt(json.dumps({"app_id": app_id, "key": pem, "redirect_url": redirect_url})))
    _legacy_path().unlink(missing_ok=True)
    return Credentials(app_id, pem, redirect_url)


def remove() -> None:
    _write(None)
    _legacy_path().unlink(missing_ok=True)


def status() -> dict:
    """What the page shows: set or not, where from, the application id — never the key."""
    found = current()
    return {"configured": found is not None, "environment": from_environment(),
            "app_id": found.app_id if found else None, "redirect_url": found.redirect_url if found else None}


def encrypted_row() -> list[tuple[AppSetting, str]]:
    """The stored credentials as a row of the open archive, when that is the studio database (for a change of key)."""
    from app.services import studio

    current_archive = studio.current()
    if current_archive is not None and not current_archive.is_primary:
        return []
    row = db.session.get(AppSetting, SETTING)
    return [(row, "value")] if row is not None and (row.value or "").startswith(field_crypto.PREFIX) else []
