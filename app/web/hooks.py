"""What runs before every request, in this order: open the client's archive, refuse requests from other sites or
with NUL characters, ask to sign in, hide the modules switched off in Settings. Plus /health."""
from urllib.parse import urlsplit

from flask import Flask, current_app, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user
from sqlalchemy import text

from app.extensions import db, login_manager
from app.models.user import User
from app.services import studio, users
from app.services.ui_settings import current_settings, module_setting

PUBLIC_ENDPOINTS = {"static", "auth.login", "auth.setup", "health"}
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def wants_json() -> bool:
    """An API client (or the API docs) rather than a page: answer with JSON, never a redirect or HTML."""
    return (request.blueprint == "openapi" or "/api" in request.path or request.is_json
            or request.accept_mimetypes.best == "application/json")


def refused(status: int = 403):
    message = (_("Richiesta rifiutata: arriva da un altro sito.") if status == 403
               else _("Richiesta rifiutata: contiene caratteri non validi."))
    if wants_json():
        return jsonify({"message": message}), status
    return render_template("refused.html", message=message), status


def open_client_archive():
    """The client being worked on (F11): its database for the whole request."""
    if request.endpoint != "static":
        studio.open_from_session()


def refuse_foreign_and_broken_requests():
    """A page elsewhere could make the browser post a form here (cross-site request forgery), which matters most on
    the desktop app: a change asked by another origin is refused. Text with NUL characters too (the database cannot
    store or search it, and no keyboard types it)."""
    if request.endpoint is None:  # no such page or method: answered 404/405 anyway
        return None
    if request.method not in SAFE_METHODS:
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            return refused()
        source = request.headers.get("Origin") or request.headers.get("Referer")
        if source and (source == "null" or urlsplit(source).netloc != request.host):
            return refused()
    if any("\x00" in value for values in (request.args, request.form) for value in values.values()):
        return refused(400)
    return None


def require_login():
    """Every page needs a user, except the sign-in and first-setup pages."""
    if current_app.config.get("LOGIN_DISABLED") or request.endpoint in PUBLIC_ENDPOINTS or request.endpoint is None:
        return None
    if current_user.is_authenticated:
        return None
    if not users.any_user():  # first visit: create the administrator
        return redirect(url_for("auth.setup"))
    if wants_json():
        return jsonify({"message": "Accesso richiesto."}), 401
    return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))


def block_disabled_modules():
    """A module switched off in Settings disappears from the menu and its pages answer "not found"."""
    key = module_setting(request.blueprint, request.endpoint)
    if key and not current_settings().get(key, True):
        return render_template("module_disabled.html", setting=key), 404
    return None


def health():
    """For the desktop launcher and monitoring: the app answers and reaches its database."""
    try:
        db.session.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception:  # noqa: BLE001 - reported, not raised
        db.session.rollback()
        return {"ok": False}, 503


def load_user(user_id):
    return db.session.get(User, int(user_id)) if str(user_id).isdigit() else None


def register_hooks(app: Flask) -> None:
    login_manager.user_loader(load_user)
    app.get("/health")(app.doc(hide=True)(health))
    for hook in (open_client_archive, refuse_foreign_and_broken_requests, require_login, block_disabled_modules):
        app.before_request(hook)
