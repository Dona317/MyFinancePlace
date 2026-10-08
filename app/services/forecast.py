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
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean, median

from sqlalchemy.orm import selectinload

from app.models.transaction import Transaction
from app.services.analytics import UNCATEGORIZED
from app.services.duplicates import meaningful_words
from app.services.periods import add_months, month_index, month_label, month_start, shift_month  # noqa: F401 (shift_month re-exported)
from app.services.forecast_prefs import (  # noqa: F401 - the page's choices, re-exported for older imports
    DEFAULT_RECURRING, HORIZON_RANGE, LAYOUT_SETTING, METHODS, RECURRING_AMOUNTS, WIDGETS, WINDOW_RANGE, default_layout, layout,
    normalize_layout, preferences, reset_layout, save_layout, save_preferences,
)
from app.services.i18n import _l

# ── Constants ──────────────────────────────────────────────────────────────────

BACKTEST_MONTHS = 6
AMOUNT_TOLERANCE = 0.15   # a recurring series keeps its amount within ±15% (fuel or groceries don't)

FREQUENCIES = {  # label, average length in days, tolerance in days, occurrences per month
    "weekly":    (_l("Settimanale"), 7.0, 2, 52 / 12),
    "monthly":   (_l("Mensile"), 30.44, 5, 1.0),
    "quarterly": (_l("Trimestrale"), 91.31, 10, 1 / 3),
    "yearly":    (_l("Annuale"), 365.25, 15, 1 / 12),
}
STEP_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}


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
    words = meaningful_words(tx.description)
    return (tx.type, tuple(sorted(words)) if words else ((tx.description or "").strip().lower(),))


def step_date(day: date, frequency: str, k: int = 1) -> date:
    """`k` periods of `frequency` after `day` (a week, or 1/2/3/6/12 months)."""
    if frequency == "weekly":
        return day + timedelta(days=7 * k)
    return add_months(day, STEP_MONTHS[frequency] * k)


def occurrences(template, start: date, end: date) -> list[date]:
    """Future dates of a recurring transaction in [start, end), after the template's own date."""
    frequency = template.recurrence if template.recurrence in FREQUENCIES else "monthly"
    dates, k = [], 1
    while True:
        d = step_date(template.date, frequency, k)
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
    return (tx.magnitude if amount is None else amount) * FREQUENCIES[frequency][3]


def recurring_amounts(transactions, templates, window_months: range, mode: str) -> dict:
    """
    {series key: amount of each future occurrence}. With "media", the rolling window applies to the
    recurring series too (incoming salary included): the mean of the series' amounts in the last N complete
    months, or the latest amount if the series has no movement in the window (a yearly premium).
    """
    amounts = {series_key(t): t.magnitude for t in templates}
    if mode != "media":
        return amounts
    in_window = defaultdict(list)
    for tx in transactions:
        key = series_key(tx)
        if key in amounts and month_index(tx.date) in window_months:
            in_window[key].append(tx.magnitude)
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
        amounts = [t.magnitude for t in txs]
        amount = median(amounts)
        if amount <= 0 or sum(abs(a - amount) <= AMOUNT_TOLERANCE * amount for a in amounts) < 0.75 * len(amounts):
            continue
        if (today - dates[-1]).days > 1.5 * days + tol:  # stopped
            continue
        latest = txs[-1]
        found.append(Candidate(latest, frequency, len(txs), round(amount, 2), step_date(latest.date, frequency)))
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
            for category, amount in tx.parts():  # a split transaction counts in each of its categories
                series[(tx.type, category or UNCATEGORIZED)][i - first] += amount
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


@dataclass
class _Plan:
    """What every method's month rows are built from (one build)."""
    current: int                      # month index of today
    steps: int                        # the current month, then `horizon` months
    window: int
    remaining: float                  # share of the current month still to come after the cutoff
    balance_now: float
    actual: dict                      # month index → [income, expenses] recorded
    variable: dict                    # series key → monthly history of the variable spending
    scheduled: dict                   # month index → {series key: amount} of the scheduled ones
    scheduled_rest: dict              # the same, for the current month after the cutoff only


def _actual_totals(real) -> dict:
    actual = defaultdict(lambda: [0.0, 0.0])
    for tx in real:
        actual[month_index(tx.date)][0 if tx.type == "income" else 1] += tx.magnitude
    return actual


def _history(actual: dict, first: int, last_complete: int) -> dict:
    """The actual totals of the last 12 complete months, for the chart."""
    shown = range(max(first, last_complete - 11), last_complete + 1)
    return {
        "labels": [month_label(i) for i in shown],
        "income": [round(actual[i][0], 2) for i in shown],
        "expenses": [round(actual[i][1], 2) for i in shown],
        "net": [round(actual[i][0] - actual[i][1], 2) for i in shown],
    }


def _cutoff(real, today: date) -> tuple[date, float]:
    """Movements are recorded up to the last transaction (statements are imported after the fact): the day they stop,
    and the share of this month still to come after it."""
    this_month = month_start(month_index(today))
    last_tx = max((t.date for t in real if t.date <= today), default=this_month - timedelta(days=1))
    cutoff = min(max(last_tx, this_month - timedelta(days=1)), today)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    return cutoff, (days_in_month - cutoff.day) / days_in_month if cutoff >= this_month else 1.0


def _month_rows(plan: _Plan, method_key: str) -> list[dict]:
    """The forecast of one method, month by month, with the running balance."""
    predicted = {key: predict(method_key, values, plan.steps, plan.window) for key, values in plan.variable.items()}
    rows = []
    for h in range(plan.steps):
        i = plan.current + h
        var = {key: values[h] for key, values in predicted.items()}
        if h == 0:  # current month: recorded so far + what is still to come
            done_income, done_expenses = plan.actual[i]
            s_income, s_expenses = _split(plan.scheduled_rest.get(i, {}))
            v_income, v_expenses = _split({k: v * plan.remaining for k, v in var.items()})
            income, expenses = done_income + s_income + v_income, done_expenses + s_expenses + v_expenses
            rest_net = (s_income + v_income) - (s_expenses + v_expenses)
        else:
            s_income, s_expenses = _split(plan.scheduled.get(i, {}))
            v_income, v_expenses = _split(var)
            income, expenses = s_income + v_income, s_expenses + v_expenses
            rest_net = income - expenses
        rows.append({
            "index": i, "label": month_label(i), "current": h == 0,
            "income": round(income, 2), "expenses": round(expenses, 2), "net": round(income - expenses, 2),
            "scheduled_income": round(s_income, 2), "scheduled_expenses": round(s_expenses, 2),
            "rest_net": rest_net,
        })
    balance = plan.balance_now
    for row in rows:
        balance += row.pop("rest_net")
        row["balance"] = round(balance, 2)
    return rows


def _add_bands(months: list[dict], all_rows: dict) -> None:
    """The range of every method's forecast, for the net and for each flow."""
    for row_i, row in enumerate(months):
        for field_name, low, high in (("net", "low", "high"), ("income", "income_low", "income_high"),
                                      ("expenses", "expenses_low", "expenses_high")):
            values = [all_rows[key][row_i][field_name] for key in METHODS]
            row[low], row[high] = min(values), max(values)


def _compare_methods(fc: Forecast, variable: dict, all_rows: dict, steps: int) -> list[dict]:
    """Each method with its back-tested error, which one is best, and its forecast of the next month."""
    errors = {key: backtest(variable, key, fc.window) if fc.history_months >= 2 else None for key in METHODS}
    measured = {k: e for k, e in errors.items() if e is not None}

    def best_for(flow):
        return min(measured, key=lambda k: measured[k][flow]) if measured else None

    best, best_income, best_expenses = best_for("total"), best_for("income"), best_for("expenses")
    methods = []
    for key, (label, description) in METHODS.items():
        error = errors[key] or {}
        next_row = all_rows[key][1 if steps > 1 else 0]
        history = fc.history_months if key == "stagionale" else min(fc.history_months, fc.window)
        methods.append({
            "key": key, "label": label, "description": description,
            "error": error.get("total"), "error_income": error.get("income"), "error_expenses": error.get("expenses"),
            "best": key == best, "best_income": key == best_income, "best_expenses": key == best_expenses,
            "selected": key == fc.method, "fallback": method_needs_more_history(key, history),
            "next_net": next_row["net"], "next_income": next_row["income"], "next_expenses": next_row["expenses"],
            "final_balance": all_rows[key][-1]["balance"],
        })
    return methods


def _next_month_categories(real, plan: _Plan, method: str, window_months: range) -> list[dict]:
    """Next full month by category: the average of the window, what is scheduled and the variable forecast."""
    nxt = plan.current + 1
    averages = defaultdict(float)
    for tx in real:
        if month_index(tx.date) in window_months:
            for category, amount in tx.parts():
                averages[(tx.type, category or UNCATEGORIZED)] += amount
    n_months = max(len(window_months), 1)
    var_next = {key: predict(method, values, 2, plan.window)[1] for key, values in plan.variable.items()}
    scheduled_next = plan.scheduled.get(nxt, {})
    rows = []
    for key in set(averages) | set(var_next) | set(scheduled_next):
        sched, var = scheduled_next.get(key, 0.0), var_next.get(key, 0.0)
        avg = averages.get(key, 0.0) / n_months
        if round(sched + var, 2) == 0 and round(avg, 2) == 0:
            continue
        rows.append({"type": key[0], "category": key[1], "average": round(avg, 2),
                     "scheduled": round(sched, 2), "variable": round(var, 2), "total": round(sched + var, 2)})
    return sorted(rows, key=lambda r: (r["type"] != "expense", -r["total"], -r["average"], r["category"]))


def _upcoming(templates, amounts: dict, cutoff: date, current: int) -> list[dict]:
    """Scheduled occurrences still to come, up to the end of next month."""
    soon_end = month_start(current + 2)
    upcoming = [(d, tpl) for tpl in templates for d in occurrences(tpl, cutoff + timedelta(days=1), soon_end)]
    return [{"date": d, "tx": tpl, "amount": amounts[series_key(tpl)]}
            for d, tpl in sorted(upcoming, key=lambda x: (x[0], x[1].description))]


def build(transactions, method: str, window: int, horizon: int, today: date, recurring: str = DEFAULT_RECURRING) -> Forecast:
    fc = Forecast(method=method, window=window, horizon=horizon, today=today, recurring_mode=recurring)
    real = [t for t in transactions if t.type in ("income", "expense")]
    fc.balance_now = round(sum(t.signed_amount for t in real if t.date <= today), 2)

    templates = scheduled_templates(real)
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

    actual = _actual_totals(real)
    fc.history = _history(actual, first, last_complete)
    fc.cutoff, remaining = _cutoff(real, today)
    steps = horizon + 1  # the current month, then `horizon` months
    this_month = month_start(current)
    plan = _Plan(
        current=current, steps=steps, window=window, remaining=remaining, balance_now=fc.balance_now, actual=actual,
        variable=_variable_series(real, first, last_complete, {series_key(t) for t in templates})
        if fc.history_months else {},
        scheduled=_scheduled_by_month(templates, amounts, this_month, month_start(current + steps)),
        scheduled_rest=_scheduled_by_month(templates, amounts, this_month, month_start(current + 1), after=fc.cutoff),
    )

    all_rows = {key: _month_rows(plan, key) for key in METHODS}
    fc.months = all_rows[method]
    _add_bands(fc.months, all_rows)
    fc.methods = _compare_methods(fc, plan.variable, all_rows, steps)
    if steps > 1:
        fc.categories = _next_month_categories(real, plan, method, window_months)
    fc.upcoming = _upcoming(templates, amounts, fc.cutoff, current)
    return fc


def load(method: str, window: int, horizon: int, recurring: str = DEFAULT_RECURRING, today: date | None = None) -> Forecast:
    today = today or date.today()
    transactions = (Transaction.query.filter(Transaction.type.in_(["income", "expense"]))
                    .options(selectinload(Transaction.splits)).all())
    return build(transactions, method, window, horizon, today, recurring)
