from flask import Blueprint, render_template, request, redirect, url_for, flash, session

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")

# Default values for every toggle — all sections enabled out of the box
DEFAULT_SETTINGS = {
    # ── Dashboard KPI cards ──────────────────────────────────────────────
    "dashboard_net_worth":      True,
    "dashboard_income":         True,
    "dashboard_expenses":       True,
    "dashboard_savings_rate":   True,
    "dashboard_investments":    True,
    "dashboard_debt":           True,
    # ── Dashboard sections ───────────────────────────────────────────────
    "dashboard_cashflow_chart": True,
    "dashboard_expense_pie":    True,
    "dashboard_recent_tx":      True,
    "dashboard_health":         True,
    # ── Modules (sidebar visibility + route access) ──────────────────────
    "module_portfolio":         True,
    "module_debt":              True,
    "module_insurance":         True,
    "module_documents":         True,
    "module_snapshots":         True,
    "module_export":            True,
    # ── Accounting sub-sections ──────────────────────────────────────────
    "accounting_balance_sheet":     True,
    "accounting_income_statement":  True,
    "accounting_cash_flow":         True,
    # ── Lifestyle sub-sections ───────────────────────────────────────────
    "lifestyle_goals":          True,
    # ── Display preferences ──────────────────────────────────────────────
    "currency":    "EUR",
    "locale":      "it-IT",
    "date_format": "DD/MM/YYYY",
}


@settings_bp.route("/")
def index():
    # TODO: load user-specific settings from DB; fall back to defaults
    current = {**DEFAULT_SETTINGS}
    return render_template("settings/index.html", settings=current, defaults=DEFAULT_SETTINGS)


@settings_bp.route("/save", methods=["POST"])
def save():
    # TODO: persist settings to DB for the current user
    # For now, store in session as a lightweight demo
    form = request.form
    new_settings = {}
    for key in DEFAULT_SETTINGS:
        if isinstance(DEFAULT_SETTINGS[key], bool):
            new_settings[key] = key in form  # checkbox is present only when checked
        else:
            new_settings[key] = form.get(key, DEFAULT_SETTINGS[key])
    session["settings"] = new_settings
    flash("Impostazioni salvate con successo.", "success")
    return redirect(url_for("settings.index"))


@settings_bp.route("/reset", methods=["POST"])
def reset():
    # TODO: reset to defaults in DB
    session.pop("settings", None)
    flash("Impostazioni ripristinate ai valori predefiniti.", "success")
    return redirect(url_for("settings.index"))
