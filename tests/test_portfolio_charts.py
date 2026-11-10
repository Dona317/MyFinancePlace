"""
G40, G41, G50: the price of a holding with its operations, the weights against the targets and their tolerance bands,
the treemap of the allocation — the data handed to the charts and the pages that draw them.
"""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.account import Account
from app.models.wealth import Holding, HoldingPrice
from app.services import portfolio_charts, portfolio_models, portfolio_ops, wealth
from app.services.portfolio_ops import Operation

TREEMAP_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "vendor" / "chartjs-chart-treemap.min.js"


@pytest.fixture()
def traded(app, db):
    broker = Account(name="Directa", kind="other")
    etf = Holding(name="All-World", ticker="VWCE.DE", asset_class="ETF", quantity=10, avg_price=100,
                  opening_quantity=10, opening_price=100, opening_date=date(2025, 1, 2))
    db.session.add_all([broker, etf])
    db.session.flush()
    db.session.add_all([HoldingPrice(holding_id=etf.id, on=date(2025, 1, 2), price=100),
                        HoldingPrice(holding_id=etf.id, on=date(2025, 3, 3), price=110)])
    with app.test_request_context():
        portfolio_ops.record(etf, Operation("buy", date(2025, 6, 2), broker, units=Decimal(10), price=Decimal(120)))
        portfolio_ops.record(etf, Operation("sell", date(2025, 9, 1), broker, units=Decimal(5), price=Decimal(130)))
        portfolio_ops.record(etf, Operation("dividend", date(2025, 10, 15), broker, amount=Decimal("12.40")))
        portfolio_ops.record(etf, Operation("coupon", date(2024, 12, 1), broker, amount=Decimal("1")))
        portfolio_ops.record(etf, Operation("tax", date(2025, 12, 31), broker, amount=Decimal("2")))
    db.session.commit()
    return etf


def test_price_chart_has_the_operations_as_markers(app, db, traded):
    with app.test_request_context():
        chart = portfolio_charts.price_chart(traded, wealth.price_history(traded))
    # the days of the prices and of the operations on one axis (the tax is no marker)
    assert chart["labels"] == ["2024-12-01", "2025-01-02", "2025-03-03", "2025-06-02", "2025-09-01", "2025-10-15"]
    assert chart["data"] == [None, 100.0, 110.0, 120.0, 130.0, None]  # the trades' prices went into the history
    assert chart["prices"] == 4
    assert chart["buys"] == [{"x": "2025-06-02", "y": 120.0, "units": 10.0}]
    assert chart["sells"] == [{"x": "2025-09-01", "y": 130.0, "units": 5.0}]
    # on the price line: the latest price before the day, or the first one after it
    assert chart["income"] == [{"x": "2024-12-01", "y": 100.0, "amount": 1.0, "kind": "coupon"},
                               {"x": "2025-10-15", "y": 130.0, "amount": 12.4, "kind": "dividend"}]
    assert chart["avg_price"] == 110.0  # (1000 + 1200) / 20, a sale keeps the average


def test_price_chart_without_units_or_prices(app, db):
    empty = Holding(name="Venduto", asset_class="ETF", quantity=0, avg_price=50, opening_quantity=0)
    db.session.add(empty)
    db.session.commit()
    chart = portfolio_charts.price_chart(empty, [])
    assert chart == {"labels": [], "data": [], "prices": 0, "buys": [], "sells": [], "income": [], "avg_price": None}


def test_detail_page_draws_the_price_with_operations(client, db, traded):
    page = client.get(f"/portfolio/{traded.id}").get_data(as_text=True)
    assert "makePriceOpsChart('priceChart'" in page and '"avg_price": 110.0' in page
    assert '"sells": [{"units": 5.0, "x": "2025-09-01", "y": 130.0}]' in page
    assert "Prezzo medio di carico" in page and "info-tip" in page


def test_detail_page_without_a_price_history_has_no_chart(client, db):
    holding = Holding(name="Nuovo", asset_class="ETF", quantity=1, avg_price=10, current_price=10)
    db.session.add(holding)
    db.session.commit()
    page = client.get(f"/portfolio/{holding.id}").get_data(as_text=True)
    assert page and "makePriceOpsChart(" not in page


@pytest.fixture()
def book(db):
    world = Holding(name="All-World", quantity=700, avg_price=10, current_price=10, asset_class="ETF",
                    isin="IE00BK5BQT80", ticker="VWCE.DE")
    bonds = Holding(name="Global Agg", quantity=200, avg_price=10, current_price=10, asset_class="ETF",
                    ticker="AGGH.MI")
    enel = Holding(name="Enel", quantity=100, avg_price=10, current_price=10, asset_class="Azione")
    db.session.add_all([world, bonds, enel])
    db.session.commit()
    return world, bonds, enel


def test_target_bands_of_a_plan(app, db, book):
    with app.test_request_context():
        template = portfolio_models.copy_ready("60-40")
        template.band = Decimal(15)
        db.session.commit()
        plan = portfolio_models.rebalance(template)
        bands = portfolio_charts.target_bands(plan)
    assert bands == {"labels": ["Azioni globali", "Obbligazioni globali", "Fuori dal modello"],
                     "weight": [70.0, 20.0, 10.0], "target": [60.0, 40.0, 0.0],
                     "band": [[45.0, 75.0], [25.0, 55.0], [0.0, 15.0]],  # never below zero
                     "off": [False, True, False], "tolerance": 15.0}


def test_rebalance_page_draws_the_bands(client, db, book):
    with client.application.test_request_context():
        portfolio_models.copy_ready("60-40")
        db.session.commit()
    page = client.get("/portfolio/rebalance").get_data(as_text=True)
    assert "makeTargetBandChart('targetBandChart'" in page and '"band": [[55.0, 65.0]' in page
    assert "vendor/chart.umd.min.js" in page and "chartjs-chart-treemap" not in page


def test_allocation_tree_by_class_then_holding(app, db, book):
    world, bonds, enel = book
    gone = Holding(name="Venduto", quantity=0, avg_price=10, current_price=10, asset_class="ETF")
    with app.test_request_context():
        tree = portfolio_charts.allocation_tree([enel, bonds, world, gone])
    # equities (All-World 7.000 + Enel 1.000) before bonds (2.000); the empty holding is left out
    assert tree == [{"asset_class": "Azionario", "name": "All-World", "value": 7000.0},
                    {"asset_class": "Azionario", "name": "Enel", "value": 1000.0},
                    {"asset_class": "Obbligazionario", "name": "Global Agg", "value": 2000.0}]


def test_positions_page_loads_the_treemap(client, db, book):
    page = client.get("/portfolio/").get_data(as_text=True)
    assert "vendor/chartjs-chart-treemap.min.js" in page and "makeTreemapChart('allocationTreemap'" in page
    assert '"asset_class": "Obbligazionario"' in page


def test_positions_page_without_holdings_has_no_treemap(client, db):
    page = client.get("/portfolio/").get_data(as_text=True)
    assert "makeTreemapChart(" not in page and 'id="allocationTreemap"' not in page


def test_treemap_plugin_is_vendored():
    text = TREEMAP_JS.read_text(encoding="utf-8")
    assert "chartjs-chart-treemap" in text and "MIT" in text[:400] and "treemap" in text
    assert len(text) > 10_000
