from datetime import date

from apiflask import APIBlueprint
from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.transaction import Transaction
from app.routes.helpers import back_to, layout_answer
from app.services import analytics, forecast, forecast_prefs, planning
from app.services.parsing import to_decimal

forecast_bp = APIBlueprint(
    "forecast",
    __name__,
    url_prefix="/forecast",
    tag="Forecast"
)


FORECAST_TABS = {
    "next12": ("balance", "net", "upcoming"),
    "months": ("months", "income", "expenses", "categories"),
    "recurring": ("candidates", "upcoming"),
    "methods": ("methods", "stability", "help"),
}


@forecast_bp.route("/")
def index():
    if request.args.get("remember") and request.args.get("horizon"):  # the period box on top: the horizon is kept
        forecast.save_preferences(horizon=request.args.get("horizon"))
        return redirect(url_for("forecast.index", scenario=request.args.get("scenario")))
    # Values in the address (e.g. a shared link) win over the saved preferences, without replacing them
    prefs = forecast.preferences(request.args.get("method"), request.args.get("window"), request.args.get("horizon"),
                                 request.args.get("recurring"))
    # F101: the scenario (the page's presets), asked for in the address and then kept
    scenario = forecast_prefs.scenario(request.args.get("scenario"))
    result = forecast.apply_scenario(forecast.load(**prefs, today=date.today()), scenario)
    stability = analytics.income_stability(date.today())
    # UI-21: the page in tabs, each with its own blocks (Personalizza arranges them inside the tab)
    tab = request.args.get("tab", "next12")
    tab = tab if tab in FORECAST_TABS else "next12"
    return render_template(
        "forecast/index.html", scenario=scenario, scenarios=forecast_prefs.SCENARIOS,
        tab=tab, tab_blocks=FORECAST_TABS[tab],
        fc=result, prefs=prefs, methods=forecast.METHODS, frequencies=forecast.FREQUENCIES,
        recurring_amounts=forecast.RECURRING_AMOUNTS, layout=forecast.layout(), widgets=forecast.WIDGETS,
        window_range=forecast.WINDOW_RANGE, horizon_range=forecast.HORIZON_RANGE, stability=stability,
    )


@forecast_bp.route("/preferences", methods=["POST"])
def save_preferences():
    """Method, rolling window, horizon and recurring amounts chosen in the page: remembered for the next visits."""
    current = forecast.preferences()
    forecast.save_preferences(
        request.form.get("method", current["method"]),
        request.form.get("window", current["window"]),
        request.form.get("horizon", current["horizon"]),
        request.form.get("recurring", current["recurring"]),
    )
    return redirect(url_for("forecast.index"))


@forecast_bp.route("/layout", methods=["POST"])
def save_layout():
    """Panels of the page, in order, each half or whole row, shown or hidden: {"widgets": [...]} or {"reset": true}."""
    return layout_answer(forecast.save_layout, forecast.reset_layout)


@forecast_bp.route("/recurring/<int:tx_id>", methods=["POST"])
def mark_recurring(tx_id):
    """Flag a detected series as recurring: its latest transaction becomes the template of the schedule."""
    tx = db.get_or_404(Transaction, tx_id)
    frequency = request.form.get("frequency")
    if frequency not in forecast.FREQUENCIES:
        flash(_("Frequenza non valida."), "error")
        return redirect(url_for("forecast.index", tab="recurring"))
    tx.is_recurring, tx.recurrence = True, frequency
    db.session.commit()
    flash(_("«%(description)s» è ora una transazione ricorrente (%(value)s).", description=tx.description, value=forecast.FREQUENCIES[frequency][0].lower()), "success")
    return back_to("forecast.index", tab="recurring")  # back to the tab with the series to confirm


# ── Retirement / FIRE (F20) ────────────────────────────────────────────────────

RETIREMENT_FIELDS = ("age", "retire_at", "horizon", "wealth", "yearly_saving", "expenses", "pension", "expected_return",
                     "volatility", "inflation", "withdrawal_rate", "bonds_at_retirement", "bonds_at_horizon", "bond_return",
                     "bond_volatility")


@forecast_bp.route("/retirement", methods=["GET", "POST"])
def retirement():
    """Will the money last? A Monte Carlo of the years to come, in today's euro."""
    plan = planning.load()
    if request.method == "POST":
        if request.form.get("reset"):
            plan = planning.suggested()
        else:
            for name in RETIREMENT_FIELDS:
                value = to_decimal(request.form.get(name))
                if value is not None:
                    setattr(plan, name, int(value) if name in ("age", "retire_at", "horizon") else float(value))
        try:
            planning.save(plan)
            db.session.commit()
            flash(_("Simulazione aggiornata."), "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("forecast.retirement"))
    try:
        result = planning.simulate(plan)
    except ValueError as exc:
        flash(str(exc), "error")
        result = None
    return render_template("forecast/retirement.html", plan=plan, result=result, runs=planning.RUNS)
