from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_babel import Babel
from flask_login import LoginManager
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

db = SQLAlchemy()
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
