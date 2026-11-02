"""F20j: stock splits adjust the past; the portfolio's exposure by region and sector."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.transaction import Transaction
from app.models.wealth import Holding, HoldingPrice
from app.services import composition
from tests.conftest import make_tx


@pytest.fixture()
def stock(db):
    h = Holding(name="Nvidia", asset_class="Azione", quantity=15, avg_price=400, current_price=100, price_date=date(2026, 7, 1),
                opening_quantity=10, opening_price=400, opening_date=date(2025, 1, 2), region="Nord America",
                sector="Tecnologia")
    db.session.add(h)
    db.session.flush()
    db.session.add_all([
        HoldingPrice(holding_id=h.id, on=date(2026, 5, 1), price=1000),
        HoldingPrice(holding_id=h.id, on=date(2026, 7, 1), price=100),
        make_tx(description="Acquisto", type="transfer", category="Investimenti", amount=Decimal("5000"),
                date=date(2026, 3, 1), holding_id=h.id, units=Decimal(5), unit_price=Decimal(1000)),
    ])
    db.session.commit()
    return h


def test_split(app, db, stock):
    with app.test_request_context():
        adjusted = composition.split(stock, Decimal(10), date(2026, 6, 10))
        db.session.commit()
    assert adjusted == 1
    trade = Transaction.query.filter(Transaction.units.isnot(None)).one()
    assert (trade.units, trade.unit_price, trade.amount) == (Decimal(50), Decimal(100), Decimal(5000))  # same money
    prices = {p.on: p.price for p in HoldingPrice.query.all()}
    assert prices == {date(2026, 5, 1): Decimal(100), date(2026, 7, 1): Decimal(100)}  # after the day: untouched
    assert (stock.opening_quantity, stock.opening_price) == (Decimal(100), Decimal(40))
    assert (stock.quantity, stock.current_price) == (Decimal(150), Decimal(100))  # its price was already after
    assert stock.avg_price == Decimal("60.000000")  # (100 × 40 + 50 × 100) / 150
    with app.test_request_context(), pytest.raises(ValueError, match="diverso da 1"):
        composition.split(stock, Decimal(1), date(2026, 6, 10))


def test_exposure(app, db, stock):
    db.session.add_all([Holding(name="World", asset_class="ETF", quantity=10, avg_price=150, region="Globale",
                                sector="Diversificato"),
                        Holding(name="Senza", asset_class="ETF", quantity=1, avg_price=500)])
    db.session.commit()
    result = composition.exposure(Holding.query.all())
    assert result["total"] == 3500
    assert result["region"] == [("Nord America", 1500, 42.9), ("Globale", 1500, 42.9), ("Non indicato", 500, 14.3)]
    assert result["sector"][0] == ("Tecnologia", 1500, 42.9)
    assert composition.exposure([]) == {"total": 0, "region": [], "sector": []}


def test_pages(client, db, stock):
    page = client.get("/portfolio/composition").get_data(as_text=True)
    assert "Per area geografica" in page and "Nord America" in page
    page = client.post(f"/portfolio/{stock.id}/split", data={"ratio": "10", "on": "2026-06-10"},
                       follow_redirects=True).get_data(as_text=True)
    assert "Frazionamento 1:10 applicato dal 10/06/2026: 1 operazioni precedenti adeguate." in page
    page = client.post(f"/portfolio/{stock.id}/split", data={"ratio": "0", "on": "2026-06-10"},
                       follow_redirects=True).get_data(as_text=True)
    assert "diverso da 1" in page
    form = {"name": "Nvidia", "asset_class": "Azione", "quantity": "150", "avg_price": "60", "region": "Europa",
            "sector": "Inventato", "price_source": "manual"}
    client.post(f"/portfolio/{stock.id}/edit", data=form)
    db.session.refresh(stock)
    assert (stock.region, stock.sector) == ("Europa", None)
