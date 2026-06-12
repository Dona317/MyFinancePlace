from flask import Blueprint, render_template, redirect, url_for

dashboard_bp = Blueprint("dashboard", __name__)


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
