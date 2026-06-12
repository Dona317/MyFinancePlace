from flask import Blueprint, render_template, request, redirect, url_for

insurance_bp = Blueprint("insurance", __name__, url_prefix="/insurance")


@insurance_bp.route("/")
def index():
    # TODO: fetch insurance policies from DB
    policies = []
    return render_template("insurance/index.html", policies=policies)


@insurance_bp.route("/new", methods=["POST"])
def new():
    # TODO: validate and save new policy
    return redirect(url_for("insurance.index"))


@insurance_bp.route("/<int:policy_id>/edit", methods=["POST"])
def edit(policy_id):
    # TODO: update existing policy
    return redirect(url_for("insurance.index"))


@insurance_bp.route("/<int:policy_id>/delete", methods=["POST"])
def delete(policy_id):
    # TODO: delete policy
    return redirect(url_for("insurance.index"))
