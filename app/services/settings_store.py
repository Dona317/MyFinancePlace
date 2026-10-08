"""Persistent application settings (table app_settings), with fallbacks to the app config."""
import json

from app.extensions import db
from app.models.setting import AppSetting


def get(key: str, default: str | None = None) -> str | None:
    row = db.session.get(AppSetting, key)
    return row.value if row is not None and row.value not in (None, "") else default


def set(key: str, value: str | None) -> None:  # noqa: A001 - mirrors get()
    row = db.session.get(AppSetting, key)
    if row is None:
        db.session.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


def get_json(key: str, default=None, expect: type | tuple[type, ...] | None = None):
    """A setting stored as JSON; `default` when it is missing, unreadable or (with `expect`) of another type."""
    raw = get(key)
    if raw is None:
        return default
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return default
    return value if expect is None or isinstance(value, expect) else default


def set_json(key: str, value) -> None:
    """Store `value` as JSON (None removes the setting's value)."""
    set(key, json.dumps(value) if value is not None else None)
