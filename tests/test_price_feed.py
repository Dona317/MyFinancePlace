"""F5b: prices from the internet (Yahoo Finance, CoinGecko), with the network replaced by canned answers."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.models.currency import ExchangeRate
from app.models.wealth import Holding, HoldingPrice
from app.routes.settings import SETTINGS_KEY
from app.services import price_feed, settings_store

STAMP = int(datetime(2026, 10, 7, 16, 0, tzinfo=timezone.utc).timestamp())


def _yahoo(price, code="EUR"):
    return {"chart": {"result": [{"meta": {"regularMarketPrice": price, "currency": code, "regularMarketTime": STAMP}}]}}


@pytest.fixture()
def web(monkeypatch):
    """Canned answers by URL fragment; any other URL fails like a network error."""
    answers = {}
    calls = []

    def fake(url):
        calls.append(url)
        for fragment, answer in answers.items():
            if fragment in url:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise OSError("network unreachable")

    monkeypatch.setattr(price_feed, "_get_json", fake)
    return answers, calls


def _holdings(db):
    rows = [Holding(name="ETF World", ticker="VWCE.DE", asset_class="ETF", quantity=10, avg_price=100),
            Holding(name="Apple", ticker="AAPL", asset_class="Azione", quantity=2, avg_price=150),
            Holding(name="Bitcoin", ticker="BTC", asset_class="Criptovaluta", quantity=Decimal("0.1"), avg_price=40000),
            Holding(name="Casa", ticker=None, asset_class="Immobile", quantity=1, avg_price=200000),
            Holding(name="Fondo pensione", ticker="COMETA", asset_class="Fondo Pensione", quantity=1, avg_price=9000)]
    db.session.add_all(rows)
    db.session.commit()
    return {h.name: h for h in rows}


def test_update_all_reads_converts_and_records(app, db, web):
    answers, calls = web
    answers.update({"VWCE.DE": _yahoo(131.2), "AAPL": _yahoo(200.0, "USD"),
                    "coingecko": {"bitcoin": {"eur": 58500.5, "last_updated_at": STAMP}}})
    db.session.add(ExchangeRate(currency="USD", on=date(2026, 10, 1), rate=Decimal("0.9")))
    h = _holdings(db)
    with app.test_request_context():
        results = {r.holding.name: r for r in price_feed.update_all(list(h.values()))}
        db.session.commit()
    assert set(results) == {"ETF World", "Apple", "Bitcoin"}  # property and pension fund are valued by hand
    assert results["ETF World"].price == Decimal("131.2") and results["ETF World"].on == date(2026, 10, 7)
    assert results["Apple"].price == Decimal("180.000000")  # 200 USD × 0,9
    assert h["Bitcoin"].current_price == Decimal("58500.5") and h["ETF World"].price_date == date(2026, 10, 7)
    assert HoldingPrice.query.count() == 3
    assert not any("COMETA" in url for url in calls)


def test_errors_are_reported_per_holding(app, db, web):
    answers, _ = web
    answers.update({"VWCE.DE": {"chart": {"result": None}}, "AAPL": _yahoo(200.0, "USD"),
                    "coingecko": {"bitcoin": {}}})
    h = _holdings(db)
    with app.test_request_context():
        results = {r.holding.name: r for r in price_feed.update_all(list(h.values()))}
    assert "non trovato" in results["ETF World"].error and ".MI" in results["ETF World"].error
    assert "manca il cambio" in results["Apple"].error
    assert "non trovata su CoinGecko" in results["Bitcoin"].error
    assert HoldingPrice.query.count() == 0


def test_network_down(app, db, web):
    h = _holdings(db)
    with app.test_request_context():
        results = price_feed.update_all(list(h.values()))
    assert len(results) == 3 and all(r.error for r in results)
    assert any("CoinGecko non risponde" in r.error for r in results)


def test_pence_and_missing_price(app, db, web):
    answers, _ = web
    answers.update({"VUSA.L": _yahoo(7000, "GBp"), "EMPTY": {"chart": {"result": [{"meta": {"currency": "EUR"}}]}}})
    db.session.add(ExchangeRate(currency="GBP", on=date(2026, 10, 1), rate=Decimal("1.2")))
    db.session.add_all([Holding(name="S&P 500", ticker="VUSA.L", asset_class="ETF", quantity=1, avg_price=70),
                        Holding(name="Vuoto", ticker="EMPTY", asset_class="ETF", quantity=1, avg_price=1)])
    db.session.commit()
    with app.test_request_context():
        results = {r.holding.name: r for r in price_feed.update_all(Holding.query.all())}
    assert results["S&P 500"].price == Decimal("84.000000")  # 7000 pence = 70 GBP × 1,2
    assert "nessun prezzo" in results["Vuoto"].error
    assert price_feed._coingecko_id(Holding(ticker="ethereum")) == "ethereum"


def test_route_needs_the_setting_and_reports(client, db, web):
    answers, _ = web
    answers.update({"VWCE.DE": _yahoo(131.2)})
    _holdings(db)
    page = client.get("/portfolio/prices").get_data(as_text=True)
    assert "Prezzi da internet: spenti" in page
    assert "sono spenti" in client.post("/portfolio/prices/online", follow_redirects=True).get_data(as_text=True)
    client.post("/settings/save", data={"prices_online": "on", "module_portfolio": "on"})
    assert "Aggiorna da internet" in client.get("/portfolio/prices").get_data(as_text=True)
    html = client.post("/portfolio/prices/online", follow_redirects=True).get_data(as_text=True)
    assert "Prezzi aggiornati da internet: ETF World" in html and "Bitcoin:" in html
    Holding.query.delete()
    db.session.commit()
    assert "Nessuna posizione con un ticker" in client.post("/portfolio/prices/online", follow_redirects=True).get_data(as_text=True)
    assert settings_store.get(SETTINGS_KEY)


def test_get_json_reads_the_answer(monkeypatch):
    import io

    seen = {}

    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout):
        seen["url"], seen["agent"], seen["timeout"] = request.full_url, request.get_header("User-agent"), timeout
        return Answer(b'{"ok": 1}')

    monkeypatch.setattr(price_feed.urllib.request, "urlopen", fake_urlopen)
    assert price_feed._get_json("https://example.org/x") == {"ok": 1}
    assert seen["timeout"] == price_feed.TIMEOUT and "MyFinancePlace" in seen["agent"]
