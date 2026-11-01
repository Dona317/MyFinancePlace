from datetime import date, timedelta

from apiflask import APIBlueprint
from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.models.transaction import Transaction
from app.models.wealth import Debt, Holding
from app.routes.helpers import year_arg
from app.services import (
    analytics,
    budgets,
    dashboard_prefs,
    encrypted_backup,
    forecast,
    i18n,
    performance,
    price_feed,
    sankey,
    settings_store,
    valuations,
    wealth,
)
from app.services.periods import month_index, month_label, month_labels, month_start, shift_month
from app.services.ui_settings import autonomy_target, current_settings

dashboard_bp = APIBlueprint(
    "dashboard",
    __name__,
    tag="Dashboard"
)


TREND_LINES = 6  # categories drawn one by one in the monthly lines; the rest are added up in «Altre»
PIE_PARTS = ("year", "H1", "H2", "Q1", "Q2", "Q3", "Q4")  # the doughnuts: the whole year, a half or a quarter
PIE_PART_SETTING = "dashboard.pie_part"
IMPACT_ROWS = 60  # biggest movements of the window sent to the page, filtered there by category
# Typical unexpected expenses («cigni neri»): what each would take from the savings
SHOCKS = (("car", 4000), ("appliance", 700), ("house", 8000), ("health", 2500))


def _translated(trend: dict) -> dict:
    """Series names like «Altre» / «Senza categoria» in the interface language (user categories stay as they are)."""
    return {**trend, "datasets": [{**ds, "key": ds["label"], "label": i18n.tr(ds["label"])} for ds in trend["datasets"]]}


def _part_bounds(year: int, part: str) -> tuple[date, date]:
    if part.startswith("Q"):
        first = (int(part[1]) - 1) * 3 + 1
        return date(year, first, 1), date(*shift_month(year, first, 3), 1)
    if part.startswith("H"):
        first = 1 if part == "H1" else 7
        return date(year, first, 1), date(*shift_month(year, first, 6), 1)
    return analytics.year_bounds(year)


def _window_cards(today: date) -> dict:
    """Income, expenses and savings rate of each card's own window, with its range and label."""
    cards = {}
    for card in dashboard_prefs.WINDOW_CARDS:
        window = dashboard_prefs.window(card)
        start, end = dashboard_prefs.window_range(window, today)
        totals = analytics.totals(start, end)
        cards[card] = {"window": window, "label": dashboard_prefs.window_label(window), "start": start,
                       "end": end, "totals": totals}
    return cards


def _forecast_figures(today: date) -> dict | None:
    """Income, expenses and savings rate the forecast gives for the period chosen in Settings (None: not enough
    history, or turned off)."""
    choice = dashboard_prefs.forecast_choice()
    if choice == "off":
        return None
    prefs = forecast.preferences()
    fc = forecast.load(prefs["method"], prefs["window"], 12 if choice == "year" else 1, prefs["recurring"], today=today)
    if fc.history_months < dashboard_prefs.MIN_HISTORY or not fc.months:
        return None
    if choice == "current":
        rows, label = [fc.months[0]], fc.months[0]["label"]
    elif choice == "next" and len(fc.months) > 1:
        rows, label = [fc.months[1]], fc.months[1]["label"]
    else:
        rows, label = fc.months[1:], str(dashboard_prefs.FORECASTS["year"])
    income = round(sum(r["income"] for r in rows), 2)
    expenses = round(sum(r["expenses"] for r in rows), 2)
    return {"label": label, "income": income, "expenses": expenses, "savings_rate": analytics.savings_rate(income, expenses)}


def _rates() -> dict:
    """Backward-looking rates for the investments and debt cards: the portfolio's return over the last 12 months (and
    per year since the start), the average interest rate of the debts weighted by what is still owed."""
    holdings = Holding.query.all()
    report = performance.report(holdings) if holdings else None
    one_year = report.windows.get("1A", (None, None))[0] if report else None
    debts = [d for d in Debt.query.all() if (getattr(d, "active", True) is not False)]
    owed = [(float(d.balance or d.principal or 0), float(d.annual_rate or 0)) for d in debts]
    weight = sum(amount for amount, _rate in owed)
    return {
        "return_1y": one_year,
        "return_annual": report.annualized if report else None,
        "debt_rate": round(sum(amount * rate for amount, rate in owed) / weight, 2) if weight else None,
    }


def _savings_flow(cash_flow: dict) -> dict:
    """The cash-flow chart's extra lines: saved each month, and saved since the first of the 12 months (bars)."""
    saved = [round(i - e, 2) for i, e in zip(cash_flow["income"], cash_flow["expenses"])]
    running, cumulative = 0.0, []
    for value in saved:
        running += value
        cumulative.append(round(running, 2))
    income_cum, expense_cum, a, b = [], [], 0.0, 0.0
    for i, e in zip(cash_flow["income"], cash_flow["expenses"]):
        a, b = a + i, b + e
        income_cum.append(round(a, 2))
        expense_cum.append(round(b, 2))
    return {"saved": saved, "saved_cumulative": cumulative, "income_cumulative": income_cum, "expenses_cumulative": expense_cum}


def _health(kpis: dict, cash_flow: dict) -> dict:
    """Months of spending covered without a salary (cash alone, cash and investments) and what a typical
    unexpected expense takes from the savings, in share of the liquid money and months of saving to rebuild it."""
    run = kpis["autonomy"]
    avg = run.get("avg_expenses")
    months_with_data = [(i, e) for i, e in zip(cash_flow["income"], cash_flow["expenses"]) if i or e]
    avg_saving = (sum(i - e for i, e in months_with_data) / len(months_with_data)) if months_with_data else 0.0
    liquid = run.get("liquid") or 0.0
    shocks = [{"key": key, "amount": amount,
               "share": round(amount / liquid * 100, 1) if liquid > 0 else None,
               "months": round(amount / avg_saving, 1) if avg_saving > 0 else None} for key, amount in SHOCKS]
    return {
        "months_cash": round(liquid / avg, 1) if avg else None,
        "months_invested": round((liquid + kpis["total_investments"]) / avg, 1) if avg else None,
        "avg_saving": round(avg_saving, 2),
        "shocks": shocks,
    }


def part_label(year: int, part: str) -> str:
    """Short name of the charts' period: «2026», «1H26», «2Q26 (Apr–Giu)»."""
    if part == "year":
        return str(year)
    number, kind = part[1], part[0]
    if kind == "H":
        return f"{number}{kind}{year % 100:02d}"
    names = month_labels()
    first = (int(number) - 1) * 3
    return f"{number}{kind}{year % 100:02d} ({names[first]}–{names[first + 2]})"


def _chart_months(start: date, end: date, today: date) -> range:
    """The month indexes of the charts' period, up to the current month."""
    return range(month_index(start), min(month_index(end) - 1, month_index(today)) + 1)


def _flow(months: range) -> dict:
    """Income and expenses of each month of the period."""
    labels, income, expenses = [], [], []
    for index in months:
        totals = analytics.totals(month_start(index), month_start(index + 1))
        labels.append(month_label(index))
        income.append(totals["income"])
        expenses.append(totals["expenses"])
    return {"labels": labels, "income": income, "expenses": expenses}


def _net_worth_trend(months: range, today: date) -> dict:
    """Each month-end of the period (today for the current month): cash, investments, other assets and debts, and
    the net worth they make."""
    ends = [min(month_start(index + 1) - timedelta(days=1), today) for index in months]
    rows = [wealth.balance_sheet(d) for d in ends]
    return {
        "labels": [d.strftime("%m/%y") for d in ends],
        "cash": [r["cash"] for r in rows],
        "investments": [r["investments"] for r in rows],
        "other": [round(r["total_assets"] - r["cash"] - r["investments"], 2) for r in rows],
        "debts": [-r["total_liabilities"] for r in rows],
        "net_worth": [r["net_worth"] for r in rows],
    }


@dashboard_bp.route("/")
def index():
    return redirect(url_for("dashboard.dashboard"))


@dashboard_bp.route("/dashboard")
def dashboard():
    valuations.refresh_daily()  # the depreciation of the cars and the like, once a day
    price_feed.refresh_in_background()  # the day's prices, once a day (when turned on)
    encrypted_backup.run_in_background()  # the automatic encrypted backup, when due
    today = date.today()
    settings = current_settings()
    layout = [w for w in dashboard_prefs.layout() if settings.get(dashboard_prefs.WIDGETS[w["id"]][2], True)]
    shown = {w["id"] for w in layout if w["visible"]}
    kpis = analytics.dashboard_kpis(today)
    last_12 = analytics.last_12_months(today)  # the financial health is about the last 12 months, whatever the period
    # The totals by category, their monthly lines and the running totals: one year (the current one by default)
    years = analytics.available_years()
    year = year_arg(today.year, choices=years)
    months = analytics.months_to_show(year, today)
    # The doughnuts: the whole year, a half or a quarter (remembered)
    part = request.args.get("part")
    if part in PIE_PARTS:
        settings_store.set(PIE_PART_SETTING, part)
    part = settings_store.get(PIE_PART_SETTING, "year")
    part = part if part in PIE_PARTS else "year"
    pie_start, pie_end = _part_bounds(year, part)
    # every chart of the page follows the same period: the year chosen, a half or a quarter of it
    chart_months = _chart_months(pie_start, pie_end, today)
    cash_flow = _flow(chart_months)
    first, last = pie_start.month - 1, pie_start.month - 1 + len(chart_months)

    def trend_of(kind: str) -> dict:
        trend = _translated(analytics.monthly_category_trend(year, TREND_LINES, kind, months, other=True))
        return {**trend, "labels": trend["labels"][first:last],
                "datasets": [{**ds, "data": ds["data"][first:last]} for ds in trend["datasets"]]}

    period_totals = analytics.totals(pie_start, pie_end)
    cards = _window_cards(today)
    window = cards["expenses"]
    recent = (Transaction.query.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(8).all()
              if "recent" in shown else [])
    impact = (Transaction.query.filter(Transaction.type.in_(["income", "expense"]),
                                       Transaction.date >= window["start"], Transaction.date < window["end"])
              .order_by(Transaction.amount_base.desc().nullslast()).limit(IMPACT_ROWS).all() if "recent" in shown else [])
    return render_template(
        "dashboard/index.html",
        kpis=kpis,
        cards=cards,
        window_presets=dashboard_prefs.preset_choices(),
        forecast_figures=_forecast_figures(today),
        rates=_rates() if settings["dashboard_investments"] or settings["dashboard_debt"] else {},
        cash_flow=cash_flow,
        savings_flow=_savings_flow(cash_flow),
        year=year, years=years, part=part, pie_parts=PIE_PARTS, pie_start=pie_start, pie_last=pie_end - timedelta(days=1),
        expense_breakdown=analytics.category_breakdown(pie_start, pie_end, "expense"),
        income_breakdown=analytics.category_breakdown(pie_start, pie_end, "income"),
        expense_trend=trend_of("expense"),
        income_trend=trend_of("income"),
        period_totals=period_totals,
        part_labels={p: part_label(year, p) for p in PIE_PARTS}, period_label=part_label(year, part),
        savings=analytics.savings_rates_by_year(today),
        sankey=sankey.flow(pie_start, pie_end) if "sankey" in shown else None,
        year_start=pie_start, year_last=pie_end - timedelta(days=1),
        net_worth_trend=_net_worth_trend(chart_months, today) if "net_worth" in shown and chart_months else None,
        recent_transactions=recent,
        impact_transactions=impact,
        health=_health(kpis, last_12),
        budget_alerts=budgets.alerts(today),
        autonomy_target=autonomy_target(),
        layout=layout,
        widgets=dashboard_prefs.WIDGETS,
    )


@dashboard_bp.route("/dashboard/window", methods=["POST"])
def save_window():
    """The time window of one card: {"card": "income", "window": {"period": "last_n", "n": 4}}, kept for every visit."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error=_("Atteso un oggetto JSON.")), 400
    try:
        window = dashboard_prefs.save_window(data.get("card"), data.get("window"))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(window=window, label=dashboard_prefs.window_label(window))


@dashboard_bp.route("/dashboard/windows/reset", methods=["POST"])
def reset_windows():
    """Settings → Dashboard: every card back to the default window (this month)."""
    dashboard_prefs.reset_windows()
    flash(_("Finestre temporali delle schede riportate al mese in corso."), "success")
    return redirect(request.form.get("next") or url_for("settings.index", _anchor="dashboard"))


@dashboard_bp.route("/dashboard/layout", methods=["POST"])
def save_layout():
    """Blocks of the page, in order, each 1–3 thirds of the row, shown or hidden: {"widgets": [...]} or {"reset": true}."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error=_("Atteso un oggetto JSON.")), 400
    if data.get("reset"):
        return jsonify(layout=dashboard_prefs.reset_layout())
    if not isinstance(data.get("widgets"), list):
        return jsonify(error=_("Manca l'elenco dei blocchi.")), 400
    return jsonify(layout=dashboard_prefs.save_layout(data["widgets"]))
