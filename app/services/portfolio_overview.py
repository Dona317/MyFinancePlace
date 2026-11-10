"""
The portfolio's overview (F48, decision D13): one page of blocks at the top of the Portfolio — what the investments
are worth and what went into them, the returns, the split by asset class and by instrument, how far each portfolio's
model is, what is coming (PAC instalments, rule alerts), costs and taxes of the year, best and worst positions, the
securities accounts with their liquidity and the latest orders — and the two blocks of the general dashboard.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models.portfolio_model import InvestmentPlan
from app.models.transaction import Transaction
from app.services import (
    broker,
    capital_gains,
    investment_plans,
    order_register,
    performance,
    portfolio_models,
    portfolio_ops,
    portfolio_rules,
    securities,
    wealth,
)
from app.services.totals import VALUE

SHOWN = 3            # best and worst positions
EVENTS_DAYS = 31     # how far ahead the coming PAC instalments are shown
LAST_ORDERS = 5


def investments() -> list:
    return [h for h in wealth.holdings_on() if wealth.ASSET_CLASSES.get(h.asset_class, ("", False))[1]]


def _year_total(ids: list[int], start: date, end: date, *conditions) -> float:
    if not ids:
        return 0.0
    total = db.session.query(func.coalesce(func.sum(VALUE), 0)).filter(
        Transaction.holding_id.in_(ids), Transaction.date >= start, Transaction.date < end, *conditions).scalar()
    return float(total or 0)


def _fees(ids: list[int], start: date, end: date) -> float:
    trade_ids = db.session.query(Transaction.id).filter(Transaction.holding_id.in_(ids or [0]),
                                                        Transaction.units.isnot(None))
    attached = db.session.query(func.coalesce(func.sum(VALUE), 0)).filter(
        Transaction.fee_for_id.in_(trade_ids), Transaction.date >= start, Transaction.date < end).scalar()
    alone = _year_total(ids, start, end, Transaction.units.is_(None), Transaction.category == broker.FEE_CATEGORY)
    return float(attached or 0) + alone


def _events(today: date) -> list[dict]:
    """The PAC instalments of the next month, then the alerts of the rules."""
    events = []
    for plan in InvestmentPlan.query.order_by(InvestmentPlan.name):
        for month in (today.replace(day=1), (today.replace(day=1) + timedelta(days=32)).replace(day=1)):
            on = investment_plans.due_date(plan, month)
            if on is None or on < plan.start or (plan.end and on > plan.end):
                continue
            if (plan.last_done or "") >= investment_plans.period(on) or (on - today).days > EVENTS_DAYS:
                continue
            events.append({"day": on, "title": plan.name, "amount": float(plan.amount), "kind": "pac",
                           "plan_id": plan.id, "late": on < today})
            break
    events.sort(key=lambda e: e["day"])
    for alert in portfolio_rules.evaluate(today):
        events.append({"day": alert.when, "title": alert.title, "detail": alert.detail, "kind": "alert",
                       "url": alert.url, "level": alert.level})
    return events


def overview(today: date | None = None) -> dict:
    today = today or date.today()
    holdings = investments()
    ids = [h.id for h in holdings]
    summary = wealth.portfolio_summary(holdings)
    series = performance.value_series(holdings, today)
    report = performance.report(holdings, today)
    perf = portfolio_ops.performance(holdings, today) if holdings else {}
    start, end = date(today.year, 1, 1), date(today.year + 1, 1, 1)
    sales = [s for s in capital_gains.realized()[0] if s.on.year == today.year and s.holding.id in set(ids)]
    dossiers = [{"dossier": d, "value": sum(p.value for p in securities.positions(securities_account_id=d.id)),
                 "cash": securities.cash(d)} for d in securities.accounts()]
    models = []
    for template in portfolio_models.actives():
        lines, _total = portfolio_models.standing(template)
        models.append({"template": template, "lines": [line for line in lines if not line.outside],
                       "off": sum(1 for line in lines if abs(line.drift) > Decimal(template.band))})
    ranked = sorted((h for h in holdings if h.cost), key=lambda h: h.gain_pct)
    invested_now = series["invested"][-1] if series["invested"] else summary["cost"]
    return {
        "value": summary["value"], "invested": invested_now, "gain": round(summary["value"] - invested_now, 2),
        "unrealized": summary["gain"], "classes": summary["classes"], "instruments": summary["allocation"],
        "realized_year": round(float(sum((s.result for s in sales), Decimal(0))), 2),
        "income_year": round(_year_total(ids, start, end, Transaction.type == "income"), 2),
        "fees_year": round(_fees(ids, start, end), 2),
        "taxes_year": round(_year_total(ids, start, end, Transaction.type == "expense", Transaction.units.is_(None),
                                        Transaction.category == portfolio_ops.TAX_CATEGORY), 2),
        "xirr": perf.get("xirr"), "twr": report.twr, "annualized": report.annualized,
        "max_drawdown": report.max_drawdown,
        "cash": round(sum(row["cash"] for row in dossiers), 2), "dossiers": dossiers,
        "series": series, "models": models, "events": _events(today),
        "best": list(reversed(ranked[-SHOWN:])), "worst": ranked[:SHOWN],
        "orders": order_register.register().rows[:LAST_ORDERS],
        "year": today.year,
    }


def dashboard_blocks(today: date | None = None) -> dict:
    """What the general dashboard shows of the investments: the key figures and the value against the money put in."""
    today = today or date.today()
    holdings = investments()
    if not holdings:
        return {"empty": True}
    summary = wealth.portfolio_summary(holdings)
    series = performance.value_series(holdings, today)
    perf = portfolio_ops.performance(holdings, today)
    invested = series["invested"][-1] if series["invested"] else summary["cost"]
    return {"empty": False, "value": summary["value"], "invested": invested,
            "gain": round(summary["value"] - invested, 2), "xirr": perf.get("xirr"), "classes": summary["classes"],
            "series": series}
