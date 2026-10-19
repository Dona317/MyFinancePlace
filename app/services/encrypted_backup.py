"""
The automatic encrypted backup (F23): the full backup (backup.create_archive) written every day, week or month to a
folder chosen by the user — a synced OneDrive or Google Drive folder, a USB stick — keeping the last N copies.

The password is never stored, not even as a hash that would open the files. It is turned (scrypt) into an X25519 key
pair: only the public half is kept, so the app can encrypt on its own and only who knows the password can decrypt.
Each file gets a fresh key pair; the shared secret (X25519 + HKDF) is the AES-256-GCM key of that file.

File layout (.mfpbackup): MAGIC | salt (16) | scrypt log2 n (1) | ephemeral public key (32) | nonce (12) | ciphertext
with its tag. Everything before the ciphertext is authenticated too, so a changed byte anywhere is noticed.
"""
from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from flask import current_app
from flask_babel import gettext as _

from app.extensions import db
from app.services import backup, settings_store, studio
from app.services.i18n import N_

MAGIC = b"MFPBAK01"
EXTENSION = ".mfpbackup"
SCRYPT_LOG_N = 15            # 32 MB and a fraction of a second: slow enough against guessing
MIN_PASSWORD = 8
FREQUENCIES = {"daily": (N_("Ogni giorno"), timedelta(days=1)), "weekly": (N_("Ogni settimana"), timedelta(days=7)),
               "monthly": (N_("Ogni mese"), timedelta(days=30))}
SETTING = "backup.auto"      # {"folder", "frequency", "keep", "salt", "log_n", "public", "last_ok", "last_error", ...}
_HEADER = len(MAGIC) + 16 + 1 + 32 + 12
_lock = threading.Lock()
_running: set = set()


class EncryptedBackupError(backup.BackupError):
    pass


# ── Keys ───────────────────────────────────────────────────────────────────────

def _private_key(password: str, salt: bytes, log_n: int) -> X25519PrivateKey:
    seed = Scrypt(salt=salt, length=32, n=2 ** log_n, r=8, p=1).derive(password.encode())
    return X25519PrivateKey.from_private_bytes(seed)


def _raw_public(key) -> bytes:
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _file_key(shared: bytes, salt: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=b"myfinanceplace backup").derive(shared)


def make_key(password: str, log_n: int | None = None) -> dict:
    """What is kept of a new password: the salt and the public key (hex)."""
    log_n = log_n or SCRYPT_LOG_N
    if len(password or "") < MIN_PASSWORD:
        raise EncryptedBackupError(_("La password deve avere almeno %(n)s caratteri.", n=MIN_PASSWORD))
    salt = os.urandom(16)
    return {"salt": salt.hex(), "log_n": log_n, "public": _raw_public(_private_key(password, salt, log_n).public_key()).hex()}


def check_password(config: dict, password: str) -> bool:
    if not config.get("public") or not password:
        return False
    private = _private_key(password, bytes.fromhex(config["salt"]), config["log_n"])
    return _raw_public(private.public_key()).hex() == config["public"]


# ── Files ──────────────────────────────────────────────────────────────────────

def is_encrypted(raw: bytes) -> bool:
    return raw[:len(MAGIC)] == MAGIC


def encrypt(raw: bytes, config: dict) -> bytes:
    salt, log_n = bytes.fromhex(config["salt"]), int(config["log_n"])
    ephemeral = X25519PrivateKey.generate()
    key = _file_key(ephemeral.exchange(X25519PublicKey.from_public_bytes(bytes.fromhex(config["public"]))), salt)
    nonce = os.urandom(12)
    header = MAGIC + salt + bytes([log_n]) + _raw_public(ephemeral.public_key()) + nonce
    return header + AESGCM(key).encrypt(nonce, raw, header)


def decrypt(blob: bytes, password: str) -> bytes:
    if not is_encrypted(blob) or len(blob) < _HEADER + 16:
        raise EncryptedBackupError(_("Non è un backup cifrato di MyFinancePlace."))
    if not password:
        raise EncryptedBackupError(_("Il backup è cifrato: scrivi la password."))
    at = len(MAGIC)
    salt, log_n = blob[at:at + 16], blob[at + 16]
    ephemeral, nonce = blob[at + 17:at + 49], blob[at + 49:at + 61]
    if not 10 <= log_n <= 20:
        raise EncryptedBackupError(_("Il file di backup è danneggiato."))
    private = _private_key(password, salt, log_n)
    key = _file_key(private.exchange(X25519PublicKey.from_public_bytes(ephemeral)), salt)
    try:
        return AESGCM(key).decrypt(nonce, blob[_HEADER:], blob[:_HEADER])
    except InvalidTag:
        raise EncryptedBackupError(_("Password sbagliata, oppure il file è stato modificato o è danneggiato.")) from None


# ── Settings and status ────────────────────────────────────────────────────────

def config() -> dict:
    return settings_store.get_json(SETTING, {}, expect=dict)


def configure(folder: str, frequency: str, keep: int | None, password: str | None, current: str | None = None) -> dict:
    """Save the choices; a new password needs the current one when there is one (the old files keep the old one)."""
    found = config()
    folder = (folder or "").strip()
    if not folder:
        raise EncryptedBackupError(_("Scegli la cartella dove salvare i backup."))
    path = Path(folder).expanduser()
    if not path.is_absolute():
        raise EncryptedBackupError(_("Scrivi il percorso completo della cartella (per esempio D:\\Backup o /home/anna/OneDrive/Backup)."))
    if frequency not in FREQUENCIES:
        raise EncryptedBackupError(_("Scegli ogni quanto fare il backup."))
    if keep is None or not 1 <= keep <= 100:
        raise EncryptedBackupError(_("Le copie da tenere vanno da 1 a 100."))
    if password:
        if found.get("public") and not check_password(found, current or ""):
            raise EncryptedBackupError(_("Per cambiare la password scrivi anche quella attuale."))
        found.update(make_key(password))
    elif not found.get("public"):
        raise EncryptedBackupError(_("Scegli una password: senza, i backup non si potranno aprire."))
    found.update(folder=str(path), frequency=frequency, keep=keep, enabled=True)
    settings_store.set_json(SETTING, found)
    return found


def disable() -> None:
    found = config()
    found["enabled"] = False
    settings_store.set_json(SETTING, found)


@dataclass
class Status:
    enabled: bool
    folder: str | None
    frequency: str | None
    keep: int | None
    last_ok: datetime | None
    last_file: str | None
    last_error: str | None
    overdue: bool        # no success for more than two periods, or the last try failed


def status(now: datetime | None = None) -> Status:
    found, now = config(), now or datetime.now()
    last_ok = datetime.fromisoformat(found["last_ok"]) if found.get("last_ok") else None
    error = found.get("last_error")
    period = FREQUENCIES.get(found.get("frequency"), FREQUENCIES["daily"])[1]
    enabled = bool(found.get("enabled") and found.get("public"))
    overdue = enabled and (bool(error) or (last_ok is not None and now - last_ok > 2 * period))
    return Status(enabled, found.get("folder"), found.get("frequency"), found.get("keep"), last_ok,
                  found.get("last_file"), error, overdue)


def due(now: datetime | None = None) -> bool:
    found, now = config(), now or datetime.now()
    if not (found.get("enabled") and found.get("public")):
        return False
    last = found.get("last_try") or found.get("last_ok")
    period = FREQUENCIES.get(found.get("frequency"), FREQUENCIES["daily"])[1]
    # a failed try is repeated after an hour (the stick may be plugged in again), not after a whole period
    wait = timedelta(hours=1) if found.get("last_error") else period - timedelta(hours=1)
    return last is None or now - datetime.fromisoformat(last) >= wait


# ── Writing ────────────────────────────────────────────────────────────────────

def _prefix() -> str:
    client = studio.current()
    name = client.name if client is not None else "principale"
    return "myfinanceplace_" + (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "archivio") + "_"


def rotate(folder: Path, prefix: str, keep: int) -> list[Path]:
    """Remove the oldest copies of this archive beyond `keep` (only files this app wrote)."""
    pattern = re.compile(re.escape(prefix) + r"\d{4}-\d{2}-\d{2}_\d{6}" + re.escape(EXTENSION) + "$")
    copies = sorted(p for p in folder.iterdir() if p.is_file() and pattern.match(p.name))
    old = copies[:-keep] if keep else copies
    for path in old:
        path.unlink()
    return old


def run(now: datetime | None = None) -> Path:
    """Write one encrypted copy now; the result (or the error) is kept for the status and the reminders."""
    found, now = config(), now or datetime.now()
    if not found.get("public") or not found.get("folder"):
        raise EncryptedBackupError(_("Il backup automatico non è impostato."))
    found["last_try"] = now.isoformat(timespec="seconds")
    try:
        folder = Path(found["folder"])
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{_prefix()}{now:%Y-%m-%d_%H%M%S}{EXTENSION}"
        partial = target.with_suffix(".tmp")
        partial.write_bytes(encrypt(backup.create_archive(), found))
        partial.replace(target)  # never a half-written backup under the final name
        rotate(folder, _prefix(), int(found.get("keep") or 8))
    except OSError as exc:
        found["last_error"] = _("Cartella non scrivibile (%(error)s).", error=exc.strerror or str(exc))
        settings_store.set_json(SETTING, found)
        db.session.commit()
        raise EncryptedBackupError(found["last_error"]) from None
    found.update(last_ok=found["last_try"], last_file=target.name, last_error=None)
    settings_store.set_json(SETTING, found)
    db.session.commit()
    return target


def run_if_due(now: datetime | None = None) -> Path | None:
    if not due(now):
        return None
    try:
        return run(now)
    except EncryptedBackupError:
        return None  # kept in the status: the reminders say it


def run_all_archives(now: datetime | None = None) -> int:
    """The desktop app's round: every archive with a backup due; returns how many were written."""
    written = 0
    for client in [c for c in studio.clients() if not c.archived]:
        with studio.using(client):
            written += run_if_due(now) is not None
    return written


def run_in_background() -> None:
    """On the first visit of the day in the web app: the backup written in a thread, the page does not wait."""
    if not due():
        return
    client = studio.current()
    key = client.id if client is not None else None
    with _lock:
        if key in _running:
            return
        _running.add(key)
    app = current_app._get_current_object()
    threading.Thread(target=_thread, args=(app, client, key), daemon=True, name="backup-auto").start()


def _thread(app, client, key) -> None:
    try:
        with app.app_context(), app.test_request_context("/"):
            studio.activate(client)
            run_if_due()
    except Exception:  # noqa: BLE001 - a failed backup must not hurt the app; the status shows it
        app.logger.exception("automatic backup not written")
    finally:
        with _lock:
            _running.discard(key)
