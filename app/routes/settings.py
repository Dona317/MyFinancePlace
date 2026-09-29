import json
import re

from flask import render_template, request, redirect, url_for, flash, session, jsonify, has_request_context
from apiflask import APIBlueprint

from app.services import ai_classification, ai_extraction, ai_models, settings_store

settings_bp = APIBlueprint(
    "settings",
    __name__,
    url_prefix="/settings",
    tag="Settings"
)

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


# Which setting switches off which pages: a whole blueprint, or single endpoints inside one
MODULE_BLUEPRINTS = {
    "portfolio": "module_portfolio", "debt": "module_debt", "insurance": "module_insurance",
    "documents": "module_documents", "snapshots": "module_snapshots", "export": "module_export",
}
MODULE_ENDPOINTS = {
    "accounting.balance_sheet": "accounting_balance_sheet", "accounting.opening_cash": "accounting_balance_sheet",
    "accounting.income_statement": "accounting_income_statement", "accounting.cash_flow": "accounting_cash_flow",
}
MODULE_ENDPOINT_PREFIXES = {"lifestyle.goal": "lifestyle_goals"}  # lifestyle.goals, lifestyle.goal_new, ...


def module_setting(blueprint: str | None, endpoint: str | None) -> str | None:
    """The setting that must be on for this page to be reachable (None: always reachable)."""
    if blueprint in MODULE_BLUEPRINTS:
        return MODULE_BLUEPRINTS[blueprint]
    if endpoint in MODULE_ENDPOINTS:
        return MODULE_ENDPOINTS[endpoint]
    return next((key for prefix, key in MODULE_ENDPOINT_PREFIXES.items() if (endpoint or "").startswith(prefix)), None)


SETTINGS_KEY = "ui.settings"  # the saved choices, as JSON in app_settings (so they survive cookies and browsers)


def current_settings() -> dict:
    """Defaults, overridden by the saved choices; unknown keys and values of the wrong type are ignored."""
    current = {**DEFAULT_SETTINGS}
    raw = settings_store.get(SETTINGS_KEY)
    try:
        # nothing saved yet: choices made with older versions, which kept them in the browser session
        saved = json.loads(raw) if raw else (session.get("settings") if has_request_context() else None) or {}
    except (ValueError, TypeError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    for key, default in DEFAULT_SETTINGS.items():
        if key in saved and isinstance(saved[key], type(default)):
            current[key] = saved[key]
    return current


@settings_bp.route("/")
def index():
    return render_template("settings/index.html", settings=current_settings(), defaults=DEFAULT_SETTINGS)


@settings_bp.route("/save", methods=["POST"])
def save():
    form = request.form
    new_settings = {}
    for key, default in DEFAULT_SETTINGS.items():
        if isinstance(default, bool):
            new_settings[key] = key in form  # checkbox is present only when checked
        else:
            new_settings[key] = (form.get(key) or default).strip()
    settings_store.set(SETTINGS_KEY, json.dumps(new_settings))
    session.pop("settings", None)  # older versions kept them in the browser session
    flash("Impostazioni salvate con successo.", "success")
    return redirect(url_for("settings.index"))


@settings_bp.route("/reset", methods=["POST"])
def reset():
    settings_store.set(SETTINGS_KEY, None)
    session.pop("settings", None)
    flash("Impostazioni ripristinate ai valori predefiniti.", "success")
    return redirect(url_for("settings.index"))


# ── AI models (Ollama / Anthropic) ─────────────────────────────────────────────

MODEL_NAME = re.compile(r"^[a-z0-9][a-z0-9._\-/]*(:[a-z0-9._\-]+)?$", re.IGNORECASE)


def _valid_model_name(name: str) -> bool:
    return bool(name) and len(name) <= 100 and bool(MODEL_NAME.match(name))


@settings_bp.route("/ai")
def ai_models_page():
    ollama = ai_models.status(ai_extraction.base_url())
    catalog = {tier: [m for m in ai_models.CATALOG if m.tier == tier] for tier in ai_models.TIERS}
    extra_installed = sorted(set(ollama["installed"]) - set(ai_models.BY_NAME))
    return render_template(
        "settings/ai.html",
        provider=ai_extraction.provider(),
        model=ai_extraction.model_name(),
        models_by_provider={p: ai_extraction.model_for(p) for p in ai_extraction.DEFAULT_MODELS},
        classify_by_provider={p: settings_store.get(ai_classification.classify_setting(p)) or ""
                              for p in ai_extraction.DEFAULT_MODELS},
        ollama=ollama,
        ollama_url=ai_extraction.base_url(),
        catalog=catalog,
        tiers=ai_models.TIERS,
        extra_installed=extra_installed,
        pulls=ai_models.pull_progress(),
        is_vision=ai_models.is_vision,
        anthropic_models=ai_extraction.ANTHROPIC_MODELS,
    )


@settings_bp.route("/ai/save", methods=["POST"])
def ai_save():
    provider = request.form.get("provider", "none")
    model = (request.form.get("model") or "").strip()
    classify_model = (request.form.get("classify_model") or "").strip()
    if provider != "none" and provider not in ai_extraction.DEFAULT_MODELS:
        flash("Provider non valido.", "error")
        return redirect(url_for("settings.ai_models_page"))
    for name in (model, classify_model):
        if name and not _valid_model_name(name):
            flash("Nome del modello non valido.", "error")
            return redirect(url_for("settings.ai_models_page"))
        if provider != "none" and name and not ai_extraction.model_matches_provider(provider, name):
            which = "un modello Claude (es. claude-haiku-4-5)" if provider == "anthropic" else "un modello Ollama (es. qwen2.5vl:7b)"
            flash(f"{name} non è un modello per questo provider: scegli {which}.", "error")
            return redirect(url_for("settings.ai_models_page"))
    settings_store.set(ai_extraction.PROVIDER_SETTING, provider)
    if provider != "none" and model:  # empty field: keep this provider's previous choice
        settings_store.set(ai_extraction.model_setting(provider), model)
    if provider != "none" and "classify_model" in request.form:
        # empty = classify with the same model that reads documents
        settings_store.set(ai_classification.classify_setting(provider), classify_model or None)
    if provider == "none":
        flash("Lettura AI disattivata.", "success")
    else:
        flash(f"Lettura AI attiva: {ai_extraction.describe()}.", "success")
    return redirect(url_for("settings.ai_models_page"))


@settings_bp.route("/ai/pull", methods=["POST"])
def ai_pull():
    name = (request.form.get("name") or "").strip()
    if not _valid_model_name(name):
        flash("Nome del modello non valido.", "error")
    elif ai_models.start_pull(ai_extraction.base_url(), name):
        flash(f"Download di {name} avviato: puoi seguire l'avanzamento qui sotto.", "success")
    else:
        flash(f"Il download di {name} è già in corso.", "warning")
    return redirect(url_for("settings.ai_models_page"))


@settings_bp.route("/ai/pull-status")
def ai_pull_status():
    return jsonify(ai_models.pull_progress())


@settings_bp.route("/ai/delete", methods=["POST"])
def ai_delete():
    name = (request.form.get("name") or "").strip()
    if not _valid_model_name(name):
        flash("Nome del modello non valido.", "error")
        return redirect(url_for("settings.ai_models_page"))
    try:
        ai_models.delete(ai_extraction.base_url(), name)
        flash(f"Modello {name} rimosso.", "success")
    except ai_models.OllamaError as exc:
        flash(str(exc), "error")
    return redirect(url_for("settings.ai_models_page"))
