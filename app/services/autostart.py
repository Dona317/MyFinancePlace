"""
Start the desktop app when the user signs in to the computer (F14), each system its own way and only for this user
(no administrator rights):

- Windows: a value under HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run (the installer writes the same one);
- macOS: a launch agent in ~/Library/LaunchAgents;
- Linux: an entry in ~/.config/autostart (XDG).

`command` is the program and its arguments, e.g. ["C:\\…\\MyFinancePlace.exe", "--background"].
"""
from __future__ import annotations

import os
import plistlib
import shlex
import subprocess
import sys
from pathlib import Path

NAME = "MyFinancePlace"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AGENT_LABEL = "com.myfinanceplace.app"


def _windows() -> bool:
    return sys.platform.startswith("win")


def _agent_file() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{AGENT_LABEL}.plist"


def _desktop_entry() -> Path:
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return config / "autostart" / "myfinanceplace.desktop"


def is_enabled() -> bool:
    if _windows():
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, NAME)
            return True
        except OSError:
            return False
    return (_agent_file() if sys.platform == "darwin" else _desktop_entry()).is_file()


def enable(command: list[str]) -> None:
    if _windows():
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(command))
    elif sys.platform == "darwin":
        path = _agent_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(plistlib.dumps({"Label": AGENT_LABEL, "ProgramArguments": command, "RunAtLoad": True}))
    else:
        path = _desktop_entry()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[Desktop Entry]\nType=Application\nName=MyFinancePlace\n"
                        f"Exec={shlex.join(command)}\nX-GNOME-Autostart-enabled=true\n", encoding="utf-8")


def disable() -> None:
    if _windows():
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, NAME)
        except OSError:
            pass  # already off
    else:
        (_agent_file() if sys.platform == "darwin" else _desktop_entry()).unlink(missing_ok=True)
