"""The reconciliation (F104) and the reversals (F108) re-align the accounts: they are in the balances, never in the
analyses — the month's savings, the daily rhythm, the monthly chart, the flows (22 Nov 2026: the reconciliation was
still counted in «Risparmio del mese»)."""
from datetime import date

from app.models.account import Account
from app.services import account_flows, accounts, analytics, dashboard_charts
from app.services.periods import month_bounds
from tests.conftest import make_tx


def _month(db):
    today = date.today()
    conto = Account(name="Conto", kind="current")
    db.session.add(conto)
    db.session.commit()
    category = accounts.reconciliation_category()
    db.session.add_all([
        make_tx(date=today, description="Stipendio", amount=1000, type="income", category="Stipendio", account_id=conto.id),
        make_tx(date=today, description="Spesa", amount=200, category="Alimentari", account_id=conto.id),
        make_tx(date=today, description="Riconciliazione", amount=5000, category=category, account_id=conto.id),
    ])
    db.session.commit()
    return today, conto


def test_the_reconciliation_is_not_a_saving_nor_a_spending(db):
    today, conto = _month(db)
    saving = dashboard_charts.month_saving(today, {"income": [1000], "expenses": [200]})
    assert saving["rate"] == 80.0 and saving["saved"] == 800
    start, end = month_bounds(today.year, today.month)
    assert sum(dashboard_charts._by_day("expense", start, end).values()) == 200
    series = analytics.monthly_series(today.year)
    assert series["expenses"][today.month - 1] == 200 and series["income"][today.month - 1] == 1000
    flows = account_flows.flows(start, end)
    assert sum(e["value"] for e in flows["edges"]) == 1200
    assert accounts.balance(conto) == -4200  # the balance still counts it: that is what it is for


def test_negative_liquidity_is_red(client, db):
    _month(db)
    html = client.get("/accounts/").get_data(as_text=True)
    assert 'class="stat stat-negative"' in html
