"""
The dashboard's choices, saved for every visit (in app_settings, not in the browser):
- the forecast the top cards show under the figure (closing of this month, next month, next 12 months, none);
- the blocks below the cards: their order, their width (a third, two thirds or the whole row: never more than
  three per row) and whether they are hidden from the page. Settings → Dashboard lists them in the same order;
- three presets, each with the blocks, the cards and the period of the page.
The cards that add up money (income, expenses, savings rate) follow the period of the page.
"""
from __future__ import annotations

from datetime import date

from flask_babel import gettext as _

from app.services import settings_store
from app.services.i18n import _l

# The top cards that add up money over the period of the page
WINDOW_CARDS = ("income", "expenses", "savings_rate")


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
    "recent":        (_l("Ultime transazioni"), 2, "dashboard_recent_tx"),
    "health":        (_l("Salute finanziaria"), 1, "dashboard_health"),
    # F48 (D13): the investments in short, next to the full overview in the Portfolio
    "investments":       (_l("Investimenti in breve"), 1, "dashboard_portfolio_blocks"),
    "investments_trend": (_l("Investimenti: valore e versato"), 2, "dashboard_portfolio_blocks"),
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
    "tbd2":         _l("Nuova scheda 2"),
    "tbd3":         _l("Nuova scheda 3"),
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


# ── Presets: three named arrangements of the page ─────────────────────────────

# Each preset keeps the blocks and the cards (order, width, height, hidden) and the period of the page (from one
# year to another, a half or a quarter). One is in use: a click on another one brings its arrangement and period;
# what changes afterwards is saved on the preset in use only when asked («Salva preset»).
PRESETS_SETTING = "dashboard.presets"
PRESET_COUNT = 3
MAX_PRESET_NAME = 30
PERIOD_PARTS = ("year", "H1", "H2", "Q1", "Q2", "Q3", "Q4")


def _clean_period(period) -> dict | None:
    """{"year", "year_to", "part"} as saved; None: the current year, whole."""
    if not isinstance(period, dict):
        return None
    try:
        year, year_to = int(period.get("year")), int(period.get("year_to", period.get("year")))
    except (TypeError, ValueError):
        return None
    if not (1900 < year < 3000 and 1900 < year_to < 3000):
        return None
    year, year_to = min(year, year_to), max(year, year_to)
    part = period.get("part")
    return {"year": year, "year_to": year_to, "part": part if part in PERIOD_PARTS and year == year_to else "year"}


def _default_name(number: int) -> str:
    return _("Preset %(num)d", num=number)


def _clean_preset(item, number: int) -> dict:
    item = item if isinstance(item, dict) else {}
    name = str(item.get("name") or "").strip()[:MAX_PRESET_NAME]
    return {"name": name or _default_name(number), "layout": normalize_layout(item.get("layout")),
            "kpis": normalize_kpis(item.get("kpis")), "period": _clean_period(item.get("period"))}


def presets() -> dict:
    """{"active": 1..3, "items": [three presets]}. The first time, the first preset is the page as it is now and
    the other two the default arrangement, so nothing the user had arranged is lost."""
    saved = settings_store.get_json(PRESETS_SETTING, None, expect=dict)
    if saved is None:
        first = {"layout": layout(), "kpis": kpi_layout()}
        return _store_presets({"active": 1, "items": [_clean_preset(first if n == 1 else None, n) for n in range(1, PRESET_COUNT + 1)]})
    items = saved.get("items") if isinstance(saved.get("items"), list) else []
    items = [_clean_preset(items[n - 1] if n <= len(items) else None, n) for n in range(1, PRESET_COUNT + 1)]
    active = saved.get("active")
    return {"active": active if active in range(1, PRESET_COUNT + 1) else 1, "items": items}


def _store_presets(data: dict) -> dict:
    settings_store.set_json(PRESETS_SETTING, data)
    return data


def _number(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    if not 1 <= number <= PRESET_COUNT:
        raise ValueError(_("Preset sconosciuto."))
    return number


def use_preset(number) -> dict:
    """Make a preset the one in use: its blocks and cards become those of the page. Returns the preset."""
    number = _number(number)
    data = presets()
    data["active"] = number
    preset = data["items"][number - 1]
    save_layout(preset["layout"])
    save_kpis(preset["kpis"])
    _store_presets(data)
    return preset


def save_preset(number, period) -> dict:
    """The page as it is now (blocks, cards and the period shown) saved on a preset, which becomes the one in use."""
    number = _number(number)
    data = presets()
    data["active"] = number
    item = data["items"][number - 1]
    item.update(layout=layout(), kpis=kpi_layout(), period=_clean_period(period))
    _store_presets(data)
    return item


def rename_preset(number, name) -> dict:
    number = _number(number)
    data = presets()
    item = data["items"][number - 1]
    item["name"] = str(name or "").strip()[:MAX_PRESET_NAME] or _default_name(number)
    _store_presets(data)
    return item


def preset_period(preset: dict, today: date | None = None) -> dict:
    """The period a preset shows: the one saved on it, else the current year, whole."""
    year = (today or date.today()).year
    return preset["period"] or {"year": year, "year_to": year, "part": "year"}


def preset_changed(preset: dict, period: dict, today: date | None = None) -> bool:
    """Whether the page differs from the preset in use: blocks, cards or period."""
    return (preset["layout"] != layout() or preset["kpis"] != kpi_layout()
            or preset_period(preset, today) != _clean_period(period))
