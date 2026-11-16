"""What runs before every request, in this order: open the client's archive, refuse requests from other sites or with
NUL characters, ask to sign in, keep a user who is not an administrator on their own archive, make its fixed accounts
(Contanti, Debiti), close the past years (once a day), hide the modules switched off in Settings and the sections
blocked for the user. After it: the answer compressed for a browser on another machine. Plus /health."""
import gzip
from datetime import date
from urllib.parse import urlsplit

from flask import Flask, current_app, g, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db, login_manager
from app.models.account import Account
from app.models.client import Client
from app.models.user import User
from app.services import accounts, cash, sections, studio, users, year_close
from app.services.ui_settings import current_settings, module_setting
from app.version import __version__

PUBLIC_ENDPOINTS = {"static", "auth.login", "auth.setup", "health", "desktop.show", "desktop.quit_app"}  # desktop.*: token-checked
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


def ensure_fixed_accounts():
    """F30: every archive has Contanti and Debiti (one quick look per request; made the first time). The tests turn
    it on where they need it (FIXED_ACCOUNTS), so that the others keep an archive with no accounts."""
    if request.endpoint in (None, "static", "health") or (current_app.testing and not current_app.config.get("FIXED_ACCOUNTS")):
        return
    try:
        if Account.query.filter(Account.fixed.isnot(None)).count() < len(accounts.FIXED):
            accounts.ensure_fixed()
    except SQLAlchemyError:  # an archive not upgraded yet: the next request tries again
        db.session.rollback()


_CLOSED_TODAY: set = set()  # (archive, day) already looked at by close_past_years


def close_past_years():
    """Once a day per archive: the cash movements of the register realigned (giroconti with Contanti), then from 1
    January the statements of the year before (and of any earlier one never closed) saved. Off in the tests unless
    YEAR_CLOSE is set."""
    if request.endpoint in (None, "static", "health") or (current_app.testing and not current_app.config.get("YEAR_CLOSE")):
        return
    client = g.get("client")
    key = (client.id if client is not None else None, date.today())
    if key in _CLOSED_TODAY:
        return
    try:
        cash.realign()  # withdrawals and cash paid in saved as expense or income become giroconti with Contanti
        year_close.ensure()
        _CLOSED_TODAY.add(key)
    except SQLAlchemyError:  # an archive not upgraded yet: the next request tries again
        db.session.rollback()


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


def confine_to_own_archive():
    """F24: a user who is not an administrator works only on their own archive — whatever the session says — and
    cannot open the pages that switch archive (clients, groups)."""
    if current_app.config.get("LOGIN_DISABLED") or not current_user.is_authenticated or current_user.is_admin:
        return None
    if request.blueprint in ("clients", "groups"):
        return refused()
    own = current_user.default_client_id
    current = studio.current()
    if own and (current is None or current.id != own):
        client = db.session.get(Client, own)
        if client is not None and not client.archived:
            studio.choose(client)
    return None


def block_disabled_modules():
    """A module switched off in Settings disappears from the menu and its pages answer "not found"; a section an
    administrator blocked for this user answers "access denied" (pages, API and downloads alike)."""
    key = module_setting(request.blueprint, request.endpoint)
    if key and not current_settings().get(key, True):
        return render_template("module_disabled.html", setting=key), 404
    section = sections.section_of(request.endpoint)
    if section and sections.blocked(section):
        if wants_json():
            return jsonify({"message": _("Non hai accesso a questa sezione.")}), 403
        return render_template("section_blocked.html", section=sections.BY_KEY[section]), 403
    return None


COMPRESSED_TYPES = {"text/html", "text/css", "text/plain", "text/csv", "application/javascript", "text/javascript",
                    "application/json", "image/svg+xml"}
COMPRESS_FROM = 1024  # bytes: below it the saving is not worth the work
LOOPBACK = {"127.0.0.1", "::1"}


def compress(response):
    """Pages are 200–400 KB of HTML and the style sheet 150 KB: gzip makes them about a seventh on the way to a
    browser on another machine (the cloud, the home network). Not for the desktop app or a proxy on this machine:
    nothing travels, the work would be wasted — and a proxy compresses by itself."""
    if (response.status_code != 200 or request.remote_addr in LOOPBACK or response.mimetype not in COMPRESSED_TYPES
            or "Content-Encoding" in response.headers or "gzip" not in request.headers.get("Accept-Encoding", "").lower()
            or request.method == "HEAD" or (response.is_streamed and not response.direct_passthrough)):
        return response
    response.direct_passthrough = False  # a static file: read it, as a page already is
    body = response.get_data()
    if len(body) >= COMPRESS_FROM:
        response.set_data(gzip.compress(body, compresslevel=5))
        response.headers["Content-Encoding"] = "gzip"
        response.vary.add("Accept-Encoding")
    return response


def health():
    """For the desktop launcher and monitoring: the app answers and reaches its database."""
    try:
        db.session.execute(text("SELECT 1"))
        return {"ok": True, "version": __version__}
    except Exception:  # noqa: BLE001 - reported, not raised
        db.session.rollback()
        return {"ok": False}, 503


def load_user(user_id):
    return db.session.get(User, int(user_id)) if str(user_id).isdigit() else None


def register_hooks(app: Flask) -> None:
    login_manager.user_loader(load_user)
    app.get("/health")(app.doc(hide=True)(health))
    for hook in (open_client_archive, refuse_foreign_and_broken_requests, require_login, confine_to_own_archive,
                 ensure_fixed_accounts, close_past_years, block_disabled_modules):
        app.before_request(hook)
    app.after_request(compress)
