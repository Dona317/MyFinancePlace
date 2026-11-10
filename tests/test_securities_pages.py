"""
F42, the pages: portfolios (create, rename, the star of the default one, archive), securities accounts (always with
their liquidity), the portfolio filtered by portfolio or securities account, operations placed and sales limited to the
position, operations edited by hand, and the rebalancing turned into orders confirmed at the executed prices.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.portfolio_model import PortfolioTemplate
from app.models.securities import Portfolio, SecuritiesAccount
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import portfolio_models, portfolio_ops, securities
from app.services.portfolio_models import SlotInput
from app.services.portfolio_ops import Operation


@pytest.fixture()
def book(db):
    directa = Account(name="Directa", kind="other", opening_balance=Decimal(5000), fee_fixed=Decimal("1.5"))
    etf = Holding(name="All-World", ticker="VWCE", asset_class="ETF", quantity=10, avg_price=100,
                  current_price=Decimal(110), opening_quantity=10, opening_price=100, opening_date=date(2025, 1, 2))
    bonds = Holding(name="Global Agg", ticker="AGGH", asset_class="ETF", quantity=0, avg_price=0,
                    current_price=Decimal(5), opening_quantity=0, opening_price=0)
    db.session.add_all([directa, etf, bonds])
    db.session.commit()
    return directa, etf, bonds


def test_portfolios_created_renamed_starred_and_archived(client, db, book):
    page = client.get("/portfolio/portfolios")
    assert page.status_code == 200 and "Portafoglio principale" in page.text and "Nessun" not in page.text[:0]
    client.post("/portfolio/portfolios/new", data={"name": "Pensione", "description": "lungo periodo"})
    assert "Esiste già" in client.post("/portfolio/portfolios/new", data={"name": "pensione"},
                                       follow_redirects=True).text
    pension = Portfolio.query.filter_by(name="Pensione").one()
    client.post(f"/portfolio/portfolios/{pension.id}/rename", data={"name": "Pensione INPS bis", "description": ""})
    assert pension.name == "Pensione INPS bis" and pension.description is None
    client.post(f"/portfolio/portfolios/{pension.id}/default")
    assert [p.name for p in Portfolio.query.filter_by(is_default=True)] == ["Pensione INPS bis"]
    assert "non si elimina" in client.post(f"/portfolio/portfolios/{pension.id}/delete", follow_redirects=True).text
    main = Portfolio.query.filter_by(name="Portafoglio principale").one()
    client.post(f"/portfolio/portfolios/{main.id}/delete")
    assert main.active is False  # the ETF's opening position is in it: archived, not deleted
    client.post("/portfolio/portfolios/new", data={"name": "Vuoto"})
    empty = Portfolio.query.filter_by(name="Vuoto").one()
    client.post(f"/portfolio/portfolios/{empty.id}/delete")
    assert db.session.get(Portfolio, empty.id) is None  # nothing in it: deleted
    # one with operations is archived, its operations stay
    client.post("/portfolio/portfolios/new", data={"name": "Casa"})
    house = Portfolio.query.filter_by(name="Casa").one()
    directa, etf, _bonds = book
    with client.application.test_request_context():
        portfolio_ops.record(etf, Operation("buy", date(2025, 3, 1), directa, units=Decimal(1), price=Decimal(100),
                                            portfolio=house))
        db.session.commit()
    assert "archiviato" in client.post(f"/portfolio/portfolios/{house.id}/delete", follow_redirects=True).text
    assert house.active is False and Transaction.query.filter_by(portfolio_id=house.id).count() == 1
    client.post(f"/portfolio/portfolios/{house.id}/rename", data={"name": "Casa"})
    assert house.active is True  # saved again: back in use


def test_a_securities_account_always_has_its_liquidity(client, db, book):
    directa, etf, _bonds = book
    refused = client.post("/portfolio/dossiers/new", data={"name": "Titoli Fineco", "active": "on"})
    assert refused.status_code == 400 and "conto di liquidità" in refused.text
    saved = client.post("/portfolio/dossiers/new", data={
        "name": "Titoli Directa", "settlement_account_id": directa.id, "tax_regime": "dichiarativo", "abroad": "on",
        "fee_fixed": "1,5", "fee_percent": "0,19", "active": "on"})
    dossier = SecuritiesAccount.query.one()
    assert saved.status_code == 302 and (dossier.broker, dossier.tax_regime, dossier.abroad) == ("Directa", "dichiarativo", True)
    assert dossier.fee_percent == Decimal("0.19")
    with client.application.test_request_context():
        portfolio_ops.record(etf, Operation("buy", date(2025, 3, 1), directa, units=Decimal(10), price=Decimal(100),
                                            securities_account=dossier))
        db.session.commit()
    page = client.get(f"/portfolio/dossiers/{dossier.id}")
    assert page.status_code == 200 and "Liquidità" in page.text
    assert "4.000,00" in page.text  # 5000 − 1000 spent on the purchase: the settlement account's balance
    assert "2.000,00" in page.text  # 20 units (10 opening + 10 bought) × 100, the price of the purchase (the newest)
    listing = client.get("/portfolio/portfolios").text
    # the opening position (10 units) went to the dossier of the first trade: titoli 2000 + liquidità 4000
    assert "Titoli Directa" in listing and "6.000,00" in listing
    client.post(f"/portfolio/dossiers/{dossier.id}/edit", data={"name": "Directa SIM", "settlement_account_id": directa.id})
    assert dossier.name == "Directa SIM" and dossier.active is False
    assert client.get(f"/portfolio/dossiers/{dossier.id}/edit").status_code == 200


def test_the_portfolio_filtered_by_portfolio_and_by_securities_account(client, db, book):
    directa, etf, _bonds = book
    pension = Portfolio(name="Pensione")
    db.session.add_all([pension, Portfolio(name="Casa")])
    db.session.commit()
    with client.application.test_request_context():
        portfolio_ops.record(etf, Operation("buy", date(2025, 3, 1), directa, units=Decimal(4), price=Decimal(100),
                                            portfolio=pension))
        db.session.commit()
        dossier = SecuritiesAccount.query.one()
    every = client.get("/portfolio/").text
    assert "Tutti i portafogli" in every and "1.400,00" in every  # 14 units × 100
    only = client.get(f"/portfolio/?portfolio={pension.id}").text
    assert "€ 400,00" in only and "1.400,00" not in only  # only the 4 units bought for the pension
    in_dossier = client.get(f"/portfolio/?dossier={dossier.id}").text
    assert "1.400,00" in in_dossier  # the opening position went to the dossier of the first trade too


def test_the_operation_form_places_the_trade_and_limits_the_sale(client, db, book):
    directa, etf, _bonds = book
    pension = Portfolio(name="Pensione")
    db.session.add(pension)
    db.session.commit()
    page = client.get(f"/portfolio/{etf.id}/operation").text
    assert "Conto titoli" in page and "Pensione" in page
    client.post(f"/portfolio/{etf.id}/operation", data={"kind": "buy", "on": "2025-03-01", "units": "5",
                                                         "price": "100", "account_id": directa.id,
                                                         "portfolio_id": pension.id})
    trade = Transaction.query.filter(Transaction.units.isnot(None)).one()
    assert trade.portfolio_id == pension.id and trade.securities_account_id == SecuritiesAccount.query.one().id
    assert "Dove le hai" in client.get(f"/portfolio/{etf.id}/operation").text
    refused = client.post(f"/portfolio/{etf.id}/operation", data={"kind": "sell", "on": "2025-04-01", "units": "6",
                                                                   "price": "120", "account_id": directa.id,
                                                                   "portfolio_id": pension.id})
    assert refused.status_code == 400 and "hai solo 5 quote" in refused.text
    client.post(f"/portfolio/{etf.id}/operation", data={"kind": "sell", "on": "2025-04-01", "units": "5",
                                                         "price": "120", "account_id": directa.id,
                                                         "portfolio_id": pension.id})
    assert Transaction.query.filter(Transaction.units < 0).count() == 1


def test_an_operation_edited_by_hand_keeps_or_changes_its_place(client, db, book):
    directa, etf, _bonds = book
    pension = Portfolio(name="Pensione")
    db.session.add(pension)
    db.session.commit()
    with client.application.test_request_context():
        trade, fee = portfolio_ops.record(etf, Operation("buy", date(2025, 3, 1), directa, units=Decimal(5),
                                                         price=Decimal(100), fee=Decimal(2)))
        db.session.commit()
        default = securities.default_portfolio()
    form = client.get(f"/transactions/{trade.id}/edit").text
    assert 'name="portfolio_id"' in form and "Pensione" in form
    client.post(f"/transactions/{trade.id}/edit", data={
        "date": "2025-03-01", "description": trade.description, "amount": "", "currency": "EUR", "transfer": "on",
        "account_id": directa.id, "holding_id": etf.id, "trade_side": "buy", "units": "5", "unit_price": "101,30",
        "category": "Investimenti", "securities_account_id": trade.securities_account_id, "portfolio_id": pension.id})
    db.session.refresh(trade)
    assert trade.unit_price == Decimal("101.300000") and trade.portfolio_id == pension.id
    assert db.session.get(Transaction, fee.id).portfolio_id == pension.id  # the commission follows
    assert default.id != pension.id


def test_the_rebalancing_becomes_orders_confirmed_at_the_executed_prices(client, db, book):
    directa, etf, bonds = book
    template = PortfolioTemplate(name="60/40", band=5, active=True)
    db.session.add(template)
    portfolio_models.save(template, "60/40", "", Decimal(5), [
        SlotInput("Azioni", Decimal(60), holding_ids=[etf.id]), SlotInput("Obbligazioni", Decimal(40), holding_ids=[bonds.id])])
    template.active = True
    db.session.commit()
    assert "Prepara gli ordini" in client.get("/portfolio/rebalance?mode=full").text
    page = client.get("/portfolio/rebalance/orders?mode=full")
    assert page.status_code == 200 and "Conferma ordini eseguiti" in page.text and "Global Agg" in page.text
    assert "All-World" in page.text  # 1100 of shares: sell 440, buy 440 of bonds
    refused = client.post("/portfolio/rebalance/orders", data={"mode": "full", "rows": "2", "on": "2025-06-02"},
                          follow_redirects=True)
    assert "Nessun ordine da confermare" in refused.text
    client.post("/portfolio/rebalance/orders", data={
        "mode": "full", "rows": "2", "on": "2025-06-02", "account_id": directa.id,
        "do-0": "1", "holding-0": etf.id, "side-0": "sell", "units-0": "4", "price-0": "109,50", "fee-0": "",
        "do-1": "1", "holding-1": bonds.id, "side-1": "buy", "units-1": "87", "price-1": "5,02", "fee-1": "1,50"})
    trades = Transaction.query.filter(Transaction.units.isnot(None)).order_by(Transaction.id).all()
    assert [(t.holding_id, t.units, t.unit_price) for t in trades] == [
        (etf.id, Decimal(-4), Decimal("109.500000")), (bonds.id, Decimal(87), Decimal("5.020000"))]
    assert all(t.notes == "Ribilanciamento «60/40»" for t in trades)
    assert (etf.quantity, bonds.quantity) == (Decimal(6), Decimal(87))
    assert Transaction.query.filter(Transaction.fee_for_id == trades[1].id).one().amount == Decimal("1.50")


def test_rebalance_orders_need_a_model_and_a_date_not_in_the_future(client, db, book):
    assert client.get("/portfolio/rebalance/orders").status_code == 302
    template = PortfolioTemplate(name="Tutto", band=5)
    db.session.add(template)
    directa, etf, _bonds = book
    portfolio_models.save(template, "Tutto", "", Decimal(5), [SlotInput("Azioni", Decimal(100), holding_ids=[etf.id])])
    template.active = True
    db.session.commit()
    assert "Nessun ordine" in client.get("/portfolio/rebalance/orders?mode=full").text
    late = client.post("/portfolio/rebalance/orders", data={"rows": "1", "on": "2999-01-01", "do-0": "1",
                                                            "holding-0": etf.id, "units-0": "1", "price-0": "1"},
                       follow_redirects=True)
    assert "nel futuro" in late.text


def test_outside_the_model_each_holding_is_sold_for_what_it_holds(db, book):
    """«Fuori dal modello» holds several holdings: one sale each, never more units than it has (not all of the line's
    value in units of the biggest one)."""
    from app.routes.portfolio_templates import _proposed_orders

    _directa, etf, bonds = book
    gold = Holding(name="Oro", ticker="SGLD", asset_class="ETF", quantity=4, avg_price=150, current_price=Decimal(200))
    coin = Holding(name="Bitcoin", ticker="BTC", asset_class="Criptovaluta", quantity=Decimal("0.01"), avg_price=40000,
                   current_price=Decimal(50000))
    db.session.add_all([gold, coin])
    template = PortfolioTemplate(name="Solo azioni", band=5, active=True)
    db.session.add(template)
    portfolio_models.save(template, "Solo azioni", "", Decimal(5), [SlotInput("Azioni", Decimal(100), holding_ids=[etf.id])])
    template.active = True
    db.session.commit()
    plan = portfolio_models.rebalance(template, "full", holdings=[etf, bonds, gold, coin])
    sales = {o["holding"].name: o["units"] for o in _proposed_orders(plan) if o["side"] == "sell"}
    assert sales == {"Oro": Decimal(4), "Bitcoin": Decimal("0.01")}
