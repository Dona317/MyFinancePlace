from flask import render_template
from apiflask import APIBlueprint

lifestyle_bp = APIBlueprint(
    "lifestyle",
    __name__,
    url_prefix="/lifestyle",
    tag="Lifestyle"
)


@lifestyle_bp.route("/")
def index():
    # TODO: pass category breakdown data
    return render_template("lifestyle/index.html")


@lifestyle_bp.route("/goals")
def goals():
    # TODO: pass goals list and progress data
    return render_template("lifestyle/goals.html")
