"""
The sections of the app (the entries of the menu) and who sees them, on three levels:

1. Settings → Moduli: a section switched off for the whole installation (the existing module_* switches);
2. blocked by an administrator for a user: not in the menu, and its pages answer «access denied» (also by address
   or API);
3. hidden by the user from their own menu: their choice, still reachable from a link and undone in Settings.

Administrators are never blocked. Dashboard and Settings are always there: every user needs a home page and the way
back to their choices.
"""
from __future__ import annotations

from dataclasses import dataclass

from flask import current_app, has_request_context
from flask_babel import gettext as _
from flask_login import current_user

from app.extensions import db
from app.services.i18n import _l
from app.services.ui_settings import current_settings


@dataclass(frozen=True)
class Section:
    key: str
    label: str
    icon: str
    group: str
    endpoints: tuple[str, ...]  # "blueprint." for a whole blueprint, or endpoint names / prefixes
    setting: str | None = None  # its switch in Settings → Moduli, if it has one


SECTIONS = [
    Section("reports", _l("Report"), "bar-chart-line", _l("Panoramica"), ("reports.",)),
    Section("accounting", _l("Contabilità"), "clipboard-data", _l("Contabilità"), ("accounting.",)),
    Section("forecast", _l("Previsioni"), "graph-up-arrow", _l("Contabilità"), ("forecast.",)),
    Section("subscriptions", _l("Abbonamenti"), "arrow-repeat", _l("Contabilità"), ("subscriptions.",)),
    Section("lifestyle", _l("Spese e Tendenze"), "pie-chart", _l("Stile di Vita"), ("lifestyle.index",)),
    Section("budget", _l("Budget"), "clipboard-check", _l("Stile di Vita"), ("lifestyle.budget",)),
    Section("goals", _l("Obiettivi"), "trophy", _l("Stile di Vita"), ("lifestyle.goal",), "lifestyle_goals"),
    Section("transactions", _l("Transazioni"), "list-ul", _l("Gestione"), ("transactions.",)),
    Section("accounts", _l("Conti e Carte"), "bank", _l("Gestione"), ("accounts.",)),
    Section("portfolio", _l("Portafoglio"), "briefcase", _l("Gestione"), ("portfolio.",), "module_portfolio"),
    Section("debt", _l("Debiti"), "credit-card", _l("Gestione"), ("debt.",), "module_debt"),
    Section("insurance", _l("Assicurazioni"), "shield-check", _l("Gestione"), ("insurance.",), "module_insurance"),
    Section("documents", _l("Documenti"), "folder2-open", _l("Gestione"), ("documents.",), "module_documents"),
    Section("tax", _l("Fisco"), "percent", _l("Gestione"), ("tax.",), "module_tax"),
    Section("snapshots", _l("Istantanee"), "camera", _l("Strumenti"), ("snapshots.",), "module_snapshots"),
    Section("export", _l("Esporta e importa"), "box-arrow-up", _l("Strumenti"), ("export.",), "module_export"),
    Section("clients", _l("Clienti"), "people", _l("Strumenti"), ("clients.",)),
    Section("notifications", _l("Notifiche"), "bell", _l("Strumenti"), ("notifications.",)),
]
BY_KEY = {section.key: section for section in SECTIONS}


def section_of(endpoint: str | None) -> str | None:
    """The section a page belongs to (None: always reachable, e.g. Dashboard, Settings, sign-in)."""
    if not endpoint:
        return None
    for section in SECTIONS:
        if any(endpoint.startswith(prefix) for prefix in section.endpoints):
            return section.key
    return None


def clean(keys) -> list[str]:
    """Only known section keys, once each, in menu order."""
    chosen = set(keys or [])
    return [section.key for section in SECTIONS if section.key in chosen]


def _user():
    if not has_request_context() or current_app.config.get("LOGIN_DISABLED"):
        return None
    return current_user if current_user.is_authenticated else None


def blocked(key: str, user=None) -> bool:
    """Blocked by an administrator for this user (an administrator is never blocked)."""
    user = user or _user()
    return bool(user and not user.is_admin and key in (user.blocked_sections or []))


def hidden(key: str, user=None) -> bool:
    """Hidden by the user from their own menu."""
    user = user or _user()
    return bool(user and key in (user.hidden_sections or []))


def switched_off(key: str) -> bool:
    """Switched off for everybody in Settings → Moduli (only some sections have such a switch)."""
    setting = BY_KEY[key].setting
    return bool(setting) and not current_settings().get(setting, True)


def allowed(key: str) -> bool:
    """The user may use the section (its data shown elsewhere too, e.g. on the dashboard): not off, not blocked."""
    return not switched_off(key) and not blocked(key)


def in_menu(key: str) -> bool:
    """Shown in the menu: not switched off, not blocked, not hidden."""
    return not switched_off(key) and not blocked(key) and not hidden(key)


def set_hidden(user, keys) -> None:
    """The sections the user hides from their own menu."""
    user.hidden_sections = clean(keys)
    db.session.commit()


def set_blocked(user, keys) -> None:
    """The sections an administrator blocks for `user` (an administrator cannot be blocked)."""
    if user.is_admin:
        raise ValueError(_("Gli amministratori vedono sempre tutte le sezioni."))
    user.blocked_sections = clean(keys)
    db.session.commit()


def grouped() -> list[tuple[str, list[Section]]]:
    """The sections by group of the menu, in menu order (for the settings pages)."""
    groups: dict[str, list[Section]] = {}
    for section in SECTIONS:
        groups.setdefault(str(section.group), []).append(section)
    return list(groups.items())
