"""
F48 (D13): the portfolio's overview page and the two investment blocks of the general dashboard.
"""
from datetime import date, timedelta
from decimal import Decimal

from app.models.account import Account
from app.models.portfolio_model import InvestmentPlan, PortfolioRule
from app.models.wealth import Holding, HoldingPrice
from app.services import portfolio_ops, portfolio_overview
from app.services.portfolio_ops import Operation


def _book(app, db):
    directa = Account(name="Directa", kind="other", opening_balance=Decimal(3000))
    etf = Holding(name="All-World", asset_class="ETF", quantity=0, avg_price=0, opening_quantity=0, opening_price=0)
    gold = Holding(name="Physical Gold ETC", asset_class="ETF", quantity=0, avg_price=0, opening_quantity=0,
                   opening_price=0)
    db.session.add_all([directa, etf, gold])
    db.session.commit()
    today = date.today()
    with app.test_request_context():
        portfolio_ops.record(etf, Operation("buy", today - timedelta(days=70), directa, units=Decimal(10),
                                            price=Decimal(100), fee=Decimal(2)))
        portfolio_ops.record(gold, Operation("buy", today - timedelta(days=70), directa, units=Decimal(5),
                                             price=Decimal(200)))
        portfolio_ops.record(etf, Operation("sell", today - timedelta(days=1), directa, units=Decimal(2),
                                            price=Decimal(120)))
        portfolio_ops.record(etf, Operation("dividend", today - timedelta(days=1), directa, amount=Decimal(7)))
        db.session.commit()
    db.session.add(HoldingPrice(holding_id=gold.id, on=today, price=Decimal(180)))
    gold.current_price, gold.price_date = Decimal(180), today
    db.session.add(InvestmentPlan(name="PAC", amount=Decimal(200), frequency="monthly", day=today.day,
                                  account_id=directa.id, start=today - timedelta(days=400)))
    db.session.add(PortfolioRule(kind="new_cash", threshold=Decimal(100)))
    db.session.commit()
    return etf, gold


def test_overview_figures(app, db):
    etf, gold = _book(app, db)
    with app.test_request_context():
        o = portfolio_overview.overview()
    assert o["value"] == 8 * 120 + 5 * 180  # the sale's price is the ETF's newest
    assert o["fees_year"] >= 2 and o["income_year"] == 7 and o["realized_year"] != 0
    assert [h.name for h in o["best"]][0] == "All-World" and o["worst"][0].name == "Physical Gold ETC"
    assert dict(o["classes"]) == {"Azionario": 960.0, "Oro e metalli preziosi": 900.0}
    assert any(e["kind"] == "pac" for e in o["events"]) and any(e["kind"] == "alert" for e in o["events"])
    assert o["cash"] > 0 and len(o["dossiers"]) == 1 and o["orders"][0].kind in ("dividend", "sell")


def test_overview_page_and_dashboard_blocks(client, db):
    _book(client.application, db)
    page = client.get("/portfolio/overview")
    assert page.status_code == 200 and "Panoramica investimenti" in page.text and "ovClassChart" in page.text
    assert "Rata del PAC" in page.text and "Ultimi ordini" in page.text
    dash = client.get("/dashboard").text
    assert "Investimenti in breve" in dash and "dashInvClassChart" in dash
    assert portfolio_overview.dashboard_blocks()["empty"] is False


def test_empty_portfolio(client, db):
    assert client.get("/portfolio/overview").status_code == 200
    assert portfolio_overview.dashboard_blocks() == {"empty": True}
    assert "Nessun investimento" in client.get("/dashboard").text
