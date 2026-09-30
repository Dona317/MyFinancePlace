"""
Net worth: cash from the transactions, investments and other assets, debts and their amortization plans.
Feeds the Balance Sheet, the dashboard KPIs, Portfolio, Debt and the Snapshots.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import case, func

from app.extensions import db
from app.models.transaction import Transaction
from app.models.wealth import Debt, Holding, Snapshot
from app.services import accounts, settings_store
from app.services.periods import add_months
from app.services.i18n import N_

# ── Asset classes and how the Balance Sheet groups them ────────────────────────

INVESTMENTS = N_("Portafoglio investimenti")
ASSET_CLASSES = {
    # class: (balance-sheet line, is it part of the investment portfolio?)
    N_("Azione"):          (INVESTMENTS, True),
    N_("ETF"):             (INVESTMENTS, True),
    N_("Fondo"):           (INVESTMENTS, True),
    N_("Obbligazione"):    (INVESTMENTS, True),
    N_("Criptovaluta"):    (INVESTMENTS, True),
    N_("Conto Risparmio"): (N_("Conti deposito e risparmio"), False),
    N_("Fondo Pensione"):  (N_("Previdenza complementare"), False),
    N_("Immobile"):        (N_("Immobili"), False),
    N_("Altro"):           (N_("Altri beni"), False),
}
CURRENT_ASSET_LINES = (N_("Liquidità"), N_("Conti deposito e risparmio"))

DEBT_TYPES = [N_("Mutuo"), N_("Prestito Personale"), N_("Prestito Auto"), N_("Carta di Credito"), N_("Prestito Studentesco"), N_("Altro")]

OPENING_CASH_SETTING = "balance.opening_cash"
MAX_PLAN_MONTHS = 12 * 100  # a plan that never ends (installment below the interest) stops here


def _money(value) -> float:
    return round(float(value or 0), 2)


# ── Cash ───────────────────────────────────────────────────────────────────────

def opening_cash() -> float:
    """Money on the accounts before the first recorded transaction (set in the Balance Sheet)."""
    try:
        return float(settings_store.get(OPENING_CASH_SETTING) or 0)
    except ValueError:
        return 0.0


def cash_balance(on: date | None = None) -> float:
    """
    Opening balance (general + each account's) + income − expenses up to and including `on`
    (transfers move money between own accounts).
    """
    signed = func.sum(case((Transaction.type == "expense", -func.abs(Transaction.amount_base)),
                           else_=func.abs(Transaction.amount_base)))
    query = db.session.query(func.coalesce(signed, 0)).filter(Transaction.type.in_(["income", "expense"]))
    if on is not None:
        query = query.filter(Transaction.date <= on)
    return _money(opening_cash() + accounts.opening_total() + float(query.scalar()))


# ── Debts: French amortization (constant monthly installment) ──────────────────

@dataclass
class Installment:
    number: int
    due: date
    payment: float
    interest: float
    principal: float
    balance: float


def installment(debt: Debt) -> float | None:
    """The monthly installment: the one entered, or the one that repays the principal over the term."""
    if debt.monthly_payment:
        return float(debt.monthly_payment)
    if not debt.term_months:
        return None
    principal, rate = float(debt.principal or 0), float(debt.annual_rate or 0) / 1200
    if rate == 0:
        return round(principal / debt.term_months, 2)
    return round(principal * rate / (1 - (1 + rate) ** -debt.term_months), 2)


def schedule(debt: Debt) -> list[Installment]:
    """Every installment from the first (one month after the start) until the debt is repaid."""
    payment = installment(debt)
    if not payment or not debt.start_date:
        return []
    rate = float(debt.annual_rate or 0) / 1200
    balance = float(debt.principal or 0)
    plan = []
    number = 0
    while balance > 0.005 and number < MAX_PLAN_MONTHS:
        number += 1
        interest = round(balance * rate, 2)
        if payment <= interest:  # the installment doesn't even cover the interest: the debt never ends
            break
        paid = min(payment, balance + interest)
        balance = round(balance + interest - paid, 2)
        plan.append(Installment(number, add_months(debt.start_date, number), round(paid, 2),
                                interest, round(paid - interest, 2), max(balance, 0.0)))
    return plan


def never_ends(debt: Debt) -> bool:
    payment = installment(debt)
    rate = float(debt.annual_rate or 0) / 1200
    return bool(payment) and payment <= float(debt.principal or 0) * rate


def balance_on(debt: Debt, on: date | None = None, plan: list[Installment] | None = None) -> float:
    """
    Outstanding balance on a date. Today: the balance the user entered, if any; otherwise the plan says
    how much is left after the installments already due. Without a plan, the whole principal.
    """
    today = date.today()
    on = on or today
    if debt.balance is not None and on >= today:
        return _money(debt.balance)
    if debt.start_date and on < debt.start_date:
        return 0.0
    plan = schedule(debt) if plan is None else plan
    if not plan:
        return _money(debt.balance if debt.balance is not None else debt.principal)
    paid = [row for row in plan if row.due <= on]
    return _money(paid[-1].balance if paid else debt.principal)


def interest_between(debt: Debt, start: date, end: date, plan: list[Installment] | None = None) -> float:
    plan = schedule(debt) if plan is None else plan
    return _money(sum(row.interest for row in plan if start <= row.due < end))


def debt_summary(debt: Debt, today: date | None = None) -> dict:
    today = today or date.today()
    plan = schedule(debt)
    remaining = [row for row in plan if row.due > today]
    balance = balance_on(debt, today, plan)
    principal = float(debt.principal or 0)
    return {
        "debt": debt,
        "installment": installment(debt),
        "balance": balance,
        "repaid_pct": round(min(max((principal - balance) / principal * 100, 0), 100), 1) if principal else 0.0,
        "end_date": plan[-1].due if plan else None,
        "months_left": len(remaining),
        "interest_left": _money(sum(row.interest for row in remaining)),
        "interest_ytd": interest_between(debt, date(today.year, 1, 1), today + timedelta(days=1), plan),
        "never_ends": never_ends(debt),
        "short_term": debt.type == "Carta di Credito" or bool(plan and len(remaining) <= 12 and remaining),
    }


def debts_projection(debts: list[Debt], today: date | None = None, years: int = 10) -> dict:
    """Outstanding balance of each debt at the start of each of the next `years` years (for the chart)."""
    today = today or date.today()
    dates = [today] + [date(today.year + i, 1, 1) for i in range(1, years + 1)]
    datasets = []
    for debt in debts:
        plan = schedule(debt)
        datasets.append({"label": debt.name, "data": [balance_on(debt, d, plan) for d in dates]})
    return {"labels": ["Oggi"] + [str(d.year) for d in dates[1:]], "datasets": datasets}


def monthly_installments(today: date | None = None) -> float:
    """Sum of the installments of the debts still being repaid."""
    summaries = [debt_summary(d, today) for d in Debt.query.all()]
    return _money(sum(s["installment"] or 0 for s in summaries if s["balance"] > 0))


def monthly_average_income(today: date | None = None, months: int = 12) -> float:
    today = today or date.today()
    start = add_months(date(today.year, today.month, 1), -months)
    total = (
        db.session.query(func.coalesce(func.sum(func.abs(Transaction.amount_base)), 0))
        .filter(Transaction.type == "income", Transaction.date >= start, Transaction.date < date(today.year, today.month, 1))
        .scalar()
    )
    return float(total) / months


# ── Portfolio ──────────────────────────────────────────────────────────────────

def holdings_on(on: date | None = None) -> list[Holding]:
    """Holdings owned on a date (bought on or before it; no purchase date = always owned)."""
    query = Holding.query
    if on is not None:
        query = query.filter((Holding.purchase_date.is_(None)) | (Holding.purchase_date <= on))
    return query.order_by(Holding.asset_class, Holding.name).all()


def portfolio_summary(holdings: list[Holding]) -> dict:
    invested = [h for h in holdings if ASSET_CLASSES.get(h.asset_class, ("", False))[1]]
    cost = sum(h.cost for h in holdings)
    value = sum(h.value for h in holdings)
    allocation = defaultdict(float)
    for h in holdings:
        allocation[h.asset_class] += h.value
    return {
        "value": _money(value),
        "cost": _money(cost),
        "gain": _money(value - cost),
        "gain_pct": round((value - cost) / cost * 100, 2) if cost else 0.0,
        "investments_value": _money(sum(h.value for h in invested)),
        "allocation": sorted(allocation.items(), key=lambda item: item[1], reverse=True),
    }


def dividends(start: date, end: date) -> float:
    """Income recorded under a dividend or coupon category."""
    total = (
        db.session.query(func.coalesce(func.sum(func.abs(Transaction.amount_base)), 0))
        .filter(Transaction.type == "income", Transaction.date >= start, Transaction.date < end,
                func.lower(Transaction.category).op("~")("dividend|cedol"))
        .scalar()
    )
    return _money(total)


# ── Balance Sheet ──────────────────────────────────────────────────────────────

def balance_sheet(on: date | None = None) -> dict:
    """
    Assets and liabilities on a date. Holdings are valued at their latest price (the app keeps no price
    history); debts follow their amortization plan; cash is the balance of the transactions.
    """
    today = date.today()
    on = on or today
    assets = defaultdict(float)
    assets["Liquidità"] = cash_balance(on)
    for h in holdings_on(on):
        assets[ASSET_CLASSES.get(h.asset_class, ("Altri beni", False))[0]] += h.value

    liabilities = defaultdict(float)
    debt_rows = []
    for debt in Debt.query.order_by(Debt.name).all():
        summary = debt_summary(debt, on)
        if summary["balance"] <= 0:
            continue
        if debt.type == "Carta di Credito":
            line = N_("Carte di credito")
        elif summary["short_term"]:
            line = N_("Prestiti in scadenza entro 12 mesi")
        elif debt.type == "Mutuo":
            line = N_("Mutui")
        else:
            line = N_("Prestiti a lungo termine")
        liabilities[line] += summary["balance"]
        debt_rows.append({"name": debt.name, "type": debt.type, "line": line, "balance": summary["balance"]})

    current_assets = {k: _money(v) for k, v in assets.items() if k in CURRENT_ASSET_LINES}
    other_assets = {k: _money(v) for k, v in assets.items() if k not in CURRENT_ASSET_LINES and v}
    current_liabilities = {k: _money(v) for k, v in liabilities.items()
                           if k in ("Carte di credito", "Prestiti in scadenza entro 12 mesi")}
    long_liabilities = {k: _money(v) for k, v in liabilities.items() if k not in current_liabilities}

    total_assets = _money(sum(assets.values()))
    total_liabilities = _money(sum(liabilities.values()))
    return {
        "date": on,
        "current_assets": current_assets,
        "other_assets": other_assets,
        "current_liabilities": current_liabilities,
        "long_liabilities": long_liabilities,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": _money(total_assets - total_liabilities),
        "cash": _money(assets["Liquidità"]),
        "investments": _money(assets[INVESTMENTS]),
        "debts": debt_rows,
    }


def month_ends(count: int = 12, today: date | None = None) -> list[date]:
    """Today and the last day of each of the previous `count - 1` months (choices for the Balance Sheet)."""
    today = today or date.today()
    ends = [today]
    first = date(today.year, today.month, 1)
    for i in range(count - 1):
        ends.append(add_months(first, -i) - timedelta(days=1))
    return ends


# ── Snapshots ──────────────────────────────────────────────────────────────────

def take_snapshot(label: str | None = None, on: date | None = None) -> Snapshot:
    """Save today's balance sheet, so the net worth can be followed and compared over time."""
    sheet = balance_sheet(on)
    lines = {**sheet["current_assets"], **sheet["other_assets"]}
    liabilities = {**sheet["current_liabilities"], **sheet["long_liabilities"]}
    snapshot = Snapshot(
        taken_on=sheet["date"],
        label=label,
        cash=sheet["cash"],
        investments=sheet["investments"],
        other_assets=_money(sheet["total_assets"] - sheet["cash"] - sheet["investments"]),
        liabilities=sheet["total_liabilities"],
        net_worth=sheet["net_worth"],
        detail={"assets": lines, "liabilities": liabilities,
                "holdings": [{"name": h.name, "asset_class": h.asset_class, "value": _money(h.value)}
                             for h in holdings_on(sheet["date"])],
                "debts": sheet["debts"]},
    )
    db.session.add(snapshot)
    db.session.commit()
    return snapshot


def net_worth_trend(months: int = 12, today: date | None = None) -> dict:
    """Net worth at the end of each of the last `months` months (holdings at their latest price)."""
    ends = list(reversed(month_ends(months, today)))
    return {"labels": [d.strftime("%m/%y") if i < len(ends) - 1 else "Oggi" for i, d in enumerate(ends)],
            "data": [balance_sheet(d)["net_worth"] for d in ends]}
