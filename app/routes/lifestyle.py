from flask import Blueprint, render_template

lifestyle_bp = Blueprint("lifestyle", __name__, url_prefix="/lifestyle")


@lifestyle_bp.route("/")
def index():
    # TODO: pass category breakdown data
    return render_template("lifestyle/index.html")


@lifestyle_bp.route("/goals")
def goals():
    # TODO: pass goals list and progress data
    return render_template("lifestyle/goals.html")
