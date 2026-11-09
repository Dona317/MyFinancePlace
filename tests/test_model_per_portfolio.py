"""
F50: one model portfolio per portfolio. A model can be the one of a portfolio (its positions, on all its securities
accounts) or of all the investments together; each scope has its own active model, its own rebalancing, its orders
recorded in that portfolio and its own drift alerts.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.portfolio_model import PortfolioRule, PortfolioTemplate
from app.models.securities import Portfolio
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import portfolio_models, portfolio_ops, portfolio_rules
from app.services.portfolio_ops import Operation


@pytest.fixture()
def book(app, db):
    directa = Account(name="Directa", kind="other", opening_balance=Decimal(10000))
    world = Holding(name="All-World", asset_class="ETF", quantity=0, avg_price=0, current_price=Decimal(100),
                    opening_quantity=0, opening_price=0)
    bonds = Holding(name="Global Agg", asset_class="ETF", quantity=0, avg_price=0, current_price=Decimal(5),
                    opening_quantity=0, opening_price=0)
    pension, house = Portfolio(name="Pensione"), Portfolio(name="Casa")
    db.session.add_all([directa, world, bonds, pension, house])
    db.session.commit()
    with app.test_request_context():
        for holding, units, price, folio in ((world, 10, 100, pension), (bonds, 400, 5, house),
                                             (bonds, 50, 5, pension)):
            portfolio_ops.record(holding, Operation("buy", date(2025, 3, 1), directa, units=Decimal(units),
                                                    price=Decimal(price), portfolio=folio))
        db.session.commit()
    return directa, world, bonds, pension, house


def _model(client, name, folio, world, bonds):
    client.post("/portfolio/models/new", data={
        "name": name, "band": "5", "portfolio_id": folio.id if folio else "", "rows": "2",
        "label-0": "Azioni", "target-0": "80", "holdings-0": world.id,
        "label-1": "Obbligazioni", "target-1": "20", "holdings-1": bonds.id})
    return PortfolioTemplate.query.filter_by(name=name).one()


def test_each_portfolio_has_its_active_model(client, db, book):
    _directa, world, bonds, pension, house = book
    general = _model(client, "Tutto 80/20", None, world, bonds)
    mine = _model(client, "Pensione 80/20", pension, world, bonds)
    other = _model(client, "Pensione 60/40", pension, world, bonds)
    assert (general.active, mine.active, other.active) == (True, True, False)  # the first of each scope
    assert portfolio_models.active() == general and portfolio_models.active(pension.id) == mine
    assert portfolio_models.active(house.id) is None
    client.post(f"/portfolio/models/{other.id}/activate")
    assert (general.active, mine.active, other.active) == (True, False, True)  # only its own scope changes
    listing = client.get("/portfolio/models").text
    assert "Tutti gli investimenti" in listing and "Pensione" in listing


def test_the_rebalancing_of_a_portfolio_looks_at_its_positions_and_trades_for_it(client, db, book):
    directa, world, bonds, pension, _house = book
    _model(client, "Pensione 80/20", pension, world, bonds)
    page = client.get(f"/portfolio/rebalance?portfolio={pension.id}&mode=full").text
    assert "1.250,00" in page  # pension: 1000 of shares + 250 of bonds (not the house's 2000)
    orders = client.get(f"/portfolio/rebalance/orders?portfolio={pension.id}&mode=full").text
    assert f'name="portfolio" value="{pension.id}"' in orders
    client.post("/portfolio/rebalance/orders", data={
        "portfolio": pension.id, "portfolio_id": pension.id, "mode": "full", "rows": "1", "on": "2025-06-02",
        "account_id": directa.id, "do-0": "1", "holding-0": bonds.id, "side-0": "buy", "units-0": "10",
        "price-0": "5"})
    bought = Transaction.query.filter(Transaction.notes == "Ribilanciamento «Pensione 80/20»").one()
    assert bought.portfolio_id == pension.id
    assert client.get("/portfolio/rebalance?portfolio=999").status_code == 302  # no model there: to the models


def test_drift_alerts_for_every_portfolio_model(app, client, db, book):
    _directa, world, bonds, pension, house = book
    _model(client, "Pensione 50/50", pension, world, bonds)
    template = PortfolioTemplate.query.one()
    template.slots[0].target, template.slots[1].target = Decimal(50), Decimal(50)
    db.session.add(PortfolioRule(kind="drift"))
    db.session.commit()
    with app.test_request_context():
        alerts = portfolio_rules.evaluate(date(2025, 6, 2))
    assert alerts and all("(Pensione)" in a.title for a in alerts)
    assert all(f"portfolio={pension.id}" in a.url for a in alerts)
    assert house.id != pension.id
