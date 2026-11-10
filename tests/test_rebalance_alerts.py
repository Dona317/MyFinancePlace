"""
F51: rebalancing reminders tied to events — new liquidity on the securities accounts, a PAC instalment coming,
a periodic check, a sharp market move — on top of the rules of F19e (they show in the bell and on the desktop).
"""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.portfolio_model import InvestmentPlan, PortfolioRule
from app.models.wealth import Holding, HoldingPrice
from app.services import portfolio_rules, securities


@pytest.fixture()
def book(app, db):
    directa = Account(name="Directa", kind="other", opening_balance=Decimal(2500))
    etf = Holding(name="All-World", asset_class="ETF", quantity=10, avg_price=100, current_price=Decimal(90),
                  price_date=date(2026, 3, 10), opening_quantity=10, opening_price=100)
    db.session.add_all([directa, etf])
    db.session.commit()
    with app.test_request_context():
        securities.for_settlement(directa)
        db.session.commit()
    return directa, etf


def _alerts(app, kind, threshold, today):
    PortfolioRule.query.delete()
    from app.extensions import db
    db.session.add(PortfolioRule(kind=kind, threshold=Decimal(threshold)))
    db.session.commit()
    with app.test_request_context():
        return portfolio_rules.evaluate(today)


def test_new_cash_on_the_securities_accounts(app, db, book):
    (alert,) = _alerts(app, "new_cash", 1000, date(2026, 3, 10))
    assert "da investire su «Titoli Directa»" in alert.title and "amount=2500.00" in alert.url
    assert _alerts(app, "new_cash", 3000, date(2026, 3, 10)) == []


def test_a_pac_instalment_coming(app, db, book):
    directa, _etf = book
    db.session.add(InvestmentPlan(name="PAC mondo", amount=Decimal(300), frequency="monthly", day=5,
                                  account_id=directa.id, start=date(2026, 1, 1)))
    db.session.commit()
    (alert,) = _alerts(app, "pac_soon", 7, date(2026, 3, 30))  # next month's instalment, on the 5th
    assert "05/04/2026" in alert.title and "/plans/" in alert.url
    assert _alerts(app, "pac_soon", 3, date(2026, 3, 30)) == []
    plan = InvestmentPlan.query.one()
    plan.last_done = "2026-04"
    db.session.commit()
    assert _alerts(app, "pac_soon", 7, date(2026, 3, 30)) == []  # already done


def test_a_periodic_check(app, db, book):
    assert len(_alerts(app, "calendar", 3, date(2026, 4, 2))) == 1  # April starts a quarter
    assert _alerts(app, "calendar", 3, date(2026, 5, 2)) == []
    assert len(_alerts(app, "calendar", 1, date(2026, 5, 2))) == 1


def test_a_sharp_market_move(app, db, book):
    _directa, etf = book
    db.session.add(HoldingPrice(holding_id=etf.id, on=date(2026, 3, 2), price=Decimal(100)))
    db.session.commit()
    (alert,) = _alerts(app, "market_move", 5, date(2026, 3, 10))  # 100 → 90 in a week: −10 %
    assert "-10,0 %" in alert.title
    assert _alerts(app, "market_move", 15, date(2026, 3, 10)) == []


@pytest.mark.parametrize("kind, threshold, message", [
    ("calendar", 2, "1, 3, 6 o 12"), ("pac_soon", 40, "da 1 a 31"), ("market_move", 150, "da 0 a 100")])
def test_thresholds_are_checked(app, kind, threshold, message):
    with app.test_request_context(), pytest.raises(portfolio_rules.RuleError, match=message):
        portfolio_rules.validate(kind, None, Decimal(threshold))
