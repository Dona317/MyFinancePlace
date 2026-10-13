"""
The icon next to the clock (F14, Windows): the app keeps running in the background with it, so the reminders arrive
even with the window closed. Click or «Apri»: the window; «Esci»: the app stops (server and database).

Only on Windows: on macOS and Linux the menu-bar icon and the window would both need the main thread, so there the
app runs while its window is open, as before.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Callable

log = logging.getLogger("desktop.tray")


def supported() -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import pystray  # noqa: F401
    except ImportError:
        return False
    return True


class Tray:
    def __init__(self, icon_file: Path, on_open: Callable[[], None], on_quit: Callable[[], None]):
        import pystray
        from PIL import Image

        menu = pystray.Menu(
            pystray.MenuItem("Apri MyFinancePlace", lambda: on_open(), default=True),
            pystray.MenuItem("Esci", lambda: on_quit()),
        )
        self.icon = pystray.Icon("MyFinancePlace", Image.open(icon_file), "MyFinancePlace", menu)

    def start(self) -> None:
        self.icon.run_detached()  # its own message loop; the window keeps the main thread

    def stop(self) -> None:
        try:
            self.icon.stop()
        except Exception:  # noqa: BLE001 - already gone while the app quits
            log.debug("tray already stopped", exc_info=True)
