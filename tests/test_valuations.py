"""F22: assets valued by hand, and the ones that lose value every year."""
from datetime import date
from decimal import Decimal

from app.models.wealth import Holding, HoldingPrice
from app.services import settings_store, valuations, wealth


def _car(db, **values):
    car = Holding(name="Panda", asset_class="Veicolo", quantity=1, avg_price=12000, purchase_date=date(2024, 3, 10),
                  depreciation_rate=Decimal(15), **values)
    db.session.add(car)
    db.session.commit()
    return car


def test_worth():
    assert valuations.worth(Decimal(10000), Decimal(15), date(2025, 1, 1), date(2025, 1, 1)) == 10000
    one_year = valuations.worth(Decimal(10000), Decimal(15), date(2025, 1, 1), date(2026, 1, 1))
    assert abs(one_year - Decimal(8500)) < 5


def test_depreciation_from_the_purchase(db):
    car = _car(db)
    count = valuations.depreciate(car, date(2026, 3, 10))
    db.session.commit()
    points = wealth.price_history(car)
    assert count == len(points) == 25 and all(p.estimated for p in points)  # 24 months + today
    assert points[0].on == date(2024, 4, 1) and points[-1].on == date(2026, 3, 10)
    assert abs(car.current_price - Decimal(12000 * 0.85 ** 2)) < 10 and car.price_date == date(2026, 3, 10)
    # the balance sheet of a past day reads the estimate of then
    assert wealth.value_on(car, date(2025, 3, 15)) < 12000 * 0.86
    assert valuations.depreciate(Holding(name="x", asset_class="Altro", quantity=1, avg_price=1)) == 0  # no rate


def test_a_new_valuation_restarts_it(db):
    car = _car(db)
    valuations.depreciate(car, date(2026, 3, 10))
    valuations.revalue(car, Decimal(9000), date(2025, 6, 1), " listino usato ")
    valuations.depreciate(car, date(2026, 6, 1))
    db.session.commit()
    manual = HoldingPrice.query.filter_by(holding_id=car.id, estimated=False).one()
    assert manual.note == "listino usato" and manual.price == 9000
    after = [p for p in wealth.price_history(car) if p.on > date(2025, 6, 1)]
    assert after and all(p.estimated for p in after) and after[0].on == date(2025, 7, 1)
    assert abs(car.current_price - Decimal(9000 * 0.85)) < 10
    assert valuations.depreciate(car, date(2025, 6, 1)) == 0  # the valuation is today's: nothing to estimate


def test_once_a_day(db):
    car = _car(db)
    assert valuations.refresh_daily(date(2026, 3, 10)) == 25
    assert valuations.refresh_daily(date(2026, 3, 10)) == 0
    valuations.forget()
    assert not settings_store.get(valuations.LAST_RUN)
    assert valuations.refresh_daily(date(2026, 3, 10)) == 25
    assert HoldingPrice.query.filter_by(holding_id=car.id).count() == 25  # replaced, not added again


def test_pages(client, db):
    response = client.post("/portfolio/new", data={"name": "Panda", "asset_class": "Veicolo", "quantity": "1",
                                                   "avg_price": "12000", "purchase_date": "2024-03-10",
                                                   "depreciation_rate": "15"})
    assert response.status_code == 302
    car = Holding.query.filter_by(name="Panda").one()
    assert car.depreciation_rate == 15
    assert client.get("/portfolio/").status_code == 200  # writes the estimates
    page = client.get(f"/portfolio/{car.id}/history").get_data(as_text=True)
    assert "Valutazioni" in page and "stima" in page and "Perde il 15" in page
    client.post(f"/portfolio/{car.id}/history", data={"on": "2026-01-15", "price": "8000", "note": "perizia"})
    page = client.get(f"/portfolio/{car.id}/history").get_data(as_text=True)
    assert "perizia" in page
    assert "tra 0 e 99" in client.post(f"/portfolio/{car.id}/edit", data={
        "name": "Panda", "asset_class": "Veicolo", "quantity": "1", "avg_price": "12000", "depreciation_rate": "120"},
        follow_redirects=True).get_data(as_text=True)
    point = HoldingPrice.query.filter_by(holding_id=car.id, estimated=False).one()
    client.post(f"/portfolio/prices/{point.id}/delete")
    assert not settings_store.get(valuations.LAST_RUN)
    assert client.get("/dashboard").status_code == 200
    assert "Svalutazione annua" in client.get(f"/portfolio/{car.id}/edit").get_data(as_text=True)
