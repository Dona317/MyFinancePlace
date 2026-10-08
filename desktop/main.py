"""
MyFinancePlace as a desktop app (F16).

    python -m desktop.main              # window (pywebview); the data in the user's data folder
    python -m desktop.main --headless   # no window: prints the address, stops on Ctrl+C
    python -m desktop.main --smoke      # start everything, check /health, stop (used by the build)

Steps: user data folder → local PostgreSQL (desktop/database.py) → migrations of the studio and of every client
→ the app on 127.0.0.1 (waitress) → a native window. Closing the window stops the server and the database.
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
import urllib.request
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

from desktop import paths
from desktop.database import DatabaseError, EmbeddedPostgres

log = logging.getLogger("desktop")


def _arguments(argv):
    parser = argparse.ArgumentParser(prog="MyFinancePlace")
    parser.add_argument("--data-dir", help="cartella dei dati (predefinita: quella dell'utente)")
    parser.add_argument("--port", type=int, default=0, help="porta del server locale (predefinita: una libera)")
    parser.add_argument("--headless", action="store_true", help="nessuna finestra: stampa l'indirizzo")
    parser.add_argument("--browser", action="store_true", help="apre il browser invece della finestra")
    parser.add_argument("--smoke", action="store_true", help="avvia, controlla /health e chiude")
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


def _already_open(root: Path) -> str | None:
    """The address of an app already running on this data folder, if any."""
    try:
        url = json.loads((root / "running.json").read_text(encoding="utf-8"))["url"]
        return url if _health(url, 2).get("ok") else None
    except (OSError, ValueError, KeyError):
        return None


def build_app(database_url: str, secret: str, instance: Path):
    """The Flask app on the local database, migrated (studio and clients)."""
    os.environ.update(DATABASE_URL=database_url, SECRET_KEY=secret, MFP_INSTANCE_PATH=str(instance))
    from flask_migrate import upgrade

    from app import create_app
    from app.services import studio

    app = create_app("desktop")
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


def _window(url: str) -> bool:
    """A native window on the app; False when pywebview cannot open one here."""
    try:
        import webview
    except ImportError:
        return False
    try:
        webview.create_window("MyFinancePlace", url, width=1366, height=880, min_size=(380, 600))
        webview.start(private_mode=False)  # keeps the session cookie between launches
    except Exception:  # noqa: BLE001 - no GUI toolkit available: fall back to the browser
        log.exception("native window unavailable")
        return False
    return True


def _wait_for_signal() -> None:
    stop = threading.Event()
    for name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: stop.set())
    while not stop.wait(0.5):
        pass


def main(argv=None) -> int:
    args = _arguments(argv)
    root = paths.data_dir(args.data_dir)
    _logging(root)

    url = _already_open(root)
    if url and not args.smoke:
        log.info("already open at %s", url)
        if args.headless or not _window(url):
            webbrowser.open(url)
        return 0

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
    server = None
    try:
        database.ensure_database()
        app = build_app(database.url(), _secret_key(root), root / "instance")
        server, url = serve(app, args.port)
        (root / "running.json").write_text(json.dumps({"url": url, "pid": os.getpid()}), encoding="utf-8")
        log.info("MyFinancePlace on %s (data in %s)", url, root)
        print(url, flush=True)

        if args.smoke:
            body = _health(url, 10)
            print(json.dumps(body), flush=True)
            return 0 if body.get("ok") else 4
        if args.headless:
            _wait_for_signal()
        elif args.browser or not _window(url):
            webbrowser.open(url)
            _wait_for_signal()
        return 0
    finally:
        if server is not None:
            server.close()
        (root / "running.json").unlink(missing_ok=True)
        database.stop()
        log.info("closed")


if __name__ == "__main__":
    sys.exit(main())
