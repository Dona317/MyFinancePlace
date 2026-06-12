from flask import Blueprint, render_template, redirect, url_for, request, flash

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # TODO: implement authentication logic
    if request.method == "POST":
        pass
    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    # TODO: implement registration logic
    if request.method == "POST":
        pass
    return render_template("auth/register.html")


@auth_bp.route("/logout")
def logout():
    # TODO: implement logout logic
    return redirect(url_for("auth.login"))
