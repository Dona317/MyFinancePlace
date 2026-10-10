from apiflask import APIBlueprint
from flask import flash, redirect, render_template, request, session, url_for
from flask_babel import gettext as _
from flask_login import current_user, login_required, login_user, logout_user

from app.routes.helpers import back_to
from app.services import users

auth_bp = APIBlueprint(
    "auth",
    __name__,
    url_prefix="/auth",
    tag="Auth"
)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if not users.any_user():
        return redirect(url_for("auth.setup"))
    if current_user.is_authenticated:
        return back_to("dashboard.dashboard")
    if request.method == "POST":
        user = users.authenticate(request.form.get("username", ""), request.form.get("password", ""))
        if user is None:
            # the same message whether the name or the password is wrong
            flash(_("Nome utente o password non corretti."), "error")
            return render_template("auth/login.html", username=request.form.get("username", "")), 401
        login_user(user, remember="remember" in request.form)
        return back_to("dashboard.dashboard")
    return render_template("auth/login.html", username="")


@auth_bp.route("/setup", methods=["GET", "POST"])
def setup():
    """First visit: nobody can sign in yet, so the first user (an administrator) is created here."""
    if users.any_user():
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        try:
            user = users.create(request.form.get("username", ""), request.form.get("password", ""), is_admin=True,
                                confirm=request.form.get("confirm", ""))
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("auth/setup.html", username=request.form.get("username", ""))
        login_user(user)
        flash(_("Benvenuto! Il tuo account amministratore è pronto."), "success")
        return redirect(url_for("dashboard.dashboard"))
    return render_template("auth/setup.html", username="")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    logout_user()  # after the clear: it leaves the note that deletes the "remember me" cookie
    return redirect(url_for("auth.login"))
