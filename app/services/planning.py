"""
Planning (F20): where the savings goals get to, and whether the money lasts after work.

Goals
- a goal linked to an account follows its balance; with a monthly saving and a yearly return it is projected month
  by month: the date it is reached, and the monthly saving needed to reach it by its date; three scenarios (return
  −2, as set, +2 points)

Retirement / FIRE (Monte Carlo)
- everything in today's euro: the yearly return drawn from a normal distribution (mean = expected return −
  inflation, the volatility given), the same seed every time so the page does not change at each visit
- until the retirement age: wealth × (1 + r) + yearly saving; after: wealth × (1 + r) − (expenses − pension)
- success = the money never runs out before the end of the horizon; the age of financial independence is the
  first at which the median wealth covers the yearly gap at the safe withdrawal rate
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal

from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.wealth import Goal
from app.services import accounts, periods, settings_store, wealth
from app.services.totals import value_total

RETIREMENT_KEY = "planning.retirement"
MAX_MONTHS = 600
RUNS = 1000
SEED = 20


# ── Goals ──────────────────────────────────────────────────────────────────────

def sync(goals: list[Goal]) -> None:
    """A goal linked to an account has saved what the account holds."""
    for goal in goals:
        if goal.account_id:
            account = db.session.get(Account, goal.account_id)
            if account is not None:
                goal.saved_amount = Decimal(str(round(max(accounts.balance(account), 0), 2)))


def _monthly_rate(yearly: float) -> float:
    return (1 + yearly / 100) ** (1 / 12) - 1


def future_value(present: float, monthly: float, yearly_return: float, months: int) -> float:
    r = _monthly_rate(yearly_return)
    if r == 0:
        return present + monthly * months
    growth = (1 + r) ** months
    return present * growth + monthly * (growth - 1) / r


def months_to(target: float, present: float, monthly: float, yearly_return: float) -> int | None:
    """Months until `target` is reached (None: never, within fifty years)."""
    r, value = _monthly_rate(yearly_return), present
    for month in range(MAX_MONTHS + 1):
        if value >= target:
            return month
        value = value * (1 + r) + monthly
    return None


def required_monthly(target: float, present: float, yearly_return: float, months: int) -> float:
    """The monthly saving that reaches `target` in `months`."""
    if months <= 0:
        return max(target - present, 0.0)
    r = _monthly_rate(yearly_return)
    gap = target - present * (1 + r) ** months
    if gap <= 0:
        return 0.0
    return gap / months if r == 0 else gap * r / ((1 + r) ** months - 1)


@dataclass
class GoalPlan:
    goal: Goal
    monthly: float
    yearly_return: float
    months_left: int | None           # to the target date
    needed: float | None              # monthly saving to be on time
    reached_on: date | None           # with the saving and return set
    scenarios: list[tuple[float, date | None]] = field(default_factory=list)


def goal_plan(goal: Goal, today: date | None = None) -> GoalPlan:
    today = today or date.today()
    present, target = float(goal.saved_amount or 0), float(goal.target_amount)
    monthly, rate = float(goal.monthly_contribution or 0), float(goal.expected_return or 0)
    months_left = None
    if goal.target_date:
        months_left = max((goal.target_date.year - today.year) * 12 + goal.target_date.month - today.month, 0)
    needed = round(required_monthly(target, present, rate, months_left), 2) if months_left is not None else None

    def reached(r: float) -> date | None:
        n = months_to(target, present, monthly, r)
        return periods.add_months(today, n) if n is not None else None

    return GoalPlan(goal, monthly, rate, months_left, needed, reached(rate),
                    [(r, reached(r)) for r in (rate - 2, rate, rate + 2)])


# ── Retirement / FIRE ──────────────────────────────────────────────────────────

@dataclass
class Retirement:
    age: int = 40
    retire_at: int = 65
    horizon: int = 95
    wealth: float = 0.0               # investable today (cash + investments)
    yearly_saving: float = 0.0        # until retirement
    expenses: float = 0.0             # a year, after retirement, in today's euro
    pension: float = 0.0              # a year from the state and pension funds, from the retirement age
    expected_return: float = 5.0      # % a year, nominal
    volatility: float = 12.0          # % a year
    inflation: float = 2.0            # % a year
    withdrawal_rate: float = 4.0      # % of the wealth taken each year (the «4 % rule»)
    # The glide path (F22): the share in bonds at retirement and at the end, rising in a straight line in between, so
    # that a crash in the first years of withdrawals hurts less. Both 0: no glide (expected_return/volatility only)
    bonds_at_retirement: float = 0.0  # %
    bonds_at_horizon: float = 0.0     # %
    bond_return: float = 3.0          # % a year, nominal
    bond_volatility: float = 5.0      # % a year

    @property
    def glides(self) -> bool:
        return bool(self.bonds_at_retirement or self.bonds_at_horizon)

    def bond_share(self, age: int) -> float:
        """The share in bonds at an age: the retirement one before, then a straight line to the horizon's."""
        if age <= self.retire_at:
            return self.bonds_at_retirement / 100
        step = (age - self.retire_at) / (self.horizon - self.retire_at)
        return (self.bonds_at_retirement + (self.bonds_at_horizon - self.bonds_at_retirement) * step) / 100

    def check(self) -> None:
        if not 18 <= self.age < self.retire_at < self.horizon <= 110:
            raise ValueError(_("Le età devono essere in ordine: oggi < pensione < fine dell'orizzonte (al massimo 110)."))
        if self.volatility < 0 or self.withdrawal_rate <= 0 or self.wealth < 0 or self.expenses < 0:
            raise ValueError(_("Patrimonio, spese, volatilità e prelievo non possono essere negativi."))
        if not (0 <= self.bonds_at_retirement <= 100 and 0 <= self.bonds_at_horizon <= 100) or self.bond_volatility < 0:
            raise ValueError(_("Quote in obbligazioni tra 0 e 100; la loro volatilità non può essere negativa."))


def suggested(today: date | None = None) -> Retirement:
    """A starting point from the archive: investable wealth, last year's expenses and saving."""
    today = today or date.today()
    sheet = wealth.balance_sheet()
    start = periods.add_months(today, -12)
    period = (Transaction.date > start, Transaction.date <= today)
    expenses = value_total(Transaction.type == "expense", *period)
    income = value_total(Transaction.type == "income", *period)
    return Retirement(wealth=round(sheet["cash"] + sheet["investments"], 2), expenses=round(expenses, 2),
                      yearly_saving=round(max(income - expenses, 0), 2))


def load() -> Retirement:
    data = settings_store.get_json(RETIREMENT_KEY, {}, expect=dict)
    if not data:
        return suggested()
    known = {k: v for k, v in data.items() if k in Retirement.__dataclass_fields__}
    return Retirement(**known)


def save(plan: Retirement) -> None:
    plan.check()
    settings_store.set_json(RETIREMENT_KEY, asdict(plan))


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(int(q * len(ordered)), len(ordered) - 1)]


def simulate(plan: Retirement, runs: int = RUNS, seed: int = SEED, glide: bool = True) -> dict:
    """The Monte Carlo of the plan; with a glide path, also the same run without it, to compare."""
    plan.check()
    result = _simulate(plan, runs, seed, glide and plan.glides)
    if glide and plan.glides:
        without = _simulate(plan, runs, seed, False)
        result["without"] = {"success": without["success"], "p10_end": without["p10"][-1], "p50_end": without["p50"][-1]}
        result["bonds"] = [round(plan.bond_share(age) * 100, 1) for age in result["ages"]]
    return result


def _simulate(plan: Retirement, runs: int, seed: int, glide: bool) -> dict:
    rng = random.Random(seed)
    mean, vol = (plan.expected_return - plan.inflation) / 100, plan.volatility / 100
    bond_mean, bond_vol = (plan.bond_return - plan.inflation) / 100, plan.bond_volatility / 100
    ages = list(range(plan.age, plan.horizon + 1))
    paths, successes, ran_out = [], 0, []
    gap = max(plan.expenses - plan.pension, 0.0)
    for _run in range(runs):
        value, path, broke = plan.wealth, [plan.wealth], None
        for age in ages[1:]:
            r = rng.gauss(mean, vol)
            if glide:
                share = plan.bond_share(age)
                r = (1 - share) * r + share * rng.gauss(bond_mean, bond_vol)
            value = value * (1 + r) + (plan.yearly_saving if age <= plan.retire_at else -gap)
            if value < 0 and broke is None:
                broke = age
            value = max(value, 0.0)
            path.append(value)
        paths.append(path)
        if broke is None:
            successes += 1
        else:
            ran_out.append(broke)
    bands = {q: [round(_percentile([p[i] for p in paths], q), 0) for i in range(len(ages))] for q in (0.1, 0.5, 0.9)}
    at_retirement = bands[0.5][ages.index(plan.retire_at)]
    needed = gap / (plan.withdrawal_rate / 100) if gap else 0.0
    fire_age = next((age for age, value in zip(ages, bands[0.5]) if needed and value >= needed), None)
    return {
        "ages": ages, "p10": bands[0.1], "p50": bands[0.5], "p90": bands[0.9],
        "success": round(successes / runs * 100, 1),
        "median_at_retirement": at_retirement,
        "sustainable": round(at_retirement * plan.withdrawal_rate / 100, 0),
        "needed": round(needed, 0),
        "fire_age": fire_age,
        "first_broke": min(ran_out) if ran_out else None,
        "gap": round(gap, 0),
    }
