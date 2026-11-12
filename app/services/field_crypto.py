"""
Sensitive fields stored encrypted (the first piece of F84): AES-256-GCM with a random nonce for each value, so the
database (and its backups) hold only ciphertext.

The key: the environment variable MFP_DATA_KEY (32 bytes, base64) when set — a server keeps it out of the data
folder — otherwise a key file made the first time in the app's instance folder (`data.key`, readable only by its
owner). Whoever has the database without the key reads nothing; whoever restores a backup on another computer needs
the same key, or the encrypted fields stay unreadable (the app says so and keeps working). The key can be read,
copied and downloaded from Esporta (to keep it with the backups) and typed in on another computer: the values
still readable with the old key are encrypted again with the new one. Where the key will live for good (system
keychain, a password at start) is decision D15.

Stored form: "v1:" + base64(nonce ‖ ciphertext+tag).
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import current_app

PREFIX = "v1:"
KEY_FILE = "data.key"
ENV = "MFP_DATA_KEY"


class Unreadable(ValueError):
    """The value was encrypted with another key (a backup from another computer) or is damaged."""


def _key() -> bytes:
    configured = os.environ.get(ENV)
    if configured:
        key = base64.b64decode(configured)
        if len(key) != 32:
            raise RuntimeError(f"{ENV} must be 32 bytes in base64")
        return key
    path = Path(current_app.instance_path) / KEY_FILE
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(base64.b64encode(AESGCM.generate_key(bit_length=256)))
    return base64.b64decode(path.read_bytes().strip())


def encrypt(text: str | None) -> str | None:
    if not text:
        return None
    nonce = os.urandom(12)
    sealed = AESGCM(_key()).encrypt(nonce, text.encode("utf-8"), PREFIX.encode())
    return PREFIX + base64.b64encode(nonce + sealed).decode("ascii")


def decrypt(stored: str | None) -> str | None:
    if not stored:
        return None
    if not stored.startswith(PREFIX):
        raise Unreadable("not an encrypted value")
    try:
        raw = base64.b64decode(stored[len(PREFIX):])
        return AESGCM(_key()).decrypt(raw[:12], raw[12:], PREFIX.encode()).decode("utf-8")
    except Exception as exc:  # wrong key, damaged value
        raise Unreadable(str(exc) or "unreadable") from None


# ── The key itself: read it to keep it, put it on another computer ───────────────────────────────────────────

def from_environment() -> bool:
    """The key comes from MFP_DATA_KEY (a server): it is read and changed there, not from the app."""
    return bool(os.environ.get(ENV))


def key_text() -> str:
    """The key as text (base64), to write down or save with the backups; made now if there is none yet."""
    return base64.b64encode(_key()).decode("ascii")


def fingerprint() -> str:
    """A short code of the key, to tell two keys apart without showing them: «3F9A-01C2»."""
    digest = hashlib.sha256(_key()).hexdigest().upper()
    return f"{digest[:4]}-{digest[4:8]}"


def _parse(text: str) -> bytes:
    try:
        key = base64.b64decode("".join((text or "").split()), validate=True)
    except ValueError:
        key = b""
    if len(key) != 32:
        raise ValueError("not a key")
    return key


def replace_key(text: str, rows: list[tuple[object, str]]) -> tuple[int, int]:
    """Use the key typed in (the one of another computer, or a saved one). `rows` are (object, attribute) pairs
    holding encrypted values: the ones readable with the old key are encrypted again with the new one, so nothing
    is lost. Returns (encrypted again, now readable thanks to the new key)."""
    if from_environment():
        raise RuntimeError(f"the key comes from {ENV}")
    new = _parse(text)
    old_values = {}
    for obj, attr in rows:
        try:
            old_values[(id(obj), attr)] = decrypt(getattr(obj, attr))
        except Unreadable:
            old_values[(id(obj), attr)] = None
    path = Path(current_app.instance_path) / KEY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(base64.b64encode(new))
    os.replace(tmp, path)
    again = readable = 0
    for obj, attr in rows:
        plain = old_values[(id(obj), attr)]
        if plain is not None:
            setattr(obj, attr, encrypt(plain))
            again += 1
        else:
            try:
                decrypt(getattr(obj, attr))
                readable += 1
            except Unreadable:
                pass
    return again, readable


def unreadable(rows: list[tuple[object, str]]) -> int:
    """How many encrypted values this key cannot read (a backup from another computer)."""
    count = 0
    for obj, attr in rows:
        try:
            decrypt(getattr(obj, attr))
        except Unreadable:
            count += 1
    return count
