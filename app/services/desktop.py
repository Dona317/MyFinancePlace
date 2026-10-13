"""
The desktop app's own choices (F14): start with the computer, reminders as system notifications. They belong to the
installation, not to a client archive, so they live in a file of the data folder (desktop.json) that the launcher
reads too. The launcher sets DESKTOP_DIR, DESKTOP_COMMAND (how to start the app) and DESKTOP_SHOW (bring the window
up on a page) in the app's config; without them (server, tests) none of this applies.
"""
from __future__ import annotations

import json
from pathlib import Path

from flask import current_app
from itsdangerous import BadSignature, URLSafeSerializer

from app.services import autostart

FILE = "desktop.json"
DEFAULTS = {"notify": True}
BACKGROUND = "--background"


def available() -> bool:
    return bool(current_app.config.get("DESKTOP_DIR"))


def read_prefs(folder: Path) -> dict:
    """The saved choices (also for the launcher, outside a request); defaults for anything missing or unreadable."""
    try:
        saved = json.loads((Path(folder) / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    return DEFAULTS | {key: value for key, value in saved.items() if key in DEFAULTS and isinstance(value, bool)}


def prefs() -> dict:
    return read_prefs(current_app.config["DESKTOP_DIR"]) | {"autostart": autostart.is_enabled()}


def save(notify: bool, start_with_computer: bool) -> None:
    folder = Path(current_app.config["DESKTOP_DIR"])
    (folder / FILE).write_text(json.dumps({"notify": notify}), encoding="utf-8")
    if start_with_computer:
        autostart.enable([*current_app.config["DESKTOP_COMMAND"], BACKGROUND])
    else:
        autostart.disable()


# ── Links in the notifications: open a client's archive on a page ─────────────

def _signer() -> URLSafeSerializer:
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="desktop-open")


def open_link(client_id: int, path: str) -> str:
    """A link that opens `client_id`'s archive on `path`; signed, so only the app makes one."""
    return _signer().dumps({"c": client_id, "p": path})


def read_link(token: str) -> tuple[int, str] | None:
    try:
        data = _signer().loads(token)
        client_id, path = int(data["c"]), str(data["p"])
    except (BadSignature, KeyError, TypeError, ValueError):
        return None
    return (client_id, path) if path.startswith("/") and not path.startswith("//") and "\\" not in path else None
