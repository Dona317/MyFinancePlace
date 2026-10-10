"""
MyFinancePlace as a desktop app (F16, F14).

    python -m desktop.main              # window (pywebview); the data in the user's data folder
    python -m desktop.main --background # no window at first: icon next to the clock (Windows), reminders as
                                        # notifications (how the app starts with the computer)
    python -m desktop.main --headless   # no window: prints the address, stops on Ctrl+C
    python -m desktop.main --smoke      # start everything, check /health, stop (used by the build)
    MyFinancePlace.exe myfinanceplace://open/?to=…   # a click on a notification: the app on that page

Steps: user data folder → local PostgreSQL (desktop/database.py) → migrations of the studio and of every client
→ the app on 127.0.0.1 (waitress) → a native window, the tray icon and the reminders. Closing the window stops the
server and the database, unless the tray icon keeps the app in the background (Windows; «Esci» stops it).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import signal
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

from desktop import notify, paths, tray, windows
from desktop.database import DatabaseError, EmbeddedPostgres

log = logging.getLogger("desktop")

REMINDERS_EVERY = 3600  # seconds between two looks at the reminders
FIRST_REMINDERS_AFTER = 20  # seconds after the start: the computer has just signed in


def _arguments(argv):
    parser = argparse.ArgumentParser(prog="MyFinancePlace")
    parser.add_argument("link", nargs="?", help="myfinanceplace://… (aperto da una notifica)")
    parser.add_argument("--data-dir", help="cartella dei dati (predefinita: quella dell'utente)")
    parser.add_argument("--port", type=int, default=0, help="porta del server locale (predefinita: una libera)")
    parser.add_argument("--background", action="store_true", help="senza finestra: icona e notifiche (avvio automatico)")
    parser.add_argument("--headless", action="store_true", help="nessuna finestra: stampa l'indirizzo")
    parser.add_argument("--browser", action="store_true", help="apre il browser invece della finestra")
    parser.add_argument("--smoke", action="store_true", help="avvia, controlla /health e chiude")
    parser.add_argument("--stop", action="store_true", help="chiude l'app aperta (installatore)")
    return parser.parse_args(argv)


def _logging(root: Path) -> None:
    folder = root / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / "myfinanceplace.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handlers = [handler] + ([logging.StreamHandler(sys.stderr)] if sys.stderr else [])  # no console in the window app
    logging.basicConfig(level=logging.INFO, handlers=handlers)


def _secret_key(root: Path) -> str:
    """Signs the session cookie: made once, kept in the data folder."""
    path = root / "secret_key"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        if os.name != "nt":
            os.chmod(path, 0o600)
    return path.read_text(encoding="utf-8").strip()


def _health(url: str, timeout: float) -> dict:
    """What the app at `url` says about itself (its database reachable or not)."""
    with urllib.request.urlopen(url + "health", timeout=timeout) as answer:  # noqa: S310 - our own localhost
        return json.loads(answer.read())


def _running(root: Path) -> dict | None:
    """The app already running on this data folder ({url, token}), if any."""
    try:
        running = json.loads((root / "running.json").read_text(encoding="utf-8"))
        return running if _health(running["url"], 2).get("ok") else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _stop(root: Path, running: dict, wait: float = 60) -> bool:
    """Close the running app and wait until it has stopped (server and database), for the installer."""
    if not _ask_running(running, "quit"):
        return False
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if not (root / "running.json").exists():
            return True
        time.sleep(0.5)
    return False


def link_target(link: str | None) -> str:
    """The signed page of a myfinanceplace://open/?to=… link ('' for none or anything else)."""
    if not link or not link.startswith(f"{notify.PROTOCOL}://"):
        return ""
    return urllib.parse.parse_qs(urllib.parse.urlsplit(link).query).get("to", [""])[0]


def _ask_running(running: dict, action: str, **values) -> bool:
    """Ask the running app to `action` (show: its window, on a notification's page; quit)."""
    data = urllib.parse.urlencode({"token": running.get("token", "")} | values).encode()
    try:
        with urllib.request.urlopen(running["url"] + f"desktop/{action}", data=data, timeout=10):  # noqa: S310
            return True
    except OSError:
        log.exception("the running app did not answer")
        return False


def launch_command(data_dir: str | None) -> list[str]:
    """How to start this app again (start with the computer)."""
    command = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "desktop.main"]
    return command + (["--data-dir", data_dir] if data_dir else [])


def build_app(database_url: str, secret: str, instance: Path, desktop: dict | None = None):
    """The Flask app on the local database, migrated (studio and clients). `desktop`: the DESKTOP_* settings."""
    os.environ.update(DATABASE_URL=database_url, SECRET_KEY=secret, MFP_INSTANCE_PATH=str(instance))
    from flask_migrate import upgrade

    from app import create_app
    from app.services import studio

    app = create_app("desktop")
    app.config.update(desktop or {})
    with app.app_context():
        upgrade(directory=app.extensions["migrate"].directory)
        done = studio.migrate_all()
        log.info("database ready; client archives migrated: %s", ", ".join(done) or "none")
    return app


def serve(app, port: int):
    from waitress.server import create_server

    server = create_server(app, host="127.0.0.1", port=port, threads=8, ident="MyFinancePlace")
    thread = threading.Thread(target=server.run, name="waitress", daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.effective_port}/"


def send_reminders(app, root: Path) -> int:
    """The reminders of every archive as system notifications (when switched on in Settings → App desktop)."""
    from app.services import desktop, system_notifications

    if not desktop.read_prefs(root)["notify"]:
        return 0
    with app.app_context(), app.test_request_context("/"):
        return system_notifications.run(lambda m: notify.show(m.title, m.body, m.link))


def _reminders_loop(app, root: Path, stop: threading.Event) -> None:
    wait = FIRST_REMINDERS_AFTER
    while not stop.wait(wait):
        try:
            sent = send_reminders(app, root)
            if sent:
                log.info("%s reminder notification(s) shown", sent)
        except Exception:  # noqa: BLE001 - a failed round must not stop the next ones
            log.exception("reminders not sent")
        wait = REMINDERS_EVERY


class Window:
    """The native window; with the tray icon, closing it only hides it."""

    def __init__(self, url: str, hidden: bool, keep_running: bool):
        import webview

        self.base, self.keep_running, self.quitting = url, keep_running, False
        self.webview = webview
        self.window = webview.create_window("MyFinancePlace", url, width=1366, height=880, min_size=(380, 600),
                                            hidden=hidden)
        self.window.events.closing += self._closing

    def _closing(self):
        if self.keep_running and not self.quitting:
            self.window.hide()
            return False  # cancels the close: the app stays in the background
        return True

    def show(self, page: str = "") -> None:
        if page:
            self.window.load_url(urllib.parse.urljoin(self.base, page))
        self.window.show()
        self.window.restore()

    def quit(self) -> None:
        self.quitting = True
        self.window.destroy()

    def run(self, on_started=None) -> None:
        self.webview.start(on_started, private_mode=False)  # keeps the session cookie between launches


def _open_window(app, url: str, root: Path, background: bool, page: str) -> bool:
    """Window (+ tray icon on Windows) until the user quits; False when no native window can be opened here."""
    try:
        import webview  # noqa: F401
    except ImportError:
        return False
    keep_running = tray.supported()
    try:
        window = Window(url, hidden=background and keep_running, keep_running=keep_running)
    except Exception:  # noqa: BLE001 - no GUI toolkit available: fall back to the browser
        log.exception("native window unavailable")
        return False
    app.config.update(DESKTOP_SHOW=window.show, DESKTOP_QUIT=window.quit)
    icon = tray.Tray(paths.icon_file("png"), on_open=window.show, on_quit=window.quit) if keep_running else None

    def started():
        if icon:
            icon.start()
        if page:
            window.show(page)

    try:
        window.run(started)
    except Exception:  # noqa: BLE001
        log.exception("native window unavailable")
        return False
    finally:
        if icon:
            icon.stop()
    return True


def _wait_for_signal(stop: threading.Event) -> None:
    """Until Ctrl+C, a stop signal or `stop` is set (--stop)."""
    for name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: stop.set())
    while not stop.wait(0.5):
        pass


def main(argv=None) -> int:
    args = _arguments(argv)
    root = paths.data_dir(args.data_dir)
    _logging(root)
    target = link_target(args.link)

    running = _running(root)
    if args.stop:
        return 0 if running is None or _stop(root, running) else 5
    if running and not args.smoke:
        log.info("already open at %s", running["url"])
        if not args.background and not _ask_running(running, "show", to=target):
            webbrowser.open(running["url"])
        return 0

    if getattr(sys, "frozen", False):
        windows.register(Path(sys.executable), paths.icon_file("ico"))
    bin_dir = paths.postgres_bin()
    if bin_dir is None:
        log.error("PostgreSQL binaries not found (pgsql/bin, or MFP_PG_BIN)")
        return 2
    database = EmbeddedPostgres(bin_dir, root)
    try:
        database.start()
    except (DatabaseError, OSError) as exc:
        log.error("%s", exc)
        return 3
    server, stop = None, threading.Event()
    try:
        database.ensure_database()
        token = secrets.token_urlsafe(32)
        app = build_app(database.url(), _secret_key(root), root / "instance",
                        {"DESKTOP_DIR": str(root), "DESKTOP_COMMAND": launch_command(args.data_dir),
                         "DESKTOP_TOKEN": token})
        server, url = serve(app, args.port)
        (root / "running.json").write_text(json.dumps({"url": url, "pid": os.getpid(), "token": token}),
                                           encoding="utf-8")
        log.info("MyFinancePlace on %s (data in %s)", url, root)
        print(url, flush=True)

        if args.smoke:
            body = _health(url, 10)
            print(json.dumps(body), flush=True)
            return 0 if body.get("ok") else 4
        threading.Thread(target=_reminders_loop, args=(app, root, stop), name="reminders", daemon=True).start()
        if args.headless:
            app.config["DESKTOP_QUIT"] = stop.set
            _wait_for_signal(stop)
        elif args.browser or not _open_window(app, url, root, args.background, _page(app, target)):
            webbrowser.open(url)
            app.config["DESKTOP_QUIT"] = stop.set
            _wait_for_signal(stop)
        return 0
    finally:
        stop.set()
        if server is not None:
            server.close()
        (root / "running.json").unlink(missing_ok=True)
        database.stop()
        log.info("closed")


def _page(app, target: str) -> str:
    """The page a notification's link opens ('' for none)."""
    if not target:
        return ""
    with app.test_request_context("/"):
        from flask import url_for

        return url_for("desktop.open_link", token=target)


if __name__ == "__main__":
    sys.exit(main())
