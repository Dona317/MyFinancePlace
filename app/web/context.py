"""What every template can use (settings, display preferences, the bell, the open client) and versioned static
URLs."""
import os

from flask import Flask

from app.extensions import db
from app.services import display, family, groups, notifications, palettes, sections, studio
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

    def client_groups(client):
        """The groups of the open archive, next to its badge (F21)."""
        try:
            return groups.of(client)
        except Exception:  # noqa: BLE001 - never breaks a page
            app.logger.exception("groups unavailable")
            db.session.rollback()
            return []

    def notification_count() -> int:
        """Reminders not yet seen, for the bell (never breaks a page)."""
        try:
            return len(notifications.collect())
        except Exception:  # noqa: BLE001 - a broken reminder source must not take the page down
            app.logger.exception("reminders unavailable")
            db.session.rollback()
            return 0

    def archive_choices():
        """F98: the archives the selector at the top of the menu can open (the archived ones aside)."""
        try:
            return [client for client in studio.clients() if not client.archived]
        except Exception:  # noqa: BLE001 - never breaks a page
            db.session.rollback()
            return []

    def is_own_archive(client) -> bool:
        """F98: the open archive is the signed-in user's own — theirs, or the primary one for a user without one."""
        from flask_login import current_user
        if client is None or not current_user.is_authenticated:
            return True
        own = getattr(current_user, "default_client_id", None)
        return client.id == own if own else client.database is None

    def no_accounts() -> bool:
        """F97: no account of the user's yet — only the fixed Contanti and Debiti — so what is entered lands in cash."""
        from app.models.account import Account
        try:
            return Account.query.filter(Account.fixed.is_(None), Account.active.is_(True)).count() == 0
        except Exception:  # noqa: BLE001 - a page must not break over a notice
            db.session.rollback()
            return False

    # globals, not context: the form macros imported without context use them too (F20: whose things are)
    app.jinja_env.globals.update(owner_choices=family.choices, owner_label=family.label)

    @app.context_processor
    def inject_settings():
        return {"settings": current_settings(), "palette_vars": lambda: palettes.css_vars(current_settings()), "notification_count": notification_count, "display": display.prefs(),
                "current_language": current_language, "working_client": working_client, "no_accounts": no_accounts, "archive_choices": archive_choices, "is_own_archive": is_own_archive, "client_groups": client_groups, "ui_font": current_font,
                "shown": sections.in_menu, "allowed": sections.allowed, "shown_any": lambda *keys: any(sections.in_menu(k) for k in keys)}
