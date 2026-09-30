"""
Who can open the app. The data is shared by every user; an administrator adds and removes users.
The very first user (created on the first visit, when there is nobody yet) is an administrator.
"""
from datetime import datetime

from flask_babel import gettext as _

from app.extensions import db
from app.models.user import MIN_PASSWORD, User


def any_user() -> bool:
    return db.session.query(User.id).limit(1).first() is not None


def check_password(password: str, confirm: str | None = None) -> None:
    """ValueError with a message when the new password is not acceptable."""
    if len(password or "") < MIN_PASSWORD:
        raise ValueError(_("Password: almeno %(count)s caratteri.", count=MIN_PASSWORD))
    if confirm is not None and password != confirm:
        raise ValueError(_("Le due password non coincidono."))


def create(username: str, password: str, is_admin: bool = False, confirm: str | None = None) -> User:
    username = (username or "").strip()
    if not username:
        raise ValueError(_("Nome utente: campo obbligatorio."))
    if User.query.filter(db.func.lower(User.username) == username.lower()).first():
        raise ValueError(_("Esiste già un utente «%(name)s».", name=username))
    check_password(password, confirm)
    user = User(username=username, is_admin=is_admin)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def authenticate(username: str, password: str) -> User | None:
    user = User.query.filter(db.func.lower(User.username) == (username or "").strip().lower()).first()
    if user is None or not user.check_password(password):
        return None
    user.last_login = datetime.now()
    db.session.commit()
    return user


def change_password(user: User, current: str, new: str, confirm: str) -> None:
    if not user.check_password(current):
        raise ValueError(_("La password attuale non è corretta."))
    check_password(new, confirm)
    user.set_password(new)
    db.session.commit()


def reset_password(user: User, new: str) -> None:
    check_password(new)
    user.set_password(new)
    db.session.commit()


def delete(user: User, by: User) -> None:
    if user.id == by.id:
        raise ValueError(_("Non puoi eliminare il tuo stesso utente."))
    if user.is_admin and User.query.filter_by(is_admin=True).count() <= 1:
        raise ValueError(_("Serve almeno un amministratore."))
    db.session.delete(user)
    db.session.commit()
