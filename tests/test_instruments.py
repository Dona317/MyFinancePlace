"""
F19a: instruments (ISIN, quote currency, exchange, multiplier, price source), the search by ISIN or name, Stooq as a
reserve, the first year of weekly prices, and the prices read once a day by themselves. The network is canned.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.currency import ExchangeRate
from app.models.wealth import Holding, HoldingPrice
from app.services import price_feed, settings_store, studio, wealth
from tests.test_price_feed import STAMP, _yahoo, web  # noqa: F401 - web is a fixture

ISIN = "IE00BK5BQT80"


def _search(*quotes):
    return {"quotes": [dict(q) for q in quotes]}


def _with_history(price, closes, code="EUR"):
    answer = _yahoo(price, code)
    start = datetime(2025, 10, 6, tzinfo=timezone.utc)
    answer["chart"]["result"][0]["timestamp"] = [int((start + timedelta(weeks=i)).timestamp()) for i in range(len(closes))]
    answer["chart"]["result"][0]["indicators"] = {"quote": [{"close": closes}]}
    return answer


def _online(client):
    client.post("/settings/save", data={"prices_online": "on", "module_portfolio": "on"})


def test_lookup_ranks_milan_first_and_maps_the_kinds(app, web):  # noqa: F811
    answers, calls = web
    answers["search?q=IE00BK5BQT80"] = _search(
        {"symbol": "VWCE.DE", "longname": "Vanguard FTSE All-World", "quoteType": "ETF", "exchange": "GER", "exchDisp": "XETRA"},
        {"symbol": "^GSPC", "quoteType": "INDEX", "exchange": "SNP"},
        {"symbol": "VWCE.MI", "shortname": "VANGUARD ALL-WORLD", "quoteType": "ETF", "exchange": "MIL", "exchDisp": "Milan"})
    with app.test_request_context():
        found = price_feed.lookup(" ie00bk5bqt80 ")
        assert [c.symbol for c in found] == ["VWCE.MI", "VWCE.DE"]  # the index is not something one holds
        assert found[0].as_dict() == {"symbol": "VWCE.MI", "name": "VANGUARD ALL-WORLD", "asset_class": "ETF",
                                      "exchange": "Milan", "isin": ISIN, "source": "yahoo", "price_source": "auto",
                                      "currency": None}
        answers["search?q=ENI"] = _search({"symbol": "ENI.MI", "longname": "Eni", "quoteType": "EQUITY", "exchange": "MIL"},
                                          {"symbol": "CL=F", "shortname": "Crude Oil", "quoteType": "FUTURE", "exchange": "NYM"})
        assert [(c.asset_class, c.isin) for c in price_feed.lookup("ENI")] == [("Azione", None), ("Derivato", None)]
        assert price_feed.lookup("  ") == []


def test_isin_only_finds_its_ticker_and_the_first_year_of_prices(app, db, web):  # noqa: F811
    answers, _ = web
    answers["search?q=" + ISIN] = _search({"symbol": "VWCE.MI", "longname": "Vanguard", "quoteType": "ETF",
                                           "exchange": "MIL", "exchDisp": "Milan"})
    answers["chart/VWCE.MI?range=1y"] = _with_history(131.2, [110.0, None, 120.5, 125.0])
    etf = Holding(name="All-World", isin=ISIN, asset_class="ETF", quantity=10, avg_price=100)
    db.session.add(etf)
    db.session.commit()
    with app.test_request_context():
        (result,) = price_feed.update_all([etf])
        db.session.commit()
    assert result.error is None and result.source == "yahoo"
    assert (etf.ticker, etf.exchange, etf.currency) == ("VWCE.MI", "Milan", "EUR")
    assert [float(p.price) for p in wealth.price_history(etf)] == [110.0, 120.5, 125.0, 131.2]  # weekly + today
    # with a history already there, only today's price is read
    answers["chart/VWCE.MI?range=5d"] = _yahoo(132.0)
    for day in range(3):
        db.session.add(HoldingPrice(holding_id=etf.id, on=date(2025, 1, 1 + day), price=100))
    db.session.commit()
    with app.test_request_context():
        price_feed.update_all([etf])
    assert etf.current_price == Decimal("132.0")


def test_isin_not_found(app, db, web):  # noqa: F811
    answers, _ = web
    answers["search?q="] = _search()
    fund = Holding(name="Fondo", isin="LU0000000000", asset_class="Fondo", quantity=1, avg_price=10)
    db.session.add(fund)
    db.session.commit()
    with app.test_request_context():
        (result,) = price_feed.update_all([fund])
    assert "non trovato" in result.error and fund.ticker is None


def test_stooq_when_yahoo_does_not_answer(app, db, web):  # noqa: F811
    answers, _ = web
    answers["stooq.com/q/l/?s=aapl.us"] = "Symbol,Date,Time,Open,High,Low,Close,Volume\nAAPL.US,2026-10-09,22:00:00,1,1,1,200.5,1\n"
    answers["stooq.com/q/l/?s=vusa.uk"] = "Symbol,Date,Time,Open,High,Low,Close,Volume\nVUSA.UK,2026-10-09,17:00:00,1,1,1,7000,1\n"
    answers["stooq.com/q/l/?s=sap.de"] = "Symbol,Date,Time,Open,High,Low,Close,Volume\nSAP.DE,N/D,N/D,N/D,N/D,N/D,N/D,N/D\n"
    db.session.add_all([ExchangeRate(currency="USD", on=date(2026, 10, 1), rate=Decimal("0.9")),
                        ExchangeRate(currency="GBP", on=date(2026, 10, 1), rate=Decimal("1.2"))])
    rows = [Holding(name="Apple", ticker="AAPL", asset_class="Azione", quantity=1, avg_price=150),
            Holding(name="S&P", ticker="VUSA.L", asset_class="ETF", quantity=1, avg_price=70),
            Holding(name="SAP", ticker="SAP.DE", asset_class="Azione", quantity=1, avg_price=100),
            Holding(name="Enel", ticker="ENEL.MI", asset_class="Azione", quantity=1, avg_price=6),
            Holding(name="Solo Stooq", ticker="MSFT", asset_class="Azione", quantity=1, avg_price=300, price_source="stooq"),
            Holding(name="A mano", ticker="XYZ", asset_class="Azione", quantity=1, avg_price=1, price_source="manual")]
    db.session.add_all(rows)
    db.session.commit()
    with app.test_request_context():
        results = {r.holding.name: r for r in price_feed.update_all(rows)}
    assert "A mano" not in results  # valued by hand: nothing is asked
    assert (results["Apple"].price, results["Apple"].source, results["Apple"].on) == (
        Decimal("180.450000"), "stooq", date(2026, 10, 9))  # 200,5 USD × 0,9
    assert results["S&P"].price == Decimal("84.000000") and rows[1].currency == "GBP"  # 7000 pence
    assert "non trovato su Stooq" in results["SAP"].error and "network unreachable" in results["SAP"].error
    assert "non quotato su Stooq" in results["Enel"].error  # no Italian listings there
    assert "network" in results["Solo Stooq"].error and "Stooq:" not in results["Solo Stooq"].error


def test_a_missing_exchange_rate_does_not_try_stooq(app, db, web):  # noqa: F811
    answers, calls = web
    answers["chart/AAPL"] = _yahoo(200.0, "USD")
    apple = Holding(name="Apple", ticker="AAPL", asset_class="Azione", quantity=1, avg_price=150)
    db.session.add(apple)
    db.session.commit()
    with app.test_request_context():
        (result,) = price_feed.update_all([apple])
    assert "manca il cambio" in result.error and not any("stooq" in url for url in calls)


def test_history_in_pence_is_converted_week_by_week(app, db, web):  # noqa: F811
    answers, _ = web
    answers["chart/VUSA.L"] = _with_history(7000, [6000, 6500], code="GBp")
    db.session.add(ExchangeRate(currency="GBP", on=date(2025, 1, 1), rate=Decimal("1.2")))
    sp = Holding(name="S&P", ticker="VUSA.L", asset_class="ETF", quantity=1, avg_price=70)
    db.session.add(sp)
    db.session.commit()
    with app.test_request_context():
        (result,) = price_feed.update_all([sp])
        db.session.commit()
    assert result.error is None and [float(p.price) for p in wealth.price_history(sp)] == [72.0, 78.0, 84.0]


def test_a_derivative_is_worth_quantity_times_multiplier_times_price(db):
    option = Holding(name="Call ENI", ticker="ENI.MI", asset_class="Derivato", quantity=2, avg_price=Decimal("0.5"),
                     current_price=Decimal("0.8"), multiplier=100)
    assert (option.units, option.cost, option.value, round(option.gain, 2)) == (200.0, 100.0, 160.0, 60.0)
    db.session.add(option)
    db.session.commit()
    db.session.add(HoldingPrice(holding_id=option.id, on=date(2026, 1, 5), price=Decimal("0.6")))
    db.session.commit()
    assert wealth.value_on(option, date(2026, 1, 10)) == 120.0
    assert wealth.portfolio_summary([option])["investments_value"] == 160.0


def test_once_a_day_only_when_turned_on(client, app, db, web, monkeypatch):  # noqa: F811
    answers, calls = web
    answers["chart/VWCE.DE"] = _yahoo(131.2)
    db.session.add(Holding(name="ETF", ticker="VWCE.DE", asset_class="ETF", quantity=1, avg_price=100))
    db.session.commit()
    client.get("/portfolio/")
    assert not calls  # off by default: nothing goes to the internet
    _online(client)
    client.get("/dashboard")
    assert len(calls) == 1 and settings_store.get(price_feed.LAST_RUN) == date.today().isoformat()
    client.get("/portfolio/")
    assert len(calls) == 1  # already read today
    with app.test_request_context():
        assert price_feed.refresh_daily() is None
        assert len(price_feed.refresh_daily(date.today() + timedelta(days=1))) == 1


def test_the_daily_reading_runs_in_a_thread(client, app, db, web, monkeypatch):  # noqa: F811
    answers, calls = web
    answers["chart/VWCE.DE"] = _yahoo(131.2)
    db.session.add(Holding(name="ETF", ticker="VWCE.DE", asset_class="ETF", quantity=1, avg_price=100))
    db.session.commit()
    _online(client)
    started = []
    monkeypatch.setattr(price_feed.threading, "Thread",
                        lambda target, args, **kw: started.append((target, args)) or type("T", (), {"start": lambda s: None})())
    app.config["PRICES_SYNC"] = False
    try:
        client.get("/portfolio/")
        client.get("/portfolio/")  # a second visit while the first one is still reading: no second thread
    finally:
        app.config["PRICES_SYNC"] = True
    assert len(started) == 1 and not calls  # the page did not wait
    target, args = started[0]
    target(*args)  # what the thread does: the prices of the archive that was open
    assert len(calls) == 1 and not price_feed._running

    def broken():
        raise RuntimeError("database down")

    monkeypatch.setattr(price_feed, "refresh_daily", broken)
    target(*args)  # logged, never raised
    assert not price_feed._running


def test_every_archive_once_a_day(app, db, web, monkeypatch):  # noqa: F811
    answers, _ = web
    answers["chart/VWCE.DE"] = _yahoo(131.2)
    db.session.add(Holding(name="ETF", ticker="VWCE.DE", asset_class="ETF", quantity=1, avg_price=100))
    db.session.commit()
    with app.test_request_context():
        assert price_feed.refresh_all_archives() == 0  # turned off
        settings = dict(settings_store.get_json("ui.settings", {}, expect=dict))
        settings["prices_online"] = True
        settings_store.set_json("ui.settings", settings)
        assert price_feed.refresh_all_archives() == 1
        assert price_feed.refresh_all_archives() == 0  # once a day
        assert len(studio.clients()) == 1


def test_form_fields_and_search(client, db, web):  # noqa: F811
    answers, _ = web
    base = {"name": "Call ENI", "ticker": "ENI.MI", "asset_class": "Derivato", "quantity": "2", "avg_price": "0,5"}
    page = client.post("/portfolio/new", data=base | {"isin": "it 0003132476", "currency": "eur", "exchange": "Milano",
                                                      "multiplier": "100", "price_source": "manual"})
    assert page.status_code == 302
    option = Holding.query.one()
    assert (option.isin, option.currency, option.exchange, option.multiplier, option.price_source) == (
        "IT0003132476", "EUR", "Milano", Decimal("100"), "manual")
    for field, wrong, message in (("isin", "IT123", "ISIN: 12"), ("currency", "EURO", "Valuta: il codice"),
                                  ("multiplier", "0", "Moltiplicatore"), ("price_source", "bloomberg", "Fonte")):
        html = client.post("/portfolio/new", data=base | {field: wrong}).get_data(as_text=True)
        assert message in html, field
    assert 'id="lookup-q"' not in client.get("/portfolio/new").get_data(as_text=True)  # internet off: no search
    assert client.get("/portfolio/lookup?q=ENI").status_code == 403

    _online(client)
    assert 'id="lookup-q"' in client.get("/portfolio/new").get_data(as_text=True)
    answers["search?q=ENI"] = _search({"symbol": "ENI.MI", "longname": "Eni S.p.A.", "quoteType": "EQUITY",
                                       "exchange": "MIL", "exchDisp": "Milan"})
    assert client.get("/portfolio/lookup?q=ENI").get_json()["results"][0]["symbol"] == "ENI.MI"
    failed = client.get("/portfolio/lookup?q=nothing")
    assert failed.status_code == 502 and "non riuscita" in failed.get_json()["error"]


def test_source_of():
    assert price_feed.source_of(Holding(asset_class="Immobile")) is None
    assert price_feed.source_of(Holding(asset_class="Criptovaluta")) == "coingecko"
    assert price_feed.source_of(Holding(asset_class="Derivato", price_source="auto")) == "yahoo"
    assert price_feed.source_of(Holding(asset_class="Fondo Pensione", price_source="yahoo")) == "yahoo"
    assert not price_feed.supported(Holding(asset_class="ETF"))  # neither ticker nor ISIN


@pytest.mark.parametrize("ticker, symbol", [("AAPL", "aapl.us"), ("sap.de", "sap.de"), ("VUSA.L", "vusa.uk")])
def test_stooq_symbols(ticker, symbol):
    assert price_feed._stooq_symbol(ticker)[0] == symbol


def test_get_text(monkeypatch):
    import io

    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(price_feed.urllib.request, "urlopen", lambda request, timeout: Answer(b"a,b\n1,2\n"))
    assert price_feed._get_text("https://example.org/x.csv") == "a,b\n1,2\n"
