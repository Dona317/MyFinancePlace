"""
Cash-flow forecast.

Each month's forecast adds up two parts:
- scheduled: transactions flagged "Transazione ricorrente", projected on their own dates with their
  frequency until their end date (the latest transaction of each series is the template), for the
  amount either the mean over the rolling window or the latest one;
- variable: everything else, per category, estimated from the last N complete months (the rolling
  window) with the method the user picks.
Both apply to incoming and outgoing flows alike, and the methods are measured on each flow.
Transfers between own accounts are left out: they don't change the balance.

The methods are also tried on the past (rolling-origin backtest: predict each of the last months from
the months before it) so the user can see which one fits their data best. Series that look recurring
but aren't flagged are suggested, so they can be flagged with one click.
"""
from __future__ import annotations

import calendar
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean, median

from app.models.transaction import Transaction
from app.services import settings_store
from app.services.analytics import MONTH_LABELS, UNCATEGORIZED, shift_month
from app.services.duplicates import _tokens

# ── Methods and preferences ────────────────────────────────────────────────────

METHODS = {
    "media":        ("Media mobile", "Media semplice degli ultimi N mesi."),
    "ponderata":    ("Media ponderata", "Media degli ultimi N mesi con più peso ai mesi recenti (pesi 1, 2, … N)."),
    "esponenziale": ("Media esponenziale", "Livellamento esponenziale con α = 2 / (N + 1): segue i cambiamenti più in fretta."),
    "mediana":      ("Mediana", "Valore centrale degli ultimi N mesi: ignora i mesi eccezionali (una spesa una tantum)."),
    "trend":        ("Trend lineare", "Retta di regressione sugli ultimi N mesi, proiettata in avanti: coglie spese in crescita o in calo."),
    "stagionale":   ("Stagionale", "Lo stesso mese dell'anno prima, riscalato sul livello degli ultimi N mesi: coglie bollette "
                                   "invernali, vacanze estive, tredicesima. Serve almeno un anno di storico."),
}
# Amount of each recurring series in the forecast (salary with overtime, bills that change)
RECURRING_AMOUNTS = {
    "media":  ("Media della finestra", "Media degli importi della serie negli ultimi N mesi, come per le variabili."),
    "ultimo": ("Ultimo importo", "L'importo dell'ultima transazione della serie: segue subito un aumento o un rinnovo."),
}
DEFAULT_RECURRING = "media"
DEFAULT_METHOD = "media"
DEFAULT_WINDOW = 6
DEFAULT_HORIZON = 12
WINDOW_RANGE = (1, 36)
HORIZON_RANGE = (1, 24)
BACKTEST_MONTHS = 6
AMOUNT_TOLERANCE = 0.15   # a recurring series keeps its amount within ±15% (fuel or groceries don't)

FREQUENCIES = {  # label, average length in days, tolerance in days, occurrences per month
    "weekly":    ("Settimanale", 7.0, 2, 52 / 12),
    "monthly":   ("Mensile", 30.44, 5, 1.0),
    "quarterly": ("Trimestrale", 91.31, 10, 1 / 3),
    "yearly":    ("Annuale", 365.25, 15, 1 / 12),
}
STEP_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}


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
    "kpi":        ("Indicatori", 2),
    "net":        ("Netto mensile", 1),
    "methods":    ("Confronto dei metodi", 1),
    "income":     ("Entrate", 1),
    "expenses":   ("Uscite", 1),
    "balance":    ("Saldo di cassa previsto", 1),
    "months":     ("Mese per mese", 1),
    "categories": ("Previsione per categoria", 1),
    "upcoming":   ("Prossime ricorrenti", 1),
    "candidates": ("Sembrano ricorrenti", 1),
    "help":       ("Come funziona", 1),
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
    try:
        return normalize_layout(json.loads(settings_store.get("forecast.layout") or "[]"))
    except (TypeError, ValueError):
        return default_layout()


def save_layout(items) -> list[dict]:
    items = normalize_layout(items)
    settings_store.set("forecast.layout", json.dumps(items))
    return items


def reset_layout() -> list[dict]:
    settings_store.set("forecast.layout", None)
    return default_layout()


# ── Forecasting one monthly series ─────────────────────────────────────────────

def predict(method: str, history: list[float], steps: int, window: int) -> list[float]:
    """
    Forecast `steps` months after `history` (monthly totals, oldest first, all complete months),
    looking at the last `window` months. Amounts are magnitudes, so forecasts never go below zero.
    """
    recent = history[-window:]
    if not recent or steps <= 0:
        return [0.0] * max(steps, 0)
    n = len(recent)

    if method == "mediana":
        values = [median(recent)] * steps
    elif method == "ponderata":
        values = [sum(x * w for w, x in enumerate(recent, 1)) / (n * (n + 1) / 2)] * steps
    elif method == "esponenziale":
        alpha, level = 2 / (n + 1), recent[0]
        for x in recent[1:]:
            level = alpha * x + (1 - alpha) * level
        values = [level] * steps
    elif method == "trend" and n >= 2:
        x_mean, y_mean = (n - 1) / 2, mean(recent)
        slope = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(recent)) / sum((i - x_mean) ** 2 for i in range(n))
        values = [y_mean + slope * (n - 1 + h - x_mean) for h in range(1, steps + 1)]
    elif method == "stagionale" and len(history) >= 12:
        # Level of the last N months compared with the same N months a year earlier
        earlier = history[-12 - n:-12] if len(history) >= 12 + n else []
        factor = mean(recent) / mean(earlier) if earlier and mean(earlier) > 0 else 1.0
        values = [history[len(history) - 12 + (h - 1) % 12] * factor for h in range(1, steps + 1)]
    else:  # "media", and the fallback when a method lacks the history it needs
        values = [mean(recent)] * steps
    return [round(max(v, 0.0), 2) for v in values]


def method_needs_more_history(method: str, months: int) -> bool:
    return (method == "stagionale" and months < 12) or (method == "trend" and months < 2)


# ── Data ───────────────────────────────────────────────────────────────────────

def series_key(tx) -> tuple:
    """Transactions of the same series (Netflix every month) share type and meaningful description words."""
    words = _tokens(tx.description)
    return (tx.type, tuple(sorted(words)) if words else ((tx.description or "").strip().lower(),))


def month_index(d: date) -> int:
    return d.year * 12 + d.month - 1


def month_label(index: int) -> str:
    return f"{MONTH_LABELS[index % 12]} {str(index // 12)[2:]}"


def month_start(index: int) -> date:
    return date(index // 12, index % 12 + 1, 1)


def add_months(d: date, months: int) -> date:
    y, m = shift_month(d.year, d.month, months)
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def occurrences(template, start: date, end: date) -> list[date]:
    """Future dates of a recurring transaction in [start, end), after the template's own date."""
    frequency = template.recurrence if template.recurrence in FREQUENCIES else "monthly"
    dates, k = [], 1
    while True:
        if frequency == "weekly":
            d = template.date + timedelta(days=7 * k)
        else:
            d = add_months(template.date, STEP_MONTHS[frequency] * k)
        if d >= end or (template.recurrence_end and d > template.recurrence_end):
            return dates
        if d >= start:
            dates.append(d)
        k += 1


def scheduled_templates(transactions) -> list:
    """The latest flagged transaction of each recurring series."""
    latest = {}
    for tx in transactions:
        if tx.is_recurring and tx.type in ("income", "expense"):
            key = series_key(tx)
            if key not in latest or (tx.date, tx.id or 0) > (latest[key].date, latest[key].id or 0):
                latest[key] = tx
    return sorted(latest.values(), key=lambda t: (t.type, t.description.lower()))


def monthly_equivalent(tx, amount: float | None = None) -> float:
    frequency = tx.recurrence if tx.recurrence in FREQUENCIES else "monthly"
    return (abs(float(tx.amount)) if amount is None else amount) * FREQUENCIES[frequency][3]


def recurring_amounts(transactions, templates, window_months: range, mode: str) -> dict:
    """
    {series key: amount of each future occurrence}. With "media", the rolling window applies to the
    recurring series too (incoming salary included): the mean of the series' amounts in the last N complete
    months, or the latest amount if the series has no movement in the window (a yearly premium).
    """
    amounts = {series_key(t): abs(float(t.amount)) for t in templates}
    if mode != "media":
        return amounts
    in_window = defaultdict(list)
    for tx in transactions:
        key = series_key(tx)
        if key in amounts and month_index(tx.date) in window_months:
            in_window[key].append(abs(float(tx.amount)))
    for key, values in in_window.items():
        amounts[key] = round(mean(values), 2)
    return amounts


# ── Detection of unflagged recurring series ────────────────────────────────────

@dataclass
class Candidate:
    template: Transaction          # latest transaction of the series: the one that gets flagged
    frequency: str
    count: int
    typical_amount: float
    next_date: date

    @property
    def frequency_label(self) -> str:
        return FREQUENCIES[self.frequency][0]

    @property
    def monthly(self) -> float:
        return self.typical_amount * FREQUENCIES[self.frequency][3]


def detect_candidates(transactions, today: date) -> list[Candidate]:
    """Series with a regular rhythm and a stable amount, still active, not flagged as recurring."""
    flagged = {series_key(t) for t in transactions if t.is_recurring}
    groups = defaultdict(list)
    for tx in transactions:
        if tx.type in ("income", "expense") and not tx.is_recurring:
            groups[series_key(tx)].append(tx)

    found = []
    for key, txs in groups.items():
        if key in flagged:
            continue
        txs.sort(key=lambda t: (t.date, t.id or 0))
        dates = sorted({t.date for t in txs})
        if len(dates) < 2 or len(dates) != len(txs):  # several on the same day: not a simple series
            continue
        intervals = [(b - a).days for a, b in zip(dates, dates[1:])]
        typical = median(intervals)
        frequency = next((f for f, (_, days, tol, _) in FREQUENCIES.items() if abs(typical - days) <= tol), None)
        if frequency is None or len(dates) < (2 if frequency == "yearly" else 3):
            continue
        _, days, tol, _ = FREQUENCIES[frequency]
        if sum(abs(i - days) <= tol for i in intervals) < 0.75 * len(intervals):
            continue
        amounts = [abs(float(t.amount)) for t in txs]
        amount = median(amounts)
        if amount <= 0 or sum(abs(a - amount) <= AMOUNT_TOLERANCE * amount for a in amounts) < 0.75 * len(amounts):
            continue
        if (today - dates[-1]).days > 1.5 * days + tol:  # stopped
            continue
        latest = txs[-1]
        step = timedelta(days=7) if frequency == "weekly" else None
        next_date = latest.date + step if step else add_months(latest.date, STEP_MONTHS[frequency])
        found.append(Candidate(latest, frequency, len(txs), round(amount, 2), next_date))
    return sorted(found, key=lambda c: c.monthly, reverse=True)


# ── The forecast ───────────────────────────────────────────────────────────────

@dataclass
class Forecast:
    method: str
    window: int
    horizon: int
    today: date
    recurring_mode: str = DEFAULT_RECURRING
    recurring_amounts: dict = field(default_factory=dict)   # series key: projected amount
    history_months: int = 0
    cutoff: date | None = None               # movements are recorded up to this day
    balance_now: float = 0.0
    history: dict = field(default_factory=dict)       # labels, income, expenses, net (complete months)
    months: list = field(default_factory=list)        # current month + horizon: forecast rows
    methods: list = field(default_factory=list)       # comparison of all methods
    categories: list = field(default_factory=list)    # next month by category
    scheduled: list = field(default_factory=list)     # flagged recurring series
    upcoming: list = field(default_factory=list)      # next scheduled occurrences
    candidates: list = field(default_factory=list)
    recurring_monthly: float = 0.0

    @property
    def method_label(self) -> str:
        return METHODS[self.method][0]

    @property
    def current(self) -> dict | None:
        return self.months[0] if self.months else None

    @property
    def next_month(self) -> dict | None:
        return self.months[1] if len(self.months) > 1 else None

    def amount_of(self, template) -> float:
        """Projected amount of a recurring series (rolling mean or latest amount)."""
        return self.recurring_amounts.get(series_key(template), abs(float(template.amount)))

    @property
    def final_balance(self) -> float:
        return self.months[-1]["balance"] if self.months else self.balance_now


def _variable_series(transactions, first: int, last: int, excluded_keys: set) -> dict:
    """{(type, category): [monthly totals from month `first` to `last`]} of non-scheduled movements."""
    series = defaultdict(lambda: [0.0] * (last - first + 1))
    for tx in transactions:
        if tx.type not in ("income", "expense") or tx.is_recurring or series_key(tx) in excluded_keys:
            continue
        i = month_index(tx.date)
        if first <= i <= last:
            series[(tx.type, tx.category or UNCATEGORIZED)][i - first] += abs(float(tx.amount))
    return series


def _scheduled_by_month(templates, amounts: dict, start: date, end: date, after: date | None = None) -> dict:
    """{month index: {(type, category): amount}} of the scheduled occurrences in [start, end)."""
    out = defaultdict(lambda: defaultdict(float))
    for tpl in templates:
        for d in occurrences(tpl, start, end):
            if after is None or d > after:
                out[month_index(d)][(tpl.type, tpl.category or UNCATEGORIZED)] += amounts[series_key(tpl)]
    return out


def _split(amounts: dict) -> tuple[float, float]:
    income = sum(v for (t, _), v in amounts.items() if t == "income")
    expenses = sum(v for (t, _), v in amounts.items() if t == "expense")
    return income, expenses


def backtest(series: dict, method: str, window: int, months: int = BACKTEST_MONTHS) -> dict | None:
    """
    Average monthly error (€) of incoming and outgoing flows, predicting each of the last `months` months
    from the months before it: {"income", "expenses", "total"}.
    """
    length = len(next(iter(series.values()), []))
    tests = range(max(1, length - months), length)
    if not series or len(tests) == 0:
        return None
    errors = []  # (income error, expenses error) per tested month
    for i in tests:
        income_err = expenses_err = 0.0
        for (tx_type, _), values in series.items():
            predicted = predict(method, values[:i], 1, window)[0]
            if tx_type == "income":
                income_err += predicted - values[i]
            else:
                expenses_err += predicted - values[i]
        errors.append((abs(income_err), abs(expenses_err)))
    income, expenses = round(mean(e[0] for e in errors), 2), round(mean(e[1] for e in errors), 2)
    return {"income": income, "expenses": expenses, "total": round(income + expenses, 2)}  # adds up as shown


def build(transactions, method: str, window: int, horizon: int, today: date, recurring: str = DEFAULT_RECURRING) -> Forecast:
    fc = Forecast(method=method, window=window, horizon=horizon, today=today, recurring_mode=recurring)
    real = [t for t in transactions if t.type in ("income", "expense")]
    fc.balance_now = round(sum(abs(float(t.amount)) * (1 if t.type == "income" else -1) for t in real if t.date <= today), 2)

    templates = scheduled_templates(real)
    template_keys = {series_key(t) for t in templates}
    fc.scheduled = templates
    fc.candidates = detect_candidates(real, today)

    current = month_index(today)
    last_complete = current - 1
    # History: complete months from the first one with movements (none if everything is in this month)
    first = min((month_index(t.date) for t in real if month_index(t.date) < current), default=current)
    fc.history_months = last_complete - first + 1 if first < current else 0
    window_months = range(max(first, last_complete - window + 1), last_complete + 1) if fc.history_months else range(0)

    amounts = fc.recurring_amounts = recurring_amounts(real, templates, window_months, recurring)
    fc.recurring_monthly = round(sum(
        monthly_equivalent(t, amounts[series_key(t)]) * (1 if t.type == "income" else -1) for t in templates), 2)

    # Actual totals of the complete months (shown for the last 12)
    actual = defaultdict(lambda: [0.0, 0.0])
    for tx in real:
        actual[month_index(tx.date)][0 if tx.type == "income" else 1] += abs(float(tx.amount))
    shown = range(max(first, last_complete - 11), last_complete + 1)
    fc.history = {
        "labels": [month_label(i) for i in shown],
        "income": [round(actual[i][0], 2) for i in shown],
        "expenses": [round(actual[i][1], 2) for i in shown],
        "net": [round(actual[i][0] - actual[i][1], 2) for i in shown],
    }

    variable = _variable_series(real, first, last_complete, template_keys) if fc.history_months else {}
    steps = horizon + 1  # the current month, then `horizon` months
    horizon_end = month_start(current + steps)
    this_month = month_start(current)

    # Movements are recorded up to the last transaction (statements are imported after the fact)
    last_tx = max((t.date for t in real if t.date <= today), default=this_month - timedelta(days=1))
    fc.cutoff = min(max(last_tx, this_month - timedelta(days=1)), today)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    remaining = (days_in_month - fc.cutoff.day) / days_in_month if fc.cutoff >= this_month else 1.0

    scheduled = _scheduled_by_month(templates, amounts, this_month, horizon_end)
    scheduled_rest = _scheduled_by_month(templates, amounts, this_month, month_start(current + 1), after=fc.cutoff)

    def month_rows(method_key: str) -> list[dict]:
        predicted = {key: predict(method_key, values, steps, window) for key, values in variable.items()}
        rows = []
        for h in range(steps):
            i = current + h
            var = {key: values[h] for key, values in predicted.items()}
            if h == 0:  # current month: recorded so far + what is still to come
                done_income, done_expenses = actual[i]
                rest_var = {k: v * remaining for k, v in var.items()}
                s_income, s_expenses = _split(scheduled_rest.get(i, {}))
                v_income, v_expenses = _split(rest_var)
                income, expenses = done_income + s_income + v_income, done_expenses + s_expenses + v_expenses
                rest_net = (s_income + v_income) - (s_expenses + v_expenses)
            else:
                s_income, s_expenses = _split(scheduled.get(i, {}))
                v_income, v_expenses = _split(var)
                income, expenses = s_income + v_income, s_expenses + v_expenses
                rest_net = income - expenses
            rows.append({
                "index": i, "label": month_label(i), "current": h == 0,
                "income": round(income, 2), "expenses": round(expenses, 2), "net": round(income - expenses, 2),
                "scheduled_income": round(s_income, 2), "scheduled_expenses": round(s_expenses, 2),
                "rest_net": rest_net,
            })
        balance = fc.balance_now
        for row in rows:
            balance += row.pop("rest_net")
            row["balance"] = round(balance, 2)
        return rows

    all_rows = {key: month_rows(key) for key in METHODS}
    fc.months = all_rows[method]
    # Bands: the range of every method's forecast, for the net and for each flow
    for row_i, row in enumerate(fc.months):
        for field_name, low, high in (("net", "low", "high"), ("income", "income_low", "income_high"),
                                      ("expenses", "expenses_low", "expenses_high")):
            values = [all_rows[key][row_i][field_name] for key in METHODS]
            row[low], row[high] = min(values), max(values)

    errors = {key: backtest(variable, key, window) if fc.history_months >= 2 else None for key in METHODS}
    measured = {k: e for k, e in errors.items() if e is not None}

    def best_for(flow):
        return min(measured, key=lambda k: measured[k][flow]) if measured else None

    best, best_income, best_expenses = best_for("total"), best_for("income"), best_for("expenses")
    fc.methods = [
        {
            "key": key, "label": label, "description": description,
            "error": errors[key]["total"] if errors[key] else None,
            "error_income": errors[key]["income"] if errors[key] else None,
            "error_expenses": errors[key]["expenses"] if errors[key] else None,
            "best": key == best, "best_income": key == best_income, "best_expenses": key == best_expenses,
            "selected": key == method,
            "fallback": method_needs_more_history(key, fc.history_months if key == "stagionale" else min(fc.history_months, window)),
            "next_net": all_rows[key][1]["net"] if steps > 1 else all_rows[key][0]["net"],
            "next_income": all_rows[key][1]["income"] if steps > 1 else all_rows[key][0]["income"],
            "next_expenses": all_rows[key][1]["expenses"] if steps > 1 else all_rows[key][0]["expenses"],
            "final_balance": all_rows[key][-1]["balance"],
        }
        for key, (label, description) in METHODS.items()
    ]

    # Next full month by category
    if steps > 1:
        nxt = current + 1
        averages = defaultdict(float)
        for tx in real:
            if month_index(tx.date) in window_months:
                averages[(tx.type, tx.category or UNCATEGORIZED)] += abs(float(tx.amount))
        n_months = max(len(window_months), 1)
        var_next = {key: predict(method, values, 2, window)[1] for key, values in variable.items()}
        keys = set(averages) | set(var_next) | set(scheduled.get(nxt, {}))
        rows = []
        for key in keys:
            sched = scheduled.get(nxt, {}).get(key, 0.0)
            var = var_next.get(key, 0.0)
            avg = averages.get(key, 0.0) / n_months
            if round(sched + var, 2) == 0 and round(avg, 2) == 0:
                continue
            rows.append({
                "type": key[0], "category": key[1], "average": round(avg, 2),
                "scheduled": round(sched, 2), "variable": round(var, 2), "total": round(sched + var, 2),
            })
        fc.categories = sorted(rows, key=lambda r: (r["type"] != "expense", -r["total"]))

    # Scheduled occurrences still to come, up to the end of next month
    soon_end = month_start(current + 2)
    upcoming = [(d, tpl) for tpl in templates for d in occurrences(tpl, fc.cutoff + timedelta(days=1), soon_end)]
    fc.upcoming = [{"date": d, "tx": tpl, "amount": amounts[series_key(tpl)]}
                   for d, tpl in sorted(upcoming, key=lambda x: (x[0], x[1].description))]
    return fc


def load(method: str, window: int, horizon: int, recurring: str = DEFAULT_RECURRING, today: date | None = None) -> Forecast:
    today = today or date.today()
    transactions = Transaction.query.filter(Transaction.type.in_(["income", "expense"])).all()
    return build(transactions, method, window, horizon, today, recurring)
