"""The forecast page's choices: method, rolling window, horizon and recurring amounts, and which panels it shows."""
from app.services import settings_store
from app.services.i18n import _l

# ── Methods and preferences ────────────────────────────────────────────────────

METHODS = {
    "media":        (_l("Media mobile"), _l("Media semplice degli ultimi N mesi.")),
    "ponderata":    (_l("Media ponderata"), _l("Media degli ultimi N mesi con più peso ai mesi recenti (pesi 1, 2, … N).")),
    "esponenziale": (_l("Media esponenziale"), _l("Livellamento esponenziale con α = 2 / (N + 1): segue i cambiamenti più in fretta.")),
    "mediana":      (_l("Mediana"), _l("Valore centrale degli ultimi N mesi: ignora i mesi eccezionali (una spesa una tantum).")),
    "trend":        (_l("Trend lineare"), _l("Retta di regressione sugli ultimi N mesi, proiettata in avanti: coglie spese in crescita o in calo.")),
    "stagionale":   (_l("Stagionale"), _l("Lo stesso mese dell'anno prima, riscalato sul livello degli ultimi N mesi: coglie bollette "
                                   "invernali, vacanze estive, tredicesima. Serve almeno un anno di storico.")),
}
# Amount of each recurring series in the forecast (salary with overtime, bills that change)
RECURRING_AMOUNTS = {
    "media":  (_l("Media della finestra"), _l("Media degli importi della serie negli ultimi N mesi, come per le variabili.")),
    "ultimo": (_l("Ultimo importo"), _l("L'importo dell'ultima transazione della serie: segue subito un aumento o un rinnovo.")),
}
DEFAULT_RECURRING = "media"
DEFAULT_METHOD = "media"
DEFAULT_WINDOW = 6
DEFAULT_HORIZON = 12
WINDOW_RANGE = (1, 36)
HORIZON_RANGE = (1, 24)
LAYOUT_SETTING = "forecast.layout"


def _clamp(value, low, high, default):
    try:
        return min(max(int(value), low), high)
    except (TypeError, ValueError):
        return default


def preferences(method=None, window=None, horizon=None, recurring=None) -> dict:
    """The given values if valid, else the saved ones, else the defaults."""
    method = method if method in METHODS else settings_store.get("forecast.method", DEFAULT_METHOD)
    recurring = recurring if recurring in RECURRING_AMOUNTS else settings_store.get("forecast.recurring", DEFAULT_RECURRING)
    return {
        "method": method if method in METHODS else DEFAULT_METHOD,
        "recurring": recurring if recurring in RECURRING_AMOUNTS else DEFAULT_RECURRING,
        "window": _clamp(window if window not in (None, "") else settings_store.get("forecast.window"), *WINDOW_RANGE, DEFAULT_WINDOW),
        "horizon": _clamp(horizon if horizon not in (None, "") else settings_store.get("forecast.horizon"), *HORIZON_RANGE, DEFAULT_HORIZON),
    }


def save_preferences(method=None, window=None, horizon=None, recurring=None) -> dict:
    prefs = preferences(method, window, horizon, recurring)
    for key, value in prefs.items():
        settings_store.set(f"forecast.{key}", str(value))
    return prefs


# ── Page layout: which panels, in which order, half or whole row ──────────────

WIDGETS = {  # id: (title, default span: 1 = half row, 2 = whole row)
    "kpi":        (_l("Indicatori"), 2),
    "net":        (_l("Netto mensile"), 1),
    "methods":    (_l("Confronto dei metodi"), 1),
    "income":     (_l("Entrate"), 1),
    "expenses":   (_l("Uscite"), 1),
    "balance":    (_l("Saldo di cassa previsto"), 1),
    "months":     (_l("Mese per mese"), 1),
    "categories": (_l("Previsione per categoria"), 1),
    "upcoming":   (_l("Prossime ricorrenti"), 1),
    "candidates": (_l("Sembrano ricorrenti"), 1),
    "stability":  (_l("Stabilità delle entrate"), 1),
    "help":       (_l("Come funziona"), 1),
}


def default_layout() -> list[dict]:
    return [{"id": key, "span": span, "visible": True} for key, (_, span) in WIDGETS.items()]


def normalize_layout(items) -> list[dict]:
    """Keep known panels once each, in the given order; panels missing from it are added at the end."""
    out, seen = [], set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or item.get("id") not in WIDGETS or item["id"] in seen:
            continue
        seen.add(item["id"])
        out.append({"id": item["id"], "span": 2 if str(item.get("span")) == "2" else 1,
                    "visible": item.get("visible", True) is not False})
    return out + [w for w in default_layout() if w["id"] not in seen]


def layout() -> list[dict]:
    return normalize_layout(settings_store.get_json(LAYOUT_SETTING, [], expect=list))


def save_layout(items) -> list[dict]:
    items = normalize_layout(items)
    settings_store.set_json(LAYOUT_SETTING, items)
    return items


def reset_layout() -> list[dict]:
    settings_store.set(LAYOUT_SETTING, None)
    return default_layout()
