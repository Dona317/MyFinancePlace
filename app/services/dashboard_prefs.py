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
    # «Come sto»
    "health":        (_l("Salute finanziaria"), 2, "dashboard_health"),
    "to_fix":        (_l("Da sistemare"), 1, "dashboard_health"),
    # «Questo mese»
    "pace":          (_l("Ritmo di spesa"), 2, "dashboard_month_charts"),
    "bridge":        (_l("Bridge del mese"), 1, "dashboard_month_charts"),
    "next_days":     (_l("Prossimi 30 giorni"), 1, "dashboard_month_charts"),
    "budget_top":    (_l("Budget più vicini al limite"), 1, "dashboard_month_charts"),
    # where the money goes: the map of the expenses (tiles as big as each category); the flow from the income to the
    # expenses (Sankey) is a block of its own
    "money_map":     (_l("Dove va il denaro"), 1, "dashboard_sankey"),
    "sankey":        (_l("Flusso del denaro"), 2, "dashboard_sankey"),
    "expense_pie":   (_l("Uscite per categoria"), 1, "dashboard_expense_pie"),
    "income_pie":    (_l("Entrate per categoria"), 1, "dashboard_income_pie"),
    "year_total":    (_l("Totale del periodo"), 1, "dashboard_net"),
    # what the old cards on top showed: income, expenses and savings rate of the period (with the forecast and the
    # comparison), and the debts — in the views «Questo mese» and «Patrimonio»
    "period_totals": (_l("Entrate e uscite del periodo"), 3, "dashboard_net"),
    # the month under way only (22 Nov 2026): the first block of «Questo mese», against last month and the average
    "month_totals":  (_l("Entrate e uscite del mese"), 3, "dashboard_net"),
    "debt_summary":  (_l("Debiti"), 1, "dashboard_net_worth_trend"),
    # «Nel tempo»
    "net_worth":     (_l("Andamento del patrimonio"), 1, "dashboard_net_worth_trend"),
    "net_worth_bridge": (_l("Variazione del patrimonio"), 1, "dashboard_net_worth_trend"),
    "cashflow":      (_l("Flusso di cassa e risparmio"), 2, "dashboard_cashflow_chart"),
    "savings_trend": (_l("Tasso di risparmio mese per mese"), 1, "dashboard_savings_trend"),
    "expense_trend": (_l("Uscite per categoria nel tempo"), 2, "dashboard_category_trends"),
    "income_trend":  (_l("Entrate per categoria nel tempo"), 2, "dashboard_category_trends"),
    # F48 (D13): the investments in short, next to the full overview in the Portfolio
    "investments":       (_l("Investimenti in breve"), 1, "dashboard_portfolio_blocks"),
    "investments_trend": (_l("Investimenti: valore e versato"), 1, "dashboard_portfolio_blocks"),
    "drawdown":      (_l("Calo dal massimo"), 1, "dashboard_portfolio_blocks"),
    # «Futuro»
    "future_balance": (_l("Saldo dei prossimi 12 mesi"), 2, "dashboard_future"),
    "big_expenses":  (_l("Uscite grosse dei prossimi 12 mesi"), 1, "dashboard_future"),
    "future_net_worth": (_l("Patrimonio tra 10 anni"), 2, "dashboard_future"),
    "fire":          (_l("Pensione e indipendenza finanziaria"), 1, "dashboard_future"),
    "goals_eta":     (_l("Obiettivi: quando ci arrivo"), 1, "dashboard_future"),
    "debt_payoff":   (_l("Debiti: quando finisco"), 1, "dashboard_future"),
    "future_income": (_l("Rendite dei prossimi 12 mesi"), 1, "dashboard_future"),
}
# UI-18: the bands of the page, from the most urgent to the slowest; «Nel tempo» and «Futuro» closed at first
BANDS = {
    # 22 Nov 2026: income and expenses of the period right under the cards of «Come sto»; «Nel tempo» and «Futuro»
    # open (UI-25: they started closed, and nobody opened them)
    "now":    (_l("Come sto"), ("period_totals", "health", "to_fix"), True),
    # 22 Nov 2026: the flow of the money (Sankey) of the month, shown from the start, two columns by two rows
    "month":  (_l("Questo mese"), ("month_totals", "pace", "bridge", "money_map", "budget_top", "next_days", "sankey",
                                    "expense_pie", "income_pie", "year_total"), True),
    "time":   (_l("Nel tempo"), ("cashflow", "net_worth", "investments_trend", "savings_trend", "net_worth_bridge",
                                  "expense_trend", "income_trend", "investments", "debt_summary", "drawdown"), True),
    "future": (_l("Futuro"), ("future_balance", "big_expenses", "future_net_worth", "fire", "goals_eta",
                               "debt_payoff", "future_income"), True),
}
BAND_OF = {widget: band for band, (_title, members, _open) in BANDS.items() for widget in members}

LAYOUT_SETTING = "dashboard.layout"
SPANS = (1, 2, 3)
HEIGHTS = (0, 1, 2, 3)  # 0: as tall as its content (and its row); 1–3: medium, tall, very tall


# Hidden at first (Modifica shows them again): what the sketch of 18 Nov leaves out of the page — «Come sto» is the
# row of cards on top, the doughnuts and the older charts are a click away.
DEFAULT_HIDDEN = {"health", "to_fix", "month_totals", "debt_summary", "expense_pie", "income_pie", "year_total",
                  "expense_trend", "income_trend", "investments", "drawdown"}
# Blocks shown again once on an arrangement saved before (22 Nov 2026: income and expenses of the period, and the
# cash-flow chart, were hidden); hidden afterwards in Modifica, they stay hidden
REVEALED = ("period_totals", "cashflow", "sankey", "sankey-2x2")
# a step of REVEALED that also gives a block its size: «sankey-2x2» = the Sankey two columns wide and two rows tall
REVEALED_SHAPES = {"sankey-2x2": ("sankey", {"span": 2, "height": 2})}
DEFAULT_HEIGHTS = {"sankey": 2}
REVEALED_SETTING = "dashboard.revealed"
UI_SETTINGS_KEY = "ui.settings"  # ui_settings.SETTINGS_KEY (not imported: ui_settings reads this module)


def default_layout() -> list[dict]:
    """Band by band (BANDS), in the sketch's order and widths."""
    return [{"id": key, "span": WIDGETS[key][1], "height": DEFAULT_HEIGHTS.get(key, 0), "visible": key not in DEFAULT_HIDDEN}
            for _title, members, _open in BANDS.values() for key in members]


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
    _mark_current()  # arranged on the new page: no upgrade over it
    return items


def reset_layout() -> list[dict]:
    settings_store.set(LAYOUT_SETTING, None)
    settings_store.set(KPI_SETTING, None)
    return default_layout()


# The cards on top: their order, width (one or two columns) and whether they are shown. "tbd" keeps a place for
# what comes next.
KPI_CARDS = {
    # UI-18: «Come sto» — net worth, the month's saving, the months the cash covers, what to fix. The old cards
    # (income, expenses, savings rate of the period, investments, debts) are blocks of the views now.
    "net_worth":     _l("Patrimonio netto"),
    "month_savings": _l("Risparmio del mese"),
    "liquidity":     _l("Liquidità"),
    "to_fix":        _l("Da sistemare"),
}
KPI_SETTING = "dashboard.kpis"
KPI_SPANS = (1, 2)



def default_kpis() -> list[dict]:
    """The four cards of «Come sto» shown, the net worth two columns wide; the others hidden (Modifica shows them)."""
    return [{"id": key, "span": 2 if key == "net_worth" else 1, "visible": True} for key in KPI_CARDS]


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
    _mark_current()
    return items


# The views of the page (the tabs on top): «Panoramica» is the page in bands, as arranged in Modifica; the others
# show their own blocks, in this order and width, whatever is hidden in the overview.
VIEWS = {
    "overview":    (_l("Panoramica"), "grid-1x2", ()),
    "month":       (_l("Questo mese"), "calendar-month", (("month_totals", 3), ("pace", 2), ("bridge", 1),
                    ("money_map", 1), ("budget_top", 1), ("next_days", 1), ("sankey", 2), ("expense_pie", 1), ("income_pie", 1),
                    ("year_total", 1), ("cashflow", 3), ("expense_trend", 3))),
    "wealth":      (_l("Patrimonio"), "bank", (("net_worth", 3), ("net_worth_bridge", 1), ("health", 1),
                    ("debt_summary", 1), ("debt_payoff", 1), ("future_net_worth", 2), ("big_expenses", 1))),
    "investments": (_l("Investimenti"), "briefcase", (("investments", 1), ("investments_trend", 2), ("drawdown", 1),
                    ("future_income", 1), ("fire", 1))),
}


VIEW_SETTING = "dashboard.view.%s"


def default_view_layout(view: str) -> list[dict]:
    return [{"id": key, "span": span, "height": 0, "visible": True} for key, span in VIEWS[view][2]]


def _normalize_view(view: str, items) -> list[dict]:
    """The view's own blocks once each, in the given order (width 1–3, height 0–3, shown or hidden); its blocks
    missing from it at the end, as in the view's default; other blocks dropped."""
    own = {key for key, _span in VIEWS[view][2]}
    kept = [w for w in normalize_layout(items) if w["id"] in own]
    given = {item.get("id") for item in items if isinstance(item, dict)} if isinstance(items, list) else set()
    out = [w for w in kept if w["id"] in given]
    return out + [w for w in default_view_layout(view) if w["id"] not in {x["id"] for x in out}]


def view_layout(view: str) -> list[dict]:
    """A view's blocks as arranged in its Modifica (the default the first time)."""
    return _normalize_view(view, settings_store.get_json(VIEW_SETTING % view, [], expect=list))


def save_view_layout(view: str, items) -> list[dict]:
    items = _normalize_view(view, items)
    settings_store.set_json(VIEW_SETTING % view, items)
    return items


def reset_view_layout(view: str) -> list[dict]:
    settings_store.set(VIEW_SETTING % view, None)
    return default_view_layout(view)


LAYOUT_VERSION = 3  # 2: the dashboard in bands (UI-18, 20 Nov 2026); 3: the cards of «Come sto», map and flow apart
VERSION_SETTING = "dashboard.layout_version"


def _mark_current() -> None:
    settings_store.set(VERSION_SETTING, str(LAYOUT_VERSION))


def upgrade() -> bool:
    """An arrangement saved before the bands goes to the new page once: blocks, cards and the presets' blocks and
    cards (their names and periods stay). True when it did."""
    try:
        version = int(settings_store.get(VERSION_SETTING, 0) or 0)
    except (TypeError, ValueError):
        version = 0
    if version >= LAYOUT_VERSION:
        return False
    settings_store.set(LAYOUT_SETTING, None)
    settings_store.set(KPI_SETTING, None)
    saved = settings_store.get_json(PRESETS_SETTING, None, expect=dict)
    if saved and isinstance(saved.get("items"), list):
        for item in saved["items"]:
            if isinstance(item, dict):
                item["layout"], item["kpis"] = default_layout(), default_kpis()
        settings_store.set_json(PRESETS_SETTING, saved)
    settings_store.set(VERSION_SETTING, str(LAYOUT_VERSION))
    return True


def reveal() -> list[str]:
    """The blocks of REVEALED shown once on an arrangement saved before them (the layout and the presets' layouts);
    returns those made visible now. The ones the user hides afterwards stay hidden."""
    done = set(settings_store.get_json(REVEALED_SETTING, [], expect=list))
    todo = [key for key in REVEALED if key not in done]
    if not todo:
        return []
    changes: dict[str, dict] = {}
    for key in todo:
        block, shape = REVEALED_SHAPES.get(key, (key, {}))
        changes.setdefault(block, {"visible": True}).update(shape)

    def apply(items) -> None:
        for item in items or []:
            if isinstance(item, dict) and item.get("id") in changes:
                item.update(changes[item["id"]])

    saved = settings_store.get_json(LAYOUT_SETTING, None, expect=list)
    if saved:
        apply(saved)
        settings_store.set_json(LAYOUT_SETTING, saved)
    presets_saved = settings_store.get_json(PRESETS_SETTING, None, expect=dict)
    if presets_saved and isinstance(presets_saved.get("items"), list):
        for preset in presets_saved["items"]:
            apply(preset.get("layout") if isinstance(preset, dict) else None)
        settings_store.set_json(PRESETS_SETTING, presets_saved)
    if "sankey" in changes:  # its switch in Impostazioni → Dashboard, on again with it
        ui = settings_store.get_json(UI_SETTINGS_KEY, None, expect=dict)
        if isinstance(ui, dict) and ui.get("dashboard_sankey") is False:
            settings_store.set_json(UI_SETTINGS_KEY, {**ui, "dashboard_sankey": True})
    settings_store.set_json(REVEALED_SETTING, sorted(done | set(todo)))
    return todo


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
# F101: a preset keeps the shared period, whatever its kind (a half, a quarter, a month, the last 12 months)
PERIOD_PARTS = ("year", "H1", "H2", "Q1", "Q2", "Q3", "Q4", *(f"M{m:02d}" for m in range(1, 13)), "last12")


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
    if part == "last12":
        return {"year": year, "year_to": year, "part": part}
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
