"""
Reminders shown by the operating system (F14), for every client archive: when the desktop app starts (so the ones of
the days it was closed arrive too) and then every hour. A reminder is shown again once a day until it is read
(dismissed in Notifiche); more than MAX_SEPARATE at once become a few plus one that counts the rest.

What was shown and when is kept per archive (setting notifications.shown: key → day).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from flask import url_for
from flask_babel import gettext as _
from flask_babel import ngettext

from app.services import desktop, notifications, settings_store, studio

SHOWN_SETTING = "notifications.shown"
MAX_SEPARATE = 3


@dataclass
class Message:
    title: str
    body: str
    link: str  # desktop.open_link: the archive and the page a click opens


def _due_in_archive(client, today: date, label: bool) -> tuple[list[Message], list[str]]:
    """The archive's unread reminders not shown yet today, as messages, and their keys."""
    shown = settings_store.get_json(SHOWN_SETTING, {}, expect=dict)
    due = [n for n in notifications.collect(today) if shown.get(n.key) != today.isoformat()]
    prefix = f"{client.name} · " if label else ""
    return ([Message(prefix + n.title, n.detail, desktop.open_link(client.id, n.url)) for n in due],
            [n.key for n in due])


def _remember(keys: list[str], today: date) -> None:
    current = notifications.collect(today, include_dismissed=True)
    alive = {n.key for n in current}
    shown = {k: v for k, v in settings_store.get_json(SHOWN_SETTING, {}, expect=dict).items() if k in alive}
    shown.update(dict.fromkeys(keys, today.isoformat()))
    settings_store.set_json(SHOWN_SETTING, shown)


def _grouped(messages: list[Message], summary_link: str) -> list[Message]:
    if len(messages) <= MAX_SEPARATE:
        return messages
    kept, rest = messages[:MAX_SEPARATE - 1], len(messages) - (MAX_SEPARATE - 1)
    return kept + [Message(ngettext("Un altro promemoria", "Altri %(num)s promemoria", rest),
                           _("Aprili in MyFinancePlace → Notifiche."), summary_link)]


def run(send: Callable[[Message], bool], today: date | None = None) -> int:
    """Show the due reminders of every archive (the open request's database is switched for each); returns how many
    messages were sent. Needs an app and a request context (links are built with url_for)."""
    today = today or date.today()
    archives = [c for c in studio.clients() if not c.archived]
    label = len(archives) > 1
    messages, sent_keys = [], {}
    for client in archives:
        with studio.using(client):
            found, keys = _due_in_archive(client, today, label)
        messages += found
        sent_keys[client.id] = keys
    if not messages:
        return 0
    primary = studio.primary()
    sent = sum(1 for message in _grouped(messages, desktop.open_link(primary.id, url_for("notifications.index")))
               if send(message))
    if sent:
        for client in archives:
            if sent_keys[client.id]:
                with studio.using(client):
                    _remember(sent_keys[client.id], today)
    return sent
