"""Where the desktop app keeps its data, and where its bundled files are."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "MyFinancePlace"


def data_dir(override: str | None = None) -> Path:
    """The user's data folder: database, documents, backups, logs. Never inside the program folder, so an update
    replaces the program and keeps the data."""
    if override:
        path = Path(override).expanduser()
    elif sys.platform.startswith("win"):
        path = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        path = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_NAME
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def bundle_dir() -> Path:
    """The program's own files: next to the executable when frozen by PyInstaller, the repository otherwise."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def postgres_bin() -> Path | None:
    """The bundled PostgreSQL binaries (pgsql/bin), or the ones in MFP_PG_BIN; None when not found."""
    candidates = [os.environ.get("MFP_PG_BIN"), bundle_dir() / "pgsql" / "bin",
                  Path(__file__).resolve().parent / "vendor" / "pgsql" / "bin"]
    exe = "pg_ctl.exe" if sys.platform.startswith("win") else "pg_ctl"
    for candidate in candidates:
        if candidate and (Path(candidate) / exe).is_file():
            return Path(candidate)
    return None


def icon_file(kind: str) -> Path:
    """The app's icon (desktop/assets/icon.png or .ico, bundled as assets/)."""
    for folder in (bundle_dir() / "assets", Path(__file__).resolve().parent / "assets"):
        if (folder / f"icon.{kind}").is_file():
            return folder / f"icon.{kind}"
    return Path(__file__).resolve().parent / "assets" / f"icon.{kind}"
