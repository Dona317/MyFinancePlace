"""
What Windows needs to know about the app (F14), written for this user only (HKCU, no administrator rights) at every
start of the installed program, so a copy moved elsewhere fixes itself; the installer writes the same and removes it:

- AppUserModelId\\MyFinancePlace.App: the name and icon shown on the app's notifications;
- myfinanceplace://: a click on a notification starts the program with the link (the open one comes up).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger("desktop.windows")

APP_ID = "MyFinancePlace.App"
CLASSES = r"Software\Classes"


def _set(winreg, path: str, values: dict) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def register(executable: Path, icon: Path | None) -> None:
    """Notifications' name and icon, the myfinanceplace:// links, this process's identity (its taskbar button and
    notifications go together). Nothing outside Windows; failures are logged, never fatal."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        import winreg

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        _set(winreg, rf"{CLASSES}\AppUserModelId\{APP_ID}",
             {"DisplayName": "MyFinancePlace"} | ({"IconUri": str(icon)} if icon and icon.is_file() else {}))
        _set(winreg, rf"{CLASSES}\myfinanceplace", {"": "URL:MyFinancePlace", "URL Protocol": ""})
        _set(winreg, rf"{CLASSES}\myfinanceplace\shell\open\command",
             {"": f'"{executable}" "%1"'})
    except OSError:
        log.exception("Windows registration failed")
