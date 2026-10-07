from datetime import date
from flask import render_template, redirect, request, url_for
from apiflask import APIBlueprint
from app.models.transaction import Transaction
from app.services import analytics, budgets, i18n

dashboard_bp = APIBlueprint(
    "dashboard",
    __name__,
    tag="Dashboard"    
)


TREND_LINES = 6  # categories drawn one by one in the monthly lines; the rest are added up in «Altre»


def _translated(trend: dict) -> dict:
    """Series names like «Altre» / «Senza categoria» in the interface language (user categories stay as they are)."""
    return {**trend, "datasets": [{**ds, "label": i18n.tr(ds["label"])} for ds in trend["datasets"]]}


@dashboard_bp.route("/")
def index():
    return redirect(url_for("dashboard.dashboard"))


@dashboard_bp.route("/dashboard")
def dashboard():
    today = date.today()
    kpis = analytics.dashboard_kpis(today)
    cash_flow = analytics.last_12_months(today)
    # The totals by category, their monthly lines and the running totals: one year (the current one by default)
    years = analytics.available_years()
    year = request.args.get("year", type=int)
    year = year if year in years else today.year
    months = analytics.months_to_show(year, today)
    year_start, year_end = analytics.year_bounds(year)
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
        year=year, years=years,
        expense_breakdown=analytics.category_breakdown(year_start, year_end, "expense"),
        income_breakdown=analytics.category_breakdown(year_start, year_end, "income"),
        expense_trend=_translated(analytics.monthly_category_trend(year, TREND_LINES, "expense", months, other=True)),
        income_trend=_translated(analytics.monthly_category_trend(year, TREND_LINES, "income", months, other=True)),
        cumulative=analytics.cumulative_series(year, months),
        savings=analytics.savings_rates_by_year(today),
        sankey=analytics.sankey(year_start, year_end),
        recent_transactions=recent,
        budget_alerts=budgets.alerts(today),
    )
