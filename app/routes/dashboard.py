from flask import render_template, redirect, url_for
from apiflask import APIBlueprint

dashboard_bp = APIBlueprint(
    "dashboard",
    __name__,
    tag="Dashboard"    
)


@dashboard_bp.route("/")
def index():
    return redirect(url_for("dashboard.dashboard"))


@dashboard_bp.route("/dashboard")
def dashboard():
    # TODO: pass real KPI data from your service/model layer
    kpis = {
        "net_worth": 0,
        "monthly_income": 0,
        "monthly_expenses": 0,
        "savings_rate": 0,
        "total_investments": 0,
        "total_debt": 0,
    }
    return render_template("dashboard/index.html", kpis=kpis)
