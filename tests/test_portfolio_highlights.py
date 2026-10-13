"""F22: the portfolio at a glance."""
from datetime import date, timedelta
from decimal import Decimal

from app.models.wealth import Holding, HoldingPrice
from app.services import portfolio_highlights as hl
from app.services import portfolio_models
from tests.conftest import make_tx

TODAY = date(2026, 10, 13)


def _book(db):
    up = Holding(name="Su", asset_class="ETF", quantity=10, avg_price=100, current_price=130, price_date=TODAY)
    down = Holding(name="Giù", asset_class="Azione", quantity=5, avg_price=100, current_price=80,
                   price_date=TODAY - timedelta(days=40))
    flat = Holding(name="Fermo", asset_class="Obbligazione", quantity=1, avg_price=1000, current_price=1000,
                   price_source="manual")
    new = Holding(name="Nuovo", asset_class="ETF", quantity=1, avg_price=50, current_price=60, price_date=TODAY,
                  purchase_date=date(2026, 6, 1))
    house = Holding(name="Casa", asset_class="Immobile", quantity=1, avg_price=1, current_price=1)
    db.session.add_all([up, down, flat, new, house])
    db.session.flush()
    for h, price in ((up, 100), (down, 100), (new, 40)):
        db.session.add(HoldingPrice(holding_id=h.id, on=date(2025, 12, 31), price=price))
    db.session.add(make_tx(date=date(2026, 3, 1), description="Cedola", amount=24, type="income", holding_id=flat.id,
                           category="Interessi"))
    db.session.commit()
    return up, down, flat, new


def test_movers_heaviest_and_stale(db):
    up, down, flat, new = _book(db)
    moves = hl.movers([up, down, flat, new], date(2026, 1, 1))
    assert [(m.holding.name, m.pct, m.gain) for m in moves["best"]] == [("Su", 30.0, 300.0)]  # «Nuovo» was not held yet
    assert [(m.holding.name, m.pct) for m in moves["worst"]] == [("Giù", -20.0)]
    heavy = hl.heaviest([up, down, flat])
    assert [(h.name, share) for h, share in heavy["rows"]] == [("Su", 48.1), ("Fermo", 37.0), ("Giù", 14.8)]
    assert heavy["top_share"] == 99.9 and hl.heaviest([])["rows"] == []
    assert [(h.name, why) for h, why in hl.stale([up, down, flat, new], TODAY)] == [("Giù", "old"), ("Fermo", "manual")]


def test_whole_page(client, db):
    up, down, flat, new = _book(db)
    data = hl.highlights(TODAY)
    assert data["model"] is None and data["income"]["next_12"] == Decimal(24)
    template = portfolio_models.copy_ready(next(iter(portfolio_models.READY)))
    portfolio_models.activate(template)
    db.session.commit()
    assert hl.highlights(TODAY)["model"]["template"] == template
    page = client.get("/portfolio/highlights").get_data(as_text=True)
    assert "In evidenza" in page and "Su" in page and "Distanza dal modello" in page and "Prezzi da controllare" in page


def test_empty(client, db):
    assert "Nessun investimento" in client.get("/portfolio/highlights").get_data(as_text=True)
