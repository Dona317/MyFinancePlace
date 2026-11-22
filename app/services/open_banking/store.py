"""Values of the bank connections kept in the studio database (app_settings of the primary archive), read and written
straight on it whichever archive is open: the application's credentials, the consents waiting for the bank's answer."""
from __future__ import annotations

import json

from sqlalchemy import delete, insert, select, update

from app.extensions import db
from app.models.setting import AppSetting

TABLE = AppSetting.__table__


def get(key: str) -> str | None:
    """The stored value (db.engine is always the studio's, not the open archive's)."""
    with db.engine.connect() as connection:
        return connection.execute(select(TABLE.c.value).where(TABLE.c.key == key)).scalar()


def put(key: str, value: str | None) -> None:
    with db.engine.begin() as connection:
        if value is None:
            connection.execute(delete(TABLE).where(TABLE.c.key == key))
        elif connection.execute(select(TABLE.c.key).where(TABLE.c.key == key)).first():
            connection.execute(update(TABLE).where(TABLE.c.key == key).values(value=value))
        else:
            connection.execute(insert(TABLE).values(key=key, value=value))


def get_json(key: str, default=None):
    try:
        value = json.loads(get(key) or "null")
    except ValueError:
        return default
    return default if value is None else value


def put_json(key: str, value) -> None:
    put(key, json.dumps(value) if value is not None else None)
