"""The desktop app's pages (F14): its settings, the link a notification opens, and the call that brings the window up."""
import hmac
import threading

from apiflask import APIBlueprint
from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.client import Client
from app.services import desktop, studio

desktop_bp = APIBlueprint("desktop", __name__, url_prefix="/desktop", tag="Desktop")


def _only_on_desktop():
    if not desktop.available():
        abort(404)


@desktop_bp.route("/settings")
def settings_page():
    _only_on_desktop()
    return render_template("settings/desktop.html", prefs=desktop.prefs())


@desktop_bp.route("/settings", methods=["POST"])
def settings_save():
    _only_on_desktop()
    try:
        desktop.save(notify="notify" in request.form, start_with_computer="autostart" in request.form)
        flash(_("Impostazioni dell'app salvate."), "success")
    except OSError as exc:
        flash(_("Avvio automatico non modificato: %(exc)s", exc=exc), "error")
    return redirect(url_for("desktop.settings_page"))


@desktop_bp.route("/open/<token>")
def open_link(token):
    """A notification's link: the reminder's archive, on its page."""
    target = desktop.read_link(token)
    client = db.session.get(Client, target[0]) if target else None
    if client is None:
        return redirect(url_for("notifications.index"))
    studio.choose(client)
    return redirect(target[1])


def _launcher_call(action: str):
    """The launcher's hook for `action`, when the caller has its token (running.json in the user's data folder:
    only the same user's programs read it); 404 otherwise."""
    expected = current_app.config.get("DESKTOP_TOKEN") or ""
    hook = current_app.config.get(action)
    if not expected or hook is None or not hmac.compare_digest(request.form.get("token", ""), expected):
        abort(404)
    return hook


@desktop_bp.route("/show", methods=["POST"])
def show():
    """Called by a second start of the app (or a click on a notification): bring the open window up, on a page."""
    show_window = _launcher_call("DESKTOP_SHOW")
    to = request.form.get("to") or ""
    show_window(url_for("desktop.open_link", token=to) if desktop.read_link(to) else "")
    return "", 204


@desktop_bp.route("/quit", methods=["POST"])
def quit_app():
    """Called by `MyFinancePlace --stop` (the installer, before an update or the uninstall): close the app cleanly."""
    threading.Timer(0.3, _launcher_call("DESKTOP_QUIT")).start()  # after this answer has left
    return "", 204
