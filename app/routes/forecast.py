from datetime import date

from apiflask import APIBlueprint
from flask import flash, jsonify, redirect, render_template, request, url_for

from app.extensions import db
from app.models.transaction import Transaction
from app.services import forecast

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
    return render_template(
        "forecast/index.html",
        fc=result, prefs=prefs, methods=forecast.METHODS, frequencies=forecast.FREQUENCIES,
        recurring_amounts=forecast.RECURRING_AMOUNTS, layout=forecast.layout(), widgets=forecast.WIDGETS,
        window_range=forecast.WINDOW_RANGE, horizon_range=forecast.HORIZON_RANGE,
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
        flash("Frequenza non valida.", "error")
        return redirect(url_for("forecast.index"))
    tx.is_recurring, tx.recurrence = True, frequency
    db.session.commit()
    flash(f"«{tx.description}» è ora una transazione ricorrente ({forecast.FREQUENCIES[frequency][0].lower()}).", "success")
    return redirect(url_for("forecast.index"))
