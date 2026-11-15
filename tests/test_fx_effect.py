"""
F43: prices kept in their own currency with the rate used; F49: the return of a holding quoted in another currency
split into what the instrument did and what the exchange rate did.
"""
from datetime import date
from decimal import Decimal

from app.models.currency import ExchangeRate
from app.models.wealth import Holding, HoldingPrice
from app.services import fx_effect, price_feed, wealth
from tests.test_instruments import _with_history
from tests.test_price_feed import _yahoo, web  # noqa: F401 - web is a fixture


def test_a_price_read_in_dollars_keeps_its_quote_and_rate(app, db, web):  # noqa: F811
    answers, _ = web
    answers["chart/AAPL"] = _with_history(220.0, [200.0, 210.0], code="USD")
    db.session.add(ExchangeRate(currency="USD", on=date(2025, 1, 1), rate=Decimal("0.9")))
    apple = Holding(name="Apple", ticker="AAPL", asset_class="Azione", quantity=10, avg_price=150)
    db.session.add(apple)
    db.session.commit()
    with app.test_request_context():
        (result,) = price_feed.update_all([apple])
        db.session.commit()
    assert result.error is None and result.native == (Decimal("220.000000"), "USD")
    points = HoldingPrice.query.filter_by(holding_id=apple.id).order_by(HoldingPrice.on).all()
    assert len(points) == 3 and all(p.currency == "USD" and p.fx_rate == Decimal("0.9") for p in points)
    assert [p.price_ccy for p in points] == [Decimal(200), Decimal(210), Decimal(220)]
    assert points[-1].price == Decimal("198")  # 220 × 0,90


def test_pence_and_euro(app, db, web):  # noqa: F811
    answers, _ = web
    answers["chart/VUSA.L"] = _yahoo(7000, "GBp")
    answers["chart/VWCE.DE"] = _yahoo(131.2)
    db.session.add(ExchangeRate(currency="GBP", on=date(2025, 1, 1), rate=Decimal("1.2")))
    sp = Holding(name="S&P", ticker="VUSA.L", asset_class="ETF", quantity=1, avg_price=70)
    world = Holding(name="World", ticker="VWCE.DE", asset_class="ETF", quantity=1, avg_price=100)
    db.session.add_all([sp, world])
    db.session.commit()
    with app.test_request_context():
        price_feed.update_all([sp, world])
        db.session.commit()
    gbp = HoldingPrice.query.filter_by(holding_id=sp.id).one()
    assert (gbp.price_ccy, gbp.currency, gbp.price) == (Decimal(70), "GBP", Decimal(84))  # pence → pounds
    eur = HoldingPrice.query.filter_by(holding_id=world.id).one()
    assert (eur.price_ccy, eur.currency, eur.fx_rate) == (None, None, None)


def test_a_price_in_euro_clears_the_quote_of_that_day(app, db):
    h = Holding(name="Apple", asset_class="Azione", currency="USD", quantity=1, avg_price=150)
    db.session.add(h)
    db.session.commit()
    with app.test_request_context():
        wealth.record_price(h, Decimal(180), date(2026, 1, 5), Decimal(200), "USD")
        wealth.record_price(h, Decimal(181), date(2026, 1, 5))  # a trade's price, typed in euro
        db.session.commit()
    point = HoldingPrice.query.one()
    assert (point.price, point.price_ccy, point.fx_rate) == (Decimal(181), None, None)


def _quoted(db, holding, rows):
    with db.session.no_autoflush:
        for on, native, rate in rows:
            wealth.record_price(holding, (Decimal(native) * Decimal(rate)).quantize(Decimal("0.0001")), on,
                                Decimal(native), "USD")
    db.session.commit()


def test_the_return_split_between_the_instrument_and_the_currency(app, client, db):
    apple = Holding(name="Apple", asset_class="Azione", currency="USD", quantity=10, avg_price=180,
                    purchase_date=date(2025, 6, 1))
    world = Holding(name="World", asset_class="ETF", currency="EUR", quantity=5, avg_price=100, current_price=110)
    db.session.add_all([apple, world])
    db.session.commit()
    with app.test_request_context():
        _quoted(db, apple, [(date(2025, 1, 2), 150, "0.95"),          # before the purchase: not counted
                            (date(2025, 6, 2), 200, "0.90"), (date(2026, 6, 1), 220, "0.85")])
        effect = fx_effect.of_holding(apple)
        assert fx_effect.of_holding(world) is None
    assert (effect.currency, effect.start, effect.end) == ("USD", date(2025, 6, 2), date(2026, 6, 1))
    assert round(effect.local, 4) == 0.1 and round(effect.fx, 4) == -0.0556
    assert round(effect.total, 4) == round(1.1 * (0.85 / 0.9) - 1, 4)
    # value today 10 × 220 × 0,85 = 1.870 €; with the rate of then it would be 1.870 / (1 − 0,0556) → −110 € from the dollar
    assert effect.fx_euro == Decimal("-110.00")
    with app.test_request_context():
        summary = fx_effect.of_holdings([apple, world])
    assert summary.by_currency == {"USD": Decimal("-110.00")} and summary.total == Decimal("-110.00")
    page = client.get(f"/portfolio/{apple.id}").get_data(as_text=True)
    assert 'id="fx-effect"' in page and "Nella sua valuta (USD)" in page and "+10 %" in page
    page = client.get(f"/portfolio/{world.id}").get_data(as_text=True)
    assert 'id="fx-effect"' not in page


def test_one_price_only_shows_nothing(app, db):
    h = Holding(name="Nestlé", asset_class="Azione", currency="CHF", quantity=1, avg_price=90)
    db.session.add(h)
    db.session.commit()
    with app.test_request_context():
        wealth.record_price(h, Decimal(95), date(2026, 1, 5), Decimal(90), "CHF")
        db.session.commit()
        assert fx_effect.of_holding(h) is None and fx_effect.of_holdings([h]).effects == []


def test_the_returns_page_shows_the_currency_effect(app, client, db):
    apple = Holding(name="Apple", asset_class="Azione", currency="USD", quantity=10, avg_price=180,
                    purchase_date=date(2025, 6, 1))
    db.session.add(apple)
    db.session.commit()
    with app.test_request_context():
        _quoted(db, apple, [(date(2025, 6, 2), 200, "0.90"), (date(2026, 6, 1), 220, "0.85")])
    page = client.get("/portfolio/performance").get_data(as_text=True)
    assert 'id="fx-effect"' in page and "Euro dal cambio" in page and "USD" in page
