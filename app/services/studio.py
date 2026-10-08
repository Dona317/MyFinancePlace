"""
Studio (F11): one person keeps the finances of several clients, each in an archive of its own.

- The **studio database** is the one in DATABASE_URL: it holds the users and the list of clients, and it is also
  the archive of the *primary* client (the data that existed before clients did).
- Every other client has a **database of its own** on the same PostgreSQL server (created here, migrated with the
  app's migrations, deleted here after a backup), plus a folder `<instance>/clients/<slug>/` for its documents and
  backups. Handing a client their archive = a backup of that client.

The open client is kept in the session; `activate` points the database session at its database for the rest of
the request (extensions.ClientSession).
"""
from __future__ import annotations

import re
import shutil
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from flask import current_app, g, session
from flask_babel import gettext as _
from sqlalchemy import create_engine, text

from app.extensions import STUDIO_TABLES, db
from app.models.client import Client

SESSION_KEY = "client_id"
SLUG = re.compile(r"^[a-z0-9_]{1,40}$")
DATABASE = re.compile(r"^[a-z0-9_]{1,63}$")
COLORS = ("#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c", "#0891b2", "#ca8a04", "#db2777")
PRIMARY_SLUG = "principale"


class StudioError(Exception):
    """A client cannot be created or removed; the message is shown to the user."""


# ── Which client is open ──────────────────────────────────────────────────────

def primary() -> Client:
    """The client whose archive is the studio database itself (created the first time it is asked for)."""
    client = Client.query.filter(Client.database.is_(None)).order_by(Client.id).first()
    if client is None:
        client = Client(name=_("Archivio principale"), slug=PRIMARY_SLUG, database=None, color=COLORS[0])
        db.session.add(client)
        db.session.commit()
    return client


def clients(include_archived: bool = True) -> list[Client]:
    primary()
    query = Client.query.order_by(Client.database.isnot(None), Client.name)
    return query.all() if include_archived else query.filter_by(archived=False).all()


def current() -> Client | None:
    """The open client, None before any is chosen (then the studio database is used: the primary archive)."""
    return g.get("client")


def is_studio() -> bool:
    """More than one archive: the interface shows which client is open."""
    try:
        return Client.query.filter(Client.database.isnot(None)).count() > 0
    except Exception:  # noqa: BLE001 - a database not yet migrated: no studio
        db.session.rollback()
        return False


def activate(client: Client | None) -> None:
    """Point this request's database session at `client`'s archive (None or the primary: the studio database)."""
    g.client = client
    g.client_engine = engine_for(client) if client is not None and not client.is_primary else None


def open_from_session() -> None:
    """Before each request: the client chosen earlier in this browser session, if it still exists."""
    client_id = session.get(SESSION_KEY)
    client = db.session.get(Client, client_id) if isinstance(client_id, int) else None
    if client_id is not None and client is None:
        session.pop(SESSION_KEY, None)
    activate(client)


def choose(client: Client) -> None:
    session[SESSION_KEY] = client.id
    activate(client)


@contextmanager
def using(client: Client):
    """Work on another client's archive for a moment (backups, migrations), then come back."""
    before = (g.get("client"), g.get("client_engine"))
    db.session.commit()
    _forget_archive_rows()
    activate(client)
    try:
        yield
        db.session.commit()
    finally:
        db.session.rollback()
        _forget_archive_rows()
        g.client, g.client_engine = before


def _forget_archive_rows() -> None:
    """The same id in two archives is two different rows: drop the loaded ones (users and clients stay)."""
    for obj in list(db.session.identity_map.values()):
        if obj.__table__.name not in STUDIO_TABLES:
            db.session.expunge(obj)


# ── Databases and folders ─────────────────────────────────────────────────────

def _url(database: str):
    return db.engine.url.set(database=database)


def engine_for(client: Client):
    engines = current_app.extensions.setdefault("studio_engines", {})
    if client.database not in engines:
        engines[client.database] = create_engine(_url(client.database), pool_pre_ping=True)
    return engines[client.database]


def folder(name: str) -> Path:
    """`<instance>/<name>` for the primary archive, `<instance>/clients/<slug>/<name>` for the others."""
    client = current()
    base = Path(current_app.instance_path)
    if client is not None and not client.is_primary:
        base = base / "clients" / client.slug
    path = base / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_")[:30] or "cliente"
    candidate, number = slug, 2
    while Client.query.filter_by(slug=candidate).first() is not None:
        candidate, number = f"{slug}_{number}", number + 1
    return candidate


def _database_name(slug: str) -> str:
    base = re.sub(r"[^a-z0-9_]", "_", (db.engine.url.database or "mfp").lower())[:20]
    name = f"{base}_c_{slug}"[:63]
    if not DATABASE.match(name):  # built here from checked parts: never from what the user typed
        raise StudioError("nome del database non valido")
    return name


def _admin(statement: str) -> None:
    """CREATE/DROP DATABASE: outside a transaction, on the studio server."""
    with db.engine.execution_options(isolation_level="AUTOCOMMIT").connect() as connection:
        connection.execute(text(statement))


def migrate(client: Client) -> None:
    """Bring a client's database to the app's current schema (the same migrations as the studio)."""
    directory = current_app.extensions["migrate"].directory
    config = Config(str(Path(directory) / "alembic.ini"))
    config.set_main_option("script_location", directory)
    with engine_for(client).begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def migrate_all() -> list[str]:
    done = []
    for client in Client.query.filter(Client.database.isnot(None)).all():
        migrate(client)
        done.append(client.slug)
    return done


# ── Creating, changing, removing ──────────────────────────────────────────────

def create(name: str, color: str | None = None, notes: str | None = None) -> Client:
    from app.services import categories  # here: categories imports settings, which imports this module's users

    name = " ".join((name or "").split())[:120]
    if not name:
        raise StudioError(_("Scrivi il nome del cliente."))
    primary()
    slug = slugify(name)
    client = Client(name=name, slug=slug, database=_database_name(slug), notes=(notes or "").strip() or None,
                    color=color if color in COLORS else COLORS[Client.query.count() % len(COLORS)])
    try:
        _admin(f'CREATE DATABASE "{client.database}"')
    except Exception as exc:
        raise StudioError(_("Impossibile creare l'archivio del cliente (%(exc)s).", exc=exc.__class__.__name__)) from exc
    try:
        migrate(client)
        db.session.add(client)
        db.session.commit()
        with using(client):
            categories.ensure_defaults()
    except Exception:
        db.session.rollback()
        _drop(client)
        raise
    return client


def update(client: Client, name: str, color: str | None, notes: str | None, archived: bool) -> None:
    name = " ".join((name or "").split())[:120]
    if not name:
        raise StudioError(_("Scrivi il nome del cliente."))
    client.name, client.notes, client.archived = name, (notes or "").strip() or None, archived and not client.is_primary
    if color in COLORS:
        client.color = color
    db.session.commit()


def backup(client: Client) -> bytes:
    from app.services import backup as backups

    with using(client):
        return backups.create_archive()


def delete(client: Client) -> Path:
    """Remove a client: a last backup goes to <instance>/clients_deleted/ first, then the database and the folder."""
    if client.is_primary:
        raise StudioError(_("L'archivio principale non si può eliminare."))
    archive = backup(client)
    kept = Path(current_app.instance_path) / "clients_deleted"
    kept.mkdir(parents=True, exist_ok=True)
    path = kept / f"{client.slug}_{datetime.now():%Y%m%d-%H%M%S}.zip"
    path.write_bytes(archive)
    if session.get(SESSION_KEY) == client.id:
        session.pop(SESSION_KEY, None)
        activate(None)
    _drop(client)
    shutil.rmtree(Path(current_app.instance_path) / "clients" / client.slug, ignore_errors=True)
    db.session.delete(client)
    db.session.commit()
    return path


def _drop(client: Client) -> None:
    engine = current_app.extensions.get("studio_engines", {}).pop(client.database, None)
    if engine is not None:
        engine.dispose()
    _admin(f'DROP DATABASE IF EXISTS "{client.database}" WITH (FORCE)')
