"""What every template can use (settings, display preferences, the bell, the open client) and versioned static
URLs."""
import os

from flask import Flask

from app.extensions import db
from app.services import display, notifications, sections, studio
from app.services.ui_settings import current_font, current_language, current_settings


def register_context(app: Flask) -> None:
    @app.url_defaults
    def static_version(endpoint, values):
        """A version in the URL of static files (their modification time): after an update the browser fetches the
        new CSS/JS instead of showing the old look from its cache."""
        if endpoint == "static" and "filename" in values and "v" not in values:
            try:
                values["v"] = int(os.path.getmtime(os.path.join(app.static_folder, values["filename"])))
            except OSError:
                pass

    def working_client():
        """The client being worked on, for the badge in the top bar (F11); None for a single archive."""
        try:
            return (studio.current() or studio.primary()) if studio.is_studio() else None
        except Exception:  # noqa: BLE001 - never breaks a page
            app.logger.exception("clients unavailable")
            db.session.rollback()
            return None

    def notification_count() -> int:
        """Reminders not yet seen, for the bell (never breaks a page)."""
        try:
            return len(notifications.collect())
        except Exception:  # noqa: BLE001 - a broken reminder source must not take the page down
            app.logger.exception("reminders unavailable")
            db.session.rollback()
            return 0

    @app.context_processor
    def inject_settings():
        return {"settings": current_settings(), "notification_count": notification_count, "display": display.prefs(),
                "current_language": current_language, "working_client": working_client, "ui_font": current_font,
                "shown": sections.in_menu, "allowed": sections.allowed, "shown_any": lambda *keys: any(sections.in_menu(k) for k in keys)}
