from datetime import date
from flask import render_template, redirect, url_for
from apiflask import APIBlueprint
from app.models.transaction import Transaction
from app.services import analytics

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
    today = date.today()
    kpis = analytics.dashboard_kpis(today)
    cash_flow = analytics.last_12_months(today)
    month_start, month_end = analytics.month_bounds(today.year, today.month)
    expense_breakdown = analytics.category_breakdown(month_start, month_end)
    recent = (
        Transaction.query
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(8)
        .all()
    )
    return render_template(
        "dashboard/index.html",
        kpis=kpis,
        cash_flow=cash_flow,
        expense_breakdown=expense_breakdown,
        recent_transactions=recent,
    )
