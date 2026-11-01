"""
The dashboard's choices, saved for every visit (in app_settings, not in the browser):
- the time window of each top card that adds up money over a period (income, expenses, savings rate): a preset
  («questo mese», «ultimi 3 mesi», …), the last N months the user types, or two dates; a default for all of them;
- the forecast the same cards show under the figure (closing of this month, next month, next 12 months, none);
- the blocks below the cards: their order, their width (a third, two thirds or the whole row: never more than
  three per row) and whether they are hidden from the page. Settings → Dashboard lists them in the same order.
"""
from __future__ import annotations

from datetime import date, timedelta

from flask_babel import gettext as _
from flask_babel import ngettext

from app.services import display, reports, settings_store
from app.services.i18n import _l
from app.services.periods import month_index, month_start

# ── Time windows of the top cards ──────────────────────────────────────────────

PRESETS = ("this_month", "last_month", "last_3", "last_6", "last_12", "this_year", "last_year")
WINDOW_CARDS = ("income", "expenses", "savings_rate")
DEFAULT_WINDOW = {"period": "this_month"}
MAX_MONTHS = 120
WINDOWS_SETTING = "dashboard.windows"
DEFAULT_WINDOW_SETTING = "dashboard.default_window"


def _clean(window) -> dict | None:
    """A window as saved: {"period": preset} | {"period": "last_n", "n": 1..120} | {"period": "custom", "start", "end"}."""
    if not isinstance(window, dict):
        return None
    period = window.get("period")
    if period in PRESETS:
        return {"period": period}
    if period == "last_n":
        try:
            n = int(window.get("n"))
        except (TypeError, ValueError):
            return None
        return {"period": "last_n", "n": n} if 1 <= n <= MAX_MONTHS else None
    if period == "custom":
        try:
            start, end = date.fromisoformat(str(window.get("start"))), date.fromisoformat(str(window.get("end")))
        except ValueError:
            return None
        start, end = min(start, end), max(start, end)
        return {"period": "custom", "start": start.isoformat(), "end": end.isoformat()}
    return None


def default_window() -> dict:
    return _clean(settings_store.get_json(DEFAULT_WINDOW_SETTING, expect=dict)) or dict(DEFAULT_WINDOW)


def set_default_window(window) -> dict:
    window = _clean(window) or dict(DEFAULT_WINDOW)
    settings_store.set_json(DEFAULT_WINDOW_SETTING, window)
    return window


def window(card: str) -> dict:
    """The window of a card: the one the user chose for it, else the default."""
    saved = settings_store.get_json(WINDOWS_SETTING, {}, expect=dict)
    return _clean(saved.get(card)) or default_window()


def save_window(card: str, value) -> dict:
    if card not in WINDOW_CARDS:
        raise ValueError(_("Scheda sconosciuta."))
    clean = _clean(value)
    if clean is None:
        raise ValueError(_("Finestra temporale non valida."))
    saved = settings_store.get_json(WINDOWS_SETTING, {}, expect=dict)
    saved[card] = clean
    settings_store.set_json(WINDOWS_SETTING, saved)
    return clean


def reset_windows() -> None:
    """Every card back to the default window («questo mese» unless the default was changed)."""
    settings_store.set(WINDOWS_SETTING, None)
    settings_store.set(DEFAULT_WINDOW_SETTING, None)


def window_range(value: dict, today: date | None = None) -> tuple[date, date]:
    """[first day, day after the last) of a window."""
    today = today or date.today()
    value = _clean(value) or dict(DEFAULT_WINDOW)
    if value["period"] == "last_n":
        current = month_index(today)
        return month_start(current - value["n"] + 1), month_start(current + 1)
    if value["period"] == "custom":
        return date.fromisoformat(value["start"]), date.fromisoformat(value["end"]) + timedelta(days=1)
    return reports.period_range(value["period"], today=today)


def window_label(value: dict) -> str:
    if value["period"] == "last_n":
        return ngettext("Ultimo mese", "Ultimi %(num)d mesi", value["n"])
    if value["period"] == "custom":
        return f"{display.day(date.fromisoformat(value['start']))} – {display.day(date.fromisoformat(value['end']))}"
    return str(reports.PERIODS[value["period"]])


def preset_choices() -> list[tuple[str, str]]:
    return [(key, str(reports.PERIODS[key])) for key in PRESETS]


# ── The forecast under the cards ──────────────────────────────────────────────

FORECASTS = {
    "next":    _l("Prossimo mese"),
    "current": _l("Chiusura del mese in corso"),
    "year":    _l("Prossimi 12 mesi"),
    "off":     _l("Nessuna previsione"),
}
DEFAULT_FORECAST = "next"
FORECAST_SETTING = "dashboard.forecast"
MIN_HISTORY = 3  # complete months of history before a forecast is worth showing


def forecast_choice() -> str:
    value = settings_store.get(FORECAST_SETTING, DEFAULT_FORECAST)
    return value if value in FORECASTS else DEFAULT_FORECAST


def save_forecast_choice(value: str) -> str:
    value = value if value in FORECASTS else DEFAULT_FORECAST
    settings_store.set(FORECAST_SETTING, value)
    return value


# ── The blocks below the cards ────────────────────────────────────────────────

# id: (title, default width in thirds of the row, the Settings switch that turns it on)
WIDGETS = {
    "cashflow":      (_l("Flusso di cassa e risparmio"), 3, "dashboard_cashflow_chart"),
    "net_worth":     (_l("Andamento del patrimonio"), 3, "dashboard_net_worth_trend"),
    "expense_pie":   (_l("Uscite per categoria"), 1, "dashboard_expense_pie"),
    "expense_trend": (_l("Uscite per categoria nel tempo"), 2, "dashboard_category_trends"),
    "income_pie":    (_l("Entrate per categoria"), 1, "dashboard_income_pie"),
    "income_trend":  (_l("Entrate per categoria nel tempo"), 2, "dashboard_category_trends"),
    "sankey":        (_l("Dove va il denaro"), 3, "dashboard_sankey"),
    "year_total":    (_l("Totale dell'anno"), 1, "dashboard_net"),
    "savings_trend": (_l("Tasso di risparmio mese per mese"), 2, "dashboard_savings_trend"),
    "recent":        (_l("Transazioni"), 2, "dashboard_recent_tx"),
    "health":        (_l("Salute finanziaria"), 1, "dashboard_health"),
}
LAYOUT_SETTING = "dashboard.layout"
SPANS = (1, 2, 3)
HEIGHTS = (0, 1, 2, 3)  # 0: as tall as its content (and its row); 1–3: medium, tall, very tall


def default_layout() -> list[dict]:
    return [{"id": key, "span": span, "height": 0, "visible": True} for key, (_title, span, _setting) in WIDGETS.items()]


def normalize_layout(items) -> list[dict]:
    """Known blocks once each, in the given order, width 1–3, height 0–3; blocks missing from it are added at the end."""
    out, seen = [], set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or item.get("id") not in WIDGETS or item["id"] in seen:
            continue
        seen.add(item["id"])
        try:
            span = int(item.get("span"))
        except (TypeError, ValueError):
            span = WIDGETS[item["id"]][1]
        height = item.get("height", 0)
        out.append({"id": item["id"], "span": span if span in SPANS else WIDGETS[item["id"]][1],
                    "height": height if height in HEIGHTS else 0, "visible": item.get("visible", True) is not False})
    return out + [w for w in default_layout() if w["id"] not in seen]


def layout() -> list[dict]:
    return normalize_layout(settings_store.get_json(LAYOUT_SETTING, [], expect=list))


def save_layout(items) -> list[dict]:
    items = normalize_layout(items)
    settings_store.set_json(LAYOUT_SETTING, items)
    return items


def reset_layout() -> list[dict]:
    settings_store.set(LAYOUT_SETTING, None)
    settings_store.set(KPI_SETTING, None)
    return default_layout()


# The cards on top: their order, width (one or two columns) and whether they are shown. "tbd" keeps a place for
# what comes next.
KPI_CARDS = {
    "net_worth":    _l("Patrimonio Netto"),
    "income":       _l("Entrate"),
    "expenses":     _l("Uscite"),
    "savings_rate": _l("Tasso di Risparmio"),
    "investments":  _l("Investimenti"),
    "debt":         _l("Debito Totale"),
    "tbd":          _l("Nuova scheda"),
}
KPI_SETTING = "dashboard.kpis"
KPI_SPANS = (1, 2)


def default_kpis() -> list[dict]:
    return [{"id": key, "span": 1, "visible": True} for key in KPI_CARDS]


def normalize_kpis(items) -> list[dict]:
    """Known cards once each, in the given order, width 1–2; cards missing from it are added at the end."""
    out, seen = [], set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or item.get("id") not in KPI_CARDS or item["id"] in seen:
            continue
        seen.add(item["id"])
        span = item.get("span", 1)
        out.append({"id": item["id"], "span": span if span in KPI_SPANS else 1, "visible": item.get("visible", True) is not False})
    return out + [k for k in default_kpis() if k["id"] not in seen]


def kpi_layout() -> list[dict]:
    return normalize_kpis(settings_store.get_json(KPI_SETTING, [], expect=list))


def save_kpis(items) -> list[dict]:
    items = normalize_kpis(items)
    settings_store.set_json(KPI_SETTING, items)
    return items


def settings_order() -> list[str]:
    """The Settings switches of the blocks, in the order of the dashboard (each switch once)."""
    return list(dict.fromkeys(WIDGETS[w["id"]][2] for w in layout()))
