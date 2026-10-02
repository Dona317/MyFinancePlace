"""Settings → Account e utenti: your own password; administrators add, reset and delete users (data is shared)."""
from flask import abort, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_login import current_user

from app.extensions import db
from app.models.user import MIN_PASSWORD, User
from app.routes.settings import settings_bp
from app.services import users


def _admin_only():
    if not (current_user.is_authenticated and current_user.is_admin):
        abort(403)


@settings_bp.route("/account")
def account():
    user_list = User.query.order_by(db.func.lower(User.username)).all() if current_user.is_authenticated and current_user.is_admin else []
    return render_template("settings/account.html", users=user_list, min_password=MIN_PASSWORD)


@settings_bp.route("/account/password", methods=["POST"])
def account_password():
    if not current_user.is_authenticated:
        abort(403)
    try:
        users.change_password(current_user, request.form.get("current", ""), request.form.get("password", ""),
                              request.form.get("confirm", ""))
        flash(_("Password cambiata."), "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("settings.account"))


@settings_bp.route("/users/add", methods=["POST"])
def user_add():
    _admin_only()
    try:
        user = users.create(request.form.get("username", ""), request.form.get("password", ""),
                            is_admin="is_admin" in request.form)
        flash(_("Utente «%(name)s» creato: vede gli stessi dati di tutti.", name=user.username), "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("settings.account"))


@settings_bp.route("/users/<int:user_id>/password", methods=["POST"])
def user_reset_password(user_id):
    _admin_only()
    user = db.get_or_404(User, user_id)
    try:
        users.reset_password(user, request.form.get("password", ""))
        flash(_("Nuova password impostata per «%(name)s».", name=user.username), "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("settings.account"))


@settings_bp.route("/users/<int:user_id>/delete", methods=["POST"])
def user_delete(user_id):
    _admin_only()
    user = db.get_or_404(User, user_id)
    try:
        users.delete(user, current_user)
        flash(_("Utente «%(name)s» eliminato.", name=user.username), "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("settings.account"))
