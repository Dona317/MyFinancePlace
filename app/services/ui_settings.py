"""
The interface choices saved from Settings (one JSON row in app_settings): which dashboard cards, sections and
modules are on, display preferences, the interface language. Services read them through `current_settings`.
"""

from flask import has_request_context, session

from app.extensions import db
from app.services import settings_store

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
    "dashboard_income_pie":     True,
    "dashboard_category_trends": True,
    "dashboard_cumulative":     True,
    "dashboard_net":            True,
    "dashboard_savings_trend":  True,
    "dashboard_sankey":         True,
    "dashboard_recent_tx":      True,
    "dashboard_health":         True,
    "autonomy_target":          "6",   # months of spending the liquid money should cover (Salute Finanziaria)
    # ── Data from the internet ───────────────────────────────────────────
    "prices_online":            False,  # «Aggiorna da internet» in Portafoglio → Aggiorna prezzi (F5b)
    # ── Modules (sidebar visibility + route access) ──────────────────────
    "module_portfolio":         True,
    "module_debt":              True,
    "module_insurance":         True,
    "module_documents":         True,
    "module_snapshots":         True,
    "module_export":            True,
    "module_tax":               True,
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
    "language":    "it",
}

LANGUAGES = {"it": "Italiano", "en": "English"}  # interface languages (translations/<code>/LC_MESSAGES)
AUTONOMY_TARGETS = (3, 6, 9, 12)


def autonomy_target() -> int:
    value = current_settings()["autonomy_target"]
    return int(value) if value.isdigit() and int(value) in AUTONOMY_TARGETS else 6


# Which setting switches off which pages: a whole blueprint, or single endpoints inside one
MODULE_BLUEPRINTS = {
    "portfolio": "module_portfolio", "debt": "module_debt", "insurance": "module_insurance",
    "documents": "module_documents", "snapshots": "module_snapshots", "export": "module_export",
    "tax": "module_tax",
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
    saved = settings_store.get_json(SETTINGS_KEY, expect=dict)
    if settings_store.get(SETTINGS_KEY) is None:  # nothing saved yet: choices of older versions, kept in the session
        saved = session.get("settings") if has_request_context() else None
    if not isinstance(saved, dict):
        saved = {}
    for key, default in DEFAULT_SETTINGS.items():
        if key in saved and isinstance(saved[key], type(default)):
            current[key] = saved[key]
    return current


def current_language() -> str:
    """The interface language chosen in Settings (Italian unless English was chosen)."""
    try:
        language = current_settings().get("language")
    except Exception:  # noqa: BLE001 - no database yet (e.g. `flask db upgrade` on a fresh one): the source language
        db.session.rollback()
        return "it"
    return language if language in LANGUAGES else "it"
