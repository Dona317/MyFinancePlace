from datetime import date

from apiflask import APIBlueprint
from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.transaction import Transaction
from app.routes.helpers import back_to
from app.services import analytics, forecast, planning
from app.services.parsing import to_decimal

forecast_bp = APIBlueprint(
    "forecast",
    __name__,
    url_prefix="/forecast",
    tag="Forecast"
)


@forecast_bp.route("/")
def index():
    # Values in the address (e.g. a shared link) win over the saved preferences, without replacing them
    prefs = forecast.preferences(request.args.get("method"), request.args.get("window"), request.args.get("horizon"),
                                 request.args.get("recurring"))
    result = forecast.load(**prefs, today=date.today())
    stability = analytics.income_stability(date.today())
    return render_template(
        "forecast/index.html",
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
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Atteso un oggetto JSON."), 400
    if data.get("reset"):
        return jsonify(layout=forecast.reset_layout())
    if not isinstance(data.get("widgets"), list):
        return jsonify(error="Manca l'elenco dei pannelli."), 400
    return jsonify(layout=forecast.save_layout(data["widgets"]))


@forecast_bp.route("/recurring/<int:tx_id>", methods=["POST"])
def mark_recurring(tx_id):
    """Flag a detected series as recurring: its latest transaction becomes the template of the schedule."""
    tx = db.get_or_404(Transaction, tx_id)
    frequency = request.form.get("frequency")
    if frequency not in forecast.FREQUENCIES:
        flash(_("Frequenza non valida."), "error")
        return redirect(url_for("forecast.index"))
    tx.is_recurring, tx.recurrence = True, frequency
    db.session.commit()
    flash(_("«%(description)s» è ora una transazione ricorrente (%(value)s).", description=tx.description, value=forecast.FREQUENCIES[frequency][0].lower()), "success")
    return back_to("forecast.index")


# ── Retirement / FIRE (F20) ────────────────────────────────────────────────────

RETIREMENT_FIELDS = ("age", "retire_at", "horizon", "wealth", "yearly_saving", "expenses", "pension", "expected_return",
                     "volatility", "inflation", "withdrawal_rate")


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
