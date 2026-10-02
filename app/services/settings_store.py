"""Persistent application settings (table app_settings), with fallbacks to the app config."""
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
