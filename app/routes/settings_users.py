"""Settings → Account e utenti: your own password; administrators add, reset and delete users. Each user has an
archive of their own (F24, decided on 2 Nov 2026); an administrator can export the archives of the users chosen."""
import io
import zipfile
from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user

from app.extensions import db
from app.models.client import Client
from app.models.user import MIN_PASSWORD, User
from app.routes.helpers import download, flash_errors
from app.routes.settings import settings_bp
from app.services import groups, sections, studio, users


def _admin_only():
    if not (current_user.is_authenticated and current_user.is_admin):
        abort(403)


@settings_bp.route("/account")
def account():
    user_list = User.query.order_by(db.func.lower(User.username)).all() if current_user.is_authenticated and current_user.is_admin else []
    archives = studio.clients() if user_list and studio.is_studio() else []
    return render_template("settings/account.html", users=user_list, min_password=MIN_PASSWORD, archives=archives)


@settings_bp.route("/account/password", methods=["POST"])
def account_password():
    if not current_user.is_authenticated:
        abort(403)
    with flash_errors():
        users.change_password(current_user, request.form.get("current", ""), request.form.get("password", ""),
                              request.form.get("confirm", ""))
        flash(_("Password cambiata."), "success")
    return redirect(url_for("settings.account"))


@settings_bp.route("/users/add", methods=["POST"])
def user_add():
    _admin_only()
    with flash_errors(ValueError, studio.StudioError, rollback=True):
        user = users.create(request.form.get("username", ""), request.form.get("password", ""),
                            is_admin="is_admin" in request.form)
        own_archive(user)
        flash(_("Utente «%(name)s» creato, con un archivio tutto suo.", name=user.username), "success")
    return redirect(url_for("settings.account"))


def own_archive(user: User) -> Client:
    """The archive of a user: a database of their own, opened at sign-in (F24). Made once."""
    client = db.session.get(Client, user.default_client_id) if user.default_client_id else None
    if client is None:
        client = studio.create(user.username)
        groups.set_start(user, client.id)
    return client


@settings_bp.route("/users/<int:user_id>/archive", methods=["POST"])
def user_archive(user_id):
    """An existing user without an archive of their own gets one (their data starts empty)."""
    _admin_only()
    user = db.get_or_404(User, user_id)
    with flash_errors(studio.StudioError):
        client = own_archive(user)
        flash(_("«%(name)s» ha ora il suo archivio, «%(archive)s».", name=user.username, archive=client.name), "success")
    return redirect(url_for("settings.account"))


@settings_bp.route("/users/export", methods=["POST"])
def users_export():
    """The administrator downloads the whole archive of each user chosen: one zip with a backup per user (the same
    file «Backup completo» makes, to restore it anywhere)."""
    _admin_only()
    chosen = User.query.filter(User.id.in_([int(i) for i in request.form.getlist("user_id") if i.isdigit()])).all()
    if not chosen:
        flash(_("Scegli almeno un utente da esportare."), "warning")
        return redirect(url_for("settings.account"))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        for user in sorted(chosen, key=lambda u: u.username.lower()):
            client = db.session.get(Client, user.default_client_id) if user.default_client_id else studio.primary()
            bundle.writestr(f"{studio.slugify_file(user.username)}.zip", studio.backup(client))
    return download(buffer.getvalue(), f"archivi-utenti-{date.today():%Y%m%d}.zip", "application/zip")


@settings_bp.route("/users/<int:user_id>/password", methods=["POST"])
def user_reset_password(user_id):
    _admin_only()
    user = db.get_or_404(User, user_id)
    with flash_errors():
        users.reset_password(user, request.form.get("password", ""))
        flash(_("Nuova password impostata per «%(name)s».", name=user.username), "success")
    return redirect(url_for("settings.account"))


@settings_bp.route("/users/<int:user_id>/start", methods=["POST"])
def user_start(user_id):
    """The archive the user opens at sign-in (F21: each member of the family on their own)."""
    _admin_only()
    user = db.get_or_404(User, user_id)
    with flash_errors(groups.GroupError):
        groups.set_start(user, request.form.get("client_id", type=int))
        flash(_("Archivio di partenza di «%(name)s» aggiornato.", name=user.username), "success")
    return redirect(url_for("settings.account"))


@settings_bp.route("/users/<int:user_id>/delete", methods=["POST"])
def user_delete(user_id):
    _admin_only()
    user = db.get_or_404(User, user_id)
    with flash_errors():
        users.delete(user, current_user)
        flash(_("Utente «%(name)s» eliminato.", name=user.username), "success")
    return redirect(url_for("settings.account"))


# ── Sections of the menu: hidden by each user, blocked by an administrator ────

@settings_bp.route("/menu", methods=["GET", "POST"])
def my_menu():
    """Each user's own menu: the sections they want to see (the blocked ones stay off)."""
    if not current_user.is_authenticated:
        abort(404)  # sign-in switched off: one shared menu, Settings → Moduli
    if request.method == "POST":
        sections.set_hidden(current_user, [s.key for s in sections.SECTIONS if s.key not in request.form])
        flash(_("Il tuo menu è aggiornato."), "success")
        return redirect(url_for("settings.my_menu"))
    return render_template("settings/menu.html", groups=sections.grouped(), user=current_user, editing_self=True)


@settings_bp.route("/users/<int:user_id>/sections", methods=["GET", "POST"])
def user_sections(user_id):
    """An administrator chooses the sections a user may open."""
    _admin_only()
    user = db.get_or_404(User, user_id)
    if request.method == "POST":
        with flash_errors():
            sections.set_blocked(user, [s.key for s in sections.SECTIONS if s.key not in request.form])
            flash(_("Sezioni di «%(name)s» aggiornate.", name=user.username), "success")
        return redirect(url_for("settings.account"))
    return render_template("settings/menu.html", groups=sections.grouped(), user=user, editing_self=False)
