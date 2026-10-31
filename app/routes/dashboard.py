from datetime import date
from flask import render_template, redirect, request, url_for
from apiflask import APIBlueprint
from app.models.transaction import Transaction
from app.services import analytics, budgets, i18n, reports, settings_store

dashboard_bp = APIBlueprint(
    "dashboard",
    __name__,
    tag="Dashboard"
)


TREND_LINES = 6  # categories drawn one by one in the monthly lines; the rest are added up in «Altre»
# Windows the figures at the top of the dashboard can cover: the report periods that look back from today
KPI_PERIODS = ("this_month", "last_month", "last_3", "this_year", "last_12")
KPI_PERIOD_SETTING = "dashboard_kpi_period"


def _translated(trend: dict) -> dict:
    """Series names like «Altre» / «Senza categoria» in the interface language (user categories stay as they are)."""
    return {**trend, "datasets": [{**ds, "label": i18n.tr(ds["label"])} for ds in trend["datasets"]]}


@dashboard_bp.route("/")
def index():
    return redirect(url_for("dashboard.dashboard"))


@dashboard_bp.route("/dashboard/kpi-period", methods=["POST"])
def save_kpi_period():
    """Remember the window of the top figures (kept for every visit, not per browser)."""
    period = request.form.get("period")
    if period in KPI_PERIODS:
        settings_store.set(KPI_PERIOD_SETTING, period)
    return redirect(url_for("dashboard.dashboard", year=request.form.get("year", type=int)))


SERIES_METRICS = ("income", "expenses", "net", "savings_rate")


@dashboard_bp.route("/dashboard/series")
def series():
    """The monthly figures of one custom chart: metric (income, expenses, net, savings_rate) over the year
    chosen or the last 12 months. Values are rounded to cents, the rate to tenths of a percent."""
    metric = request.args.get("metric", "")
    if metric not in SERIES_METRICS:
        return {"error": "metric"}, 400
    today = date.today()
    if request.args.get("period") == "last_12":
        months = analytics.last_12_months(today)
        labels, income, expenses = months["labels"], months["income"], months["expenses"]
    else:
        year = request.args.get("year", type=int) or today.year
        year_figures = analytics.monthly_series(year)
        labels, income, expenses = year_figures["labels"], year_figures["income"], year_figures["expenses"]
    if metric == "income":
        values = income
    elif metric == "expenses":
        values = expenses
    elif metric == "net":
        values = [i - e for i, e in zip(income, expenses)]
    else:
        values = [analytics.savings_rate(i, e) for i, e in zip(income, expenses)]
    return {"labels": labels, "values": [round(v, 2) for v in values]}


@dashboard_bp.route("/dashboard")
def dashboard():
    today = date.today()
    kpi_period = settings_store.get(KPI_PERIOD_SETTING, "this_month")
    if kpi_period not in KPI_PERIODS:
        kpi_period = "this_month"
    kpi_window = reports.period_range(kpi_period, today=today)
    kpis = analytics.dashboard_kpis(today, kpi_window)
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
        kpi_period=kpi_period,
        kpi_label=reports.PERIODS[kpi_period],
        kpi_periods=[(key, reports.PERIODS[key]) for key in KPI_PERIODS],
        cash_flow=cash_flow,
        year=year, years=years,
        expense_breakdown=analytics.category_breakdown(year_start, year_end, "expense"),
        income_breakdown=analytics.category_breakdown(year_start, year_end, "income"),
        expense_trend=_translated(analytics.monthly_category_trend(year, TREND_LINES, "expense", months, other=True)),
        income_trend=_translated(analytics.monthly_category_trend(year, TREND_LINES, "income", months, other=True)),
        cumulative=analytics.cumulative_series(year, months),
        sankey=analytics.sankey(year_start, year_end),
        recent_transactions=recent,
        budget_alerts=budgets.alerts(today),
    )
