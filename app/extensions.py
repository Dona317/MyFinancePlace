from flask import g, has_app_context
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.session import Session as FlaskSession
from flask_migrate import Migrate
from flask_babel import Babel
from flask_login import LoginManager
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.sql.util import find_tables

STUDIO_TABLES = {"users", "clients"}  # always in the studio database, whichever client is open


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


@event.listens_for(Session, "before_flush")
def _drop_nul_characters(session, flush_context, instances):  # noqa: ARG001
    """PostgreSQL refuses text with NUL characters: a pasted or uploaded \\x00 would turn a save into an error 500.
    They carry no meaning in a name or a description, so they are dropped from every text field before saving."""
    for obj in list(session.new) + list(session.dirty):
        for attr in inspect(obj).mapper.column_attrs:
            value = getattr(obj, attr.key, None)
            if isinstance(value, str) and "\x00" in value:
                setattr(obj, attr.key, value.replace("\x00", ""))
