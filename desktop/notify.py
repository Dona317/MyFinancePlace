"""
System notifications for the desktop app (F14), with what each system already has (nothing to install):

- Windows 10/11: a toast through PowerShell and the WinRT notification API, under the app's own name and icon
  (AppUserModelID registered by windows.register); a click opens myfinanceplace://…, which brings the app up;
- macOS: osascript «display notification»;
- Linux: notify-send.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr

from desktop import windows

log = logging.getLogger("desktop.notify")

PROTOCOL = "myfinanceplace"
TIMEOUT = 20
# Windows PowerShell 5.1 (always there on Windows 10/11) can load the WinRT types; the XML comes in an environment
# variable, so nothing in a reminder's text is ever parsed as a command
TOAST_SCRIPT = (
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
    "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null;"
    "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument; $xml.LoadXml($env:MFP_TOAST_XML);"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:MFP_TOAST_APP)"
    ".Show([Windows.UI.Notifications.ToastNotification]::new($xml))"
)


def click_url(link: str) -> str:
    """What a click on the notification opens: the app, on the reminder's archive and page."""
    return f"{PROTOCOL}://open/?to={quote(link)}"


def toast_xml(title: str, body: str, link: str) -> str:
    return (f"<toast activationType=\"protocol\" launch={quoteattr(click_url(link))}>"
            "<visual><binding template=\"ToastGeneric\">"
            f"<text>{escape(title)}</text><text>{escape(body)}</text>"
            "</binding></visual></toast>")


def _run(command: list[str], env: dict | None = None) -> bool:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
    try:
        result = subprocess.run(command, env=env, capture_output=True, timeout=TIMEOUT, creationflags=flags, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("notification not shown: %s", exc)
        return False
    if result.returncode:
        log.warning("notification not shown: %s", result.stderr.decode(errors="replace").strip()[:300])
    return result.returncode == 0


def show(title: str, body: str, link: str) -> bool:
    """Show one notification; False when the system refused it (logged)."""
    if sys.platform.startswith("win"):
        env = os.environ | {"MFP_TOAST_XML": toast_xml(title, body, link), "MFP_TOAST_APP": windows.APP_ID}
        return _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                     "-Command", TOAST_SCRIPT], env)
    if sys.platform == "darwin":
        script = "on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv)\nend run"
        return _run(["osascript", "-e", script, title, body])
    if shutil.which("notify-send"):
        return _run(["notify-send", "--app-name=MyFinancePlace", title, body])
    log.info("no notification service on this system: %s", title)
    return False
