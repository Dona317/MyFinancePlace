"""Persistent application settings (table app_settings), with fallbacks to the app config.

The table is small and read many times by every page (most keys are never set): it is read once per request."""
import json

from app.extensions import db
from app.models.setting import AppSetting
from app.services import request_cache

CACHE_KEY = "app-settings"


def _all() -> dict[str, str | None]:
    store = request_cache.cache()
    if CACHE_KEY not in store:
        store[CACHE_KEY] = dict(db.session.execute(db.select(AppSetting.key, AppSetting.value)).all())
    return store[CACHE_KEY]


def forget() -> None:
    """Read the table again on the next get (after the rows were replaced, e.g. by a restore)."""
    request_cache.cache().pop(CACHE_KEY, None)


def get(key: str, default: str | None = None) -> str | None:
    value = _all().get(key)
    return value if value not in (None, "") else default


def set(key: str, value: str | None) -> None:  # noqa: A001 - mirrors get()
    row = db.session.get(AppSetting, key)
    if row is None:
        db.session.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    db.session.commit()
    _all()[key] = value


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
