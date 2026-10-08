"""
A PostgreSQL that belongs to the desktop app (D7): the portable binaries shipped with the program, a data folder
in the user's data directory, listening only on 127.0.0.1 on a free port, with a random password kept next to the
data. Started when the app opens and stopped when it closes.
"""
from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import psycopg2
from psycopg2 import sql

SUPERUSER = "mfp"
DATABASE = "myfinanceplace"
WINDOWS = sys.platform.startswith("win")


class DatabaseError(RuntimeError):
    """The local database could not be prepared or started; the message is shown to the user."""


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class EmbeddedPostgres:
    def __init__(self, bin_dir: Path, root: Path):
        self.bin_dir = Path(bin_dir)
        self.data = root / "pgdata"
        self.log = root / "logs" / "postgres.log"
        self.password_file = root / "pg_password"
        self.port: int | None = None

    # ── Commands ──────────────────────────────────────────────────────────────
    def _exe(self, name: str) -> str:
        return str(self.bin_dir / (name + (".exe" if WINDOWS else "")))

    def _run(self, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
        flags = subprocess.CREATE_NO_WINDOW if WINDOWS else 0  # no console windows popping up
        env = {**os.environ, "LC_ALL": "C", "LANG": "C"}
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=flags, env=env)

    @property
    def password(self) -> str:
        if not self.password_file.exists():
            self.password_file.write_text(secrets.token_urlsafe(24), encoding="utf-8")
            if not WINDOWS:
                os.chmod(self.password_file, 0o600)
        return self.password_file.read_text(encoding="utf-8").strip()

    # ── Life cycle ────────────────────────────────────────────────────────────
    def initialised(self) -> bool:
        return (self.data / "PG_VERSION").is_file()

    def init(self) -> None:
        """First start: create the data folder (UTF-8, password login only)."""
        if not WINDOWS and hasattr(os, "geteuid") and os.geteuid() == 0:
            raise DatabaseError("Il database non può essere avviato dall'utente root: apri l'app con il tuo utente.")
        self.log.parent.mkdir(parents=True, exist_ok=True)
        pwfile = self.data.parent / "pg_pwfile.tmp"
        pwfile.write_text(self.password + "\n", encoding="utf-8")
        try:
            done = self._run(self._exe("initdb"), "-D", str(self.data), "-U", SUPERUSER, "--pwfile", str(pwfile),
                             "--auth=scram-sha-256", "-E", "UTF8", "--no-locale", timeout=300)
        finally:
            pwfile.unlink(missing_ok=True)
        if done.returncode != 0:
            raise DatabaseError("Preparazione del database non riuscita:\n" + (done.stderr or done.stdout)[-2000:])

    def running(self) -> bool:
        return self._run(self._exe("pg_ctl"), "-D", str(self.data), "status").returncode == 0

    def start(self) -> None:
        if not self.initialised():
            self.init()
        if self.running():  # left running by an app that did not close properly
            self.stop()
        self.port = free_port()
        options = f"-p {self.port} -c listen_addresses=127.0.0.1"
        if not WINDOWS:
            options += " -c unix_socket_directories=''"  # TCP on localhost only; no socket file to clash with
        self.log.parent.mkdir(parents=True, exist_ok=True)
        done = self._run(self._exe("pg_ctl"), "-D", str(self.data), "-l", str(self.log), "-o", options,
                         "-w", "-t", "90", "start", timeout=120)
        if done.returncode != 0:
            tail = self.log.read_text(encoding="utf-8", errors="replace")[-2000:] if self.log.exists() else ""
            raise DatabaseError("Avvio del database non riuscito:\n" + (done.stderr or done.stdout or tail)[-2000:])
        self._wait()

    def _wait(self, seconds: float = 30) -> None:
        deadline = time.time() + seconds
        while True:
            try:
                psycopg2.connect(self.url("postgres")).close()
                return
            except psycopg2.OperationalError:
                if time.time() > deadline:
                    raise
                time.sleep(0.3)

    def stop(self) -> None:
        self._run(self._exe("pg_ctl"), "-D", str(self.data), "-m", "fast", "-w", "-t", "60", "stop", timeout=90)

    # ── Databases ─────────────────────────────────────────────────────────────
    def url(self, database: str = DATABASE) -> str:
        return f"postgresql://{SUPERUSER}:{self.password}@127.0.0.1:{self.port}/{database}"

    def ensure_database(self, name: str = DATABASE) -> None:
        connection = psycopg2.connect(self.url("postgres"))
        connection.autocommit = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
                if cursor.fetchone() is None:
                    cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        finally:
            connection.close()
