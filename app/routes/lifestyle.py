from datetime import date
from flask import render_template, request
from apiflask import APIBlueprint
from app.services import analytics

lifestyle_bp = APIBlueprint(
    "lifestyle",
    __name__,
    url_prefix="/lifestyle",
    tag="Lifestyle"
)


@lifestyle_bp.route("/")
def index():
    years = analytics.available_years()
    year = request.args.get("year", type=int) or date.today().year
    report = analytics.lifestyle_report(year)
    return render_template("lifestyle/index.html", report=report, years=years, year=year)


@lifestyle_bp.route("/goals")
def goals():
    # TODO: pass goals list and progress data
    return render_template("lifestyle/goals.html")
