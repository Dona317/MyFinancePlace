"""
Groups of archives (F21): a family or a group whose members each keep an archive of their own (studio mode, F11),
added up read only on the consolidated page (services/consolidation.py). Everybody sees every group; the archive a
user opens at sign-in is chosen by an administrator.
"""
from __future__ import annotations

from flask_babel import gettext as _

from app.extensions import db
from app.models.client import Client, ClientGroup
from app.models.user import User
from app.services import studio


class GroupError(Exception):
    """A group cannot be saved; the message is shown to the user."""


def all_groups() -> list[ClientGroup]:
    return ClientGroup.query.order_by(ClientGroup.name).all()


def of(client: Client | None) -> list[ClientGroup]:
    """The groups an archive belongs to."""
    if client is None:
        return []
    return [group for group in all_groups() if any(member.id == client.id for member in group.members)]


def save(group: ClientGroup | None, name: str, color: str | None, notes: str | None, member_ids) -> ClientGroup:
    name = " ".join((name or "").split())[:120]
    if not name:
        raise GroupError(_("Scrivi il nome del gruppo."))
    ids = {int(i) for i in member_ids if str(i).isdigit()}
    members = Client.query.filter(Client.id.in_(ids)).all() if ids else []
    if len(members) < 2:
        raise GroupError(_("Un gruppo mette insieme almeno due archivi."))
    group = group or ClientGroup()
    group.name, group.notes = name, (notes or "").strip() or None
    group.color = color if color in studio.COLORS else (group.color or studio.COLORS[ClientGroup.query.count() % len(studio.COLORS)])
    group.members = members
    db.session.add(group)
    db.session.commit()
    return group


def delete(group: ClientGroup) -> None:
    """Only the group goes: the archives and their data stay as they are."""
    db.session.delete(group)
    db.session.commit()


def set_start(user: User, client_id: int | None) -> None:
    """The archive `user` opens at sign-in (None: the primary one)."""
    client = db.session.get(Client, client_id) if client_id else None
    if client is not None and client.archived:
        raise GroupError(_("«%(name)s» è archiviato: riattivalo prima.", name=client.name))
    user.default_client_id = client.id if client is not None and not client.is_primary else None
    db.session.commit()


def open_start(user: User) -> None:
    """At sign-in: open the user's own archive, when they have one and it is still usable."""
    client = db.session.get(Client, user.default_client_id) if user.default_client_id else None
    if client is not None and not client.archived:
        studio.choose(client)
