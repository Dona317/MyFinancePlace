"""F5: the price history of each holding — past balance sheets value it at the price it had then."""
import io
import json
import zipfile
from datetime import date, timedelta
from decimal import Decimal

from app.models.wealth import Holding, HoldingPrice
from app.services import backup, wealth


def _etf(db, quantity=10, price="120"):
    holding = Holding(name="ETF World", ticker="VWCE", asset_class="ETF", quantity=Decimal(quantity),
                      avg_price=Decimal(100), current_price=Decimal(price), price_date=date.today(),
                      purchase_date=date(2025, 1, 10))
    db.session.add(holding)
    db.session.commit()
    return holding


def test_past_balance_sheets_use_the_price_of_then(app, db):
    etf = _etf(db)
    with app.test_request_context():
        assert wealth.balance_sheet(date(2025, 6, 30))["investments"] == 1200  # no history yet: current price
        wealth.record_price(etf, Decimal(100), date(2025, 3, 31))
        wealth.record_price(etf, Decimal(110), date(2025, 6, 30))
        db.session.commit()
        assert wealth.balance_sheet(date(2025, 6, 30))["investments"] == 1100
        assert wealth.balance_sheet(date(2025, 5, 15))["investments"] == 1000  # the latest known by then
        assert wealth.balance_sheet(date(2025, 2, 1))["investments"] == 1200  # before the first price: current one
        assert wealth.balance_sheet()["investments"] == 1200  # today: the current price
        trend = wealth.net_worth_trend(months=24)["data"]
    assert len(set(trend)) > 1


def test_record_price_moves_the_current_price_only_forward(app, db):
    etf = _etf(db)
    with app.test_request_context():
        wealth.record_price(etf, Decimal(90), date.today() - timedelta(days=30))
        assert etf.current_price == Decimal(120)  # an older price leaves the current one alone
        wealth.record_price(etf, Decimal(130))
        wealth.record_price(etf, Decimal(131))  # the same day: corrected, not doubled
        db.session.commit()
    assert etf.current_price == Decimal(131) and HoldingPrice.query.count() == 2


def test_removing_a_price_falls_back_to_the_latest_left(app, db):
    etf = _etf(db)
    with app.test_request_context():
        wealth.record_price(etf, Decimal(100), date(2025, 3, 31))
        wealth.record_price(etf, Decimal(140))
        db.session.commit()
        newest = HoldingPrice.query.filter_by(price=Decimal(140)).one()
        wealth.remove_price(newest)
        db.session.commit()
    assert etf.current_price == Decimal(100) and etf.price_date == date(2025, 3, 31)
    with app.test_request_context():
        wealth.remove_price(HoldingPrice.query.one())  # the last one: the current price stays as it was
        db.session.commit()
    assert etf.current_price == Decimal(100)


def test_parse_prices():
    points, unread = wealth.parse_prices("31/01/2026;101,20\n2026-02-28\t102.5\n31/03/2026 1.234,56\nboh\n\n30/04/2026;-3")
    assert points == [(date(2026, 1, 31), Decimal("101.20")), (date(2026, 2, 28), Decimal("102.5")),
                      (date(2026, 3, 31), Decimal("1234.56"))]
    assert unread == ["boh", "30/04/2026;-3"]


def test_history_page(client, db):
    etf = _etf(db)
    url = f"/portfolio/{etf.id}/history"
    assert "Nessun prezzo registrato" in client.get(url).get_data(as_text=True)
    client.post(url, data={"on": "2025-03-31", "price": "100"})
    client.post(url, data={"lines": "30/06/2025;110\n30/09/2025;115\nnon valida"}, follow_redirects=True)
    html = client.get(url).get_data(as_text=True)
    assert HoldingPrice.query.count() == 3 and "priceChart" in html and "Prezzi registrati (3)" in html
    assert "maggiore di zero" in client.post(url, data={"on": "2025-01-31", "price": "0"},
                                             follow_redirects=True).get_data(as_text=True)
    assert "Data" in client.post(url, data={"price": "5"}, follow_redirects=True).get_data(as_text=True)
    point = HoldingPrice.query.filter_by(price=Decimal(110)).one()
    client.post(f"/portfolio/prices/{point.id}/delete")
    assert HoldingPrice.query.count() == 2
    assert client.get(f"/portfolio/{etf.id + 99}/history").status_code == 404


def test_update_prices_with_a_date_and_from_the_form(client, db):
    etf = _etf(db)
    client.post("/portfolio/prices", data={"on": "2025-12-31", f"price-{etf.id}": "125"})
    assert HoldingPrice.query.one().on == date(2025, 12, 31) and etf.current_price == Decimal(120)
    future = (date.today() + timedelta(days=3)).isoformat()
    html = client.post("/portfolio/prices", data={"on": future, f"price-{etf.id}": "1"}).get_data(as_text=True)
    assert "futuro" in html and HoldingPrice.query.count() == 1
    client.post(f"/portfolio/{etf.id}/edit", data={"name": "ETF World", "asset_class": "ETF", "quantity": "10",
                                                   "avg_price": "100", "current_price": "133"})
    assert etf.current_price == Decimal(133) and HoldingPrice.query.count() == 2
    assert "Data dei prezzi" in client.get("/portfolio/prices").get_data(as_text=True)


def test_backup_keeps_the_history(client, db):
    etf = _etf(db)
    with client.application.test_request_context():
        wealth.record_price(etf, Decimal(100), date(2025, 3, 31))
        db.session.commit()
    with zipfile.ZipFile(io.BytesIO(client.get("/export/backup").data)) as archive:
        data = json.loads(archive.read("backup.json"))
    assert data["tables"]["holding_prices"][0]["price"] in (100, 100.0, "100.000000")
    HoldingPrice.query.delete()
    db.session.commit()
    backup.restore(data, {})
    assert HoldingPrice.query.one().on == date(2025, 3, 31)
