from flask import g, has_app_context
from flask_babel import Babel
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.session import Session as FlaskSession
from sqlalchemy import event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.sql.util import find_tables

STUDIO_TABLES = {"users", "clients", "client_groups", "client_group_members"}  # always in the studio database, whichever client is open


class ClientSession(FlaskSession):
    """Every query goes to the database of the client that is open (F11, `g.client_engine`, set by
    services/studio.activate); the users and the list of clients stay in the studio database. With no client
    open (or the primary one) everything is in the studio database, as before clients existed."""

    def get_bind(self, mapper=None, clause=None, bind=None, **kwargs):
        engine = g.get("client_engine") if bind is None and has_app_context() else None
        if engine is not None and not _studio_only(mapper, clause):
            return engine
        return super().get_bind(mapper=mapper, clause=clause, bind=bind, **kwargs)


def _studio_only(mapper, clause) -> bool:
    if mapper is not None:
        return inspect(mapper).local_table.name in STUDIO_TABLES
    if clause is not None:
        names = {getattr(table, "name", None) for table in find_tables(clause, include_crud=True)}
        return bool(names) and names <= STUDIO_TABLES
    return False


db = SQLAlchemy(session_options={"class_": ClientSession})
migrate = Migrate()
babel = Babel()
login_manager = LoginManager()


@event.listens_for(Engine, "before_cursor_execute")
def _forget_what_was_read(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
    """Whatever is not a SELECT may change the data: what the request read before is forgotten
    (services.request_cache.data) and the database's version moves (request_cache.version)."""
    if statement.lstrip()[:6].upper() != "SELECT":
        from app.services import request_cache

        conn.info["mfp_wrote"] = True
        request_cache.wrote(conn.engine.url.database)


@event.listens_for(Engine, "commit")
def _written_for_good(conn):
    conn.info.pop("mfp_wrote", None)


@event.listens_for(Engine, "rollback")
def _forget_after_rollback(conn):
    """What was written and then undone may have been read in between: forgotten again. A transaction that only
    read (every page ends with one) changes nothing."""
    if conn.info.pop("mfp_wrote", None):
        from app.services import request_cache

        request_cache.wrote(conn.engine.url.database)


@event.listens_for(Session, "before_flush")
def _drop_nul_characters(session, flush_context, instances):  # noqa: ARG001
    """PostgreSQL refuses text with NUL characters: a pasted or uploaded \\x00 would turn a save into an error 500.
    They carry no meaning in a name or a description, so they are dropped from every text field before saving."""
    for obj in list(session.new) + list(session.dirty):
        for attr in inspect(obj).mapper.column_attrs:
            value = getattr(obj, attr.key, None)
            if isinstance(value, str) and "\x00" in value:
                setattr(obj, attr.key, value.replace("\x00", ""))
