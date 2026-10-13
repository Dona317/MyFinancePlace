"""F20h: time-weighted return, volatility, maximum drawdown and the benchmark, with past quantities and prices."""
import json
from datetime import date
from decimal import Decimal

import pytest

from app.models.wealth import Holding, HoldingPrice
from app.services import performance, price_feed
from tests.conftest import make_tx

TODAY = date(2026, 4, 15)


@pytest.fixture()
def etf(db):
    h = Holding(name="ETF", asset_class="ETF", quantity=20, avg_price=100, current_price=115,
                purchase_date=date(2025, 12, 1), opening_quantity=0, opening_price=0)
    db.session.add(h)
    db.session.flush()
    for day, price in ((date(2025, 12, 31), 100), (date(2026, 1, 31), 110), (date(2026, 2, 28), 99),
                       (date(2026, 3, 31), 110), (date(2026, 4, 15), 115)):
        db.session.add(HoldingPrice(holding_id=h.id, on=day, price=price))
    # 10 bought at 100 in December, 10 more at 99 at the end of February: the TWR must not see the new money
    db.session.add_all([
        make_tx(description="Acquisto", type="transfer", category="Investimenti", amount=Decimal("1000"),
                date=date(2025, 12, 10), holding_id=h.id, units=Decimal(10), unit_price=Decimal(100)),
        make_tx(description="Acquisto", type="transfer", category="Investimenti", amount=Decimal("990"),
                date=date(2026, 2, 28), holding_id=h.id, units=Decimal(10), unit_price=Decimal(99)),
        make_tx(description="Dividendo", type="income", category="Dividendi e cedole", amount=Decimal("11"),
                date=date(2026, 3, 20), holding_id=h.id),
    ])
    db.session.commit()
    return h


def test_twr_ignores_the_timing_of_money(app, etf):
    with app.test_request_context():
        dates, returns = performance.monthly_returns([etf], TODAY)
        r = performance.report([etf], TODAY)
    # Dec: 0 → 1.000 (all new money, no gain); Jan +10 %; Feb −10 % (1.100 → 990, then 990 bought);
    # Mar 1.980 → 2.200 + 11 dividend: +11,67 %; Apr (to the 15th, today's price 115) +4,55 %
    assert [round(x * 100, 2) for x in returns] == [0.0, 10.0, -10.0, 11.67, 4.55]
    assert r.twr == round(((1.1 * 0.9 * (1 + 231 / 1980)) * (2300 / 2200) - 1) * 100, 2)
    assert r.max_drawdown == -10.0 and r.best == ("03/26", 11.67) and r.worst == ("02/26", -10.0)
    assert r.annualized is None and r.volatility > 0  # less than a year: no yearly figure
    assert r.windows["1A"] == (None, None)


def test_benchmark(app, etf):
    with app.test_request_context():
        performance.save_benchmark("VWCE.MI", {"2025-11-30": 100.0, "2026-01-31": 105.0, "2026-03-31": 120.0}, TODAY)
        r = performance.report([etf], TODAY)
    assert r.benchmark == [0.0, 5.0, 5.0, 20.0, 20.0] and r.benchmark_twr == 20.0


def test_empty(app, db):
    with app.test_request_context():
        assert performance.report([], TODAY).twr is None
        assert performance.monthly_returns([Holding(name="x", asset_class="ETF", quantity=1, avg_price=1)], TODAY) == ([], [])


def test_benchmark_download(app, monkeypatch):
    chart = {"chart": {"result": [{"meta": {"currency": "EUR"}, "timestamp": [1767225600, 1769904000, 1772323200],
                                   "indicators": {"quote": [{"close": [100.5, None, 110.25]}]}}]}}
    monkeypatch.setattr(price_feed, "_fetch", lambda url: json.dumps(chart))
    with app.test_request_context():
        assert price_feed.benchmark_history("vwce.mi") == {"2026-01-01": 100.5, "2026-03-01": 110.25}
    monkeypatch.setattr(price_feed, "_fetch", lambda url: json.dumps({"chart": {"result": []}}))
    with app.test_request_context(), pytest.raises(ValueError, match="non trovato"):
        price_feed.benchmark_history("NOPE")
    empty = {"chart": {"result": [{"meta": {"currency": "EUR"}, "timestamp": [1767225600], "indicators": {"quote": [{"close": [None]}]}}]}}
    monkeypatch.setattr(price_feed, "_fetch", lambda url: json.dumps(empty))
    with app.test_request_context(), pytest.raises(ValueError, match="nessun prezzo"):
        price_feed.benchmark_history("X")


def test_page(client, db, etf, monkeypatch):
    monkeypatch.setattr(price_feed, "benchmark_history", lambda ticker: {"2025-11-30": 100.0, "2026-03-31": 110.0})
    assert "Rendimento cumulato" in client.get("/portfolio/performance").get_data(as_text=True)
    page = client.post("/portfolio/performance", data={"ticker": "vwce.mi"}, follow_redirects=True).get_data(as_text=True)
    assert "Storico di VWCE.MI scaricato." in page
    monkeypatch.setattr(price_feed, "benchmark_history", lambda ticker: (_ for _ in ()).throw(ValueError("rete")))
    page = client.post("/portfolio/performance", data={"ticker": "X"}, follow_redirects=True).get_data(as_text=True)
    assert "Benchmark non aggiornato: rete" in page
    page = client.post("/portfolio/performance", data={"ticker": ""}, follow_redirects=True).get_data(as_text=True)
    assert "Benchmark tolto." in page


def test_page_without_history(client, db):
    assert "Servono almeno un mese di storia" in client.get("/portfolio/performance").get_data(as_text=True)


def test_windows_over_a_year(app, db):
    h = Holding(name="Lungo", asset_class="ETF", quantity=10, avg_price=100, current_price=100,
                purchase_date=date(2024, 12, 1), opening_quantity=10, opening_price=100, opening_date=date(2024, 12, 1))
    db.session.add(h)
    db.session.flush()
    price = 100.0
    for month in range(1, 16):  # +1 % a month from January 2025 to March 2026
        price *= 1.01
        year, m = 2025 + (month - 1) // 12, (month - 1) % 12 + 1
        last = date(year, m, 28)
        db.session.add(HoldingPrice(holding_id=h.id, on=last, price=round(price, 4)))
    db.session.commit()
    with app.test_request_context():
        performance.save_benchmark("X", {"2025-01-01": 10.0, "2026-03-01": 11.0}, TODAY)
        r = performance.report([h], date(2026, 3, 31))
    mine, theirs = r.windows["1A"]
    assert mine == round((1.01 ** 12 - 1) * 100, 2) and theirs is not None
    assert r.annualized is not None and r.windows["3A"] == (None, None)
