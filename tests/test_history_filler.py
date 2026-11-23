"""F110: the past closes of the instruments held, read by themselves from their first operation, holes filled from
Yahoo or Stooq, and the ECB rates of the currencies in use (closes in another currency counted in euro)."""
import io
import zipfile
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.currency import ExchangeRate
from app.models.wealth import Holding
from app.services import history_filler, market_data, settings_store
from tests.conftest import make_tx

TODAY = date(2026, 11, 20)  # a Friday


@pytest.fixture()
def store(app, tmp_path, monkeypatch):
    monkeypatch.delenv(market_data.ENV, raising=False)
    app.instance_path = str(tmp_path)
    yield


def daily(days, code="EUR", value=100.0):
    return market_data.Daily(code, "X", None, [(d, Decimal(str(value + i)), None) for i, d in enumerate(days)])


def _etf(db, ticker="VWCE.MI", isin="IE00BK5BQT80", first=date(2026, 10, 1), **extra):
    holding = Holding(name="Vanguard FTSE All-World", ticker=ticker, isin=isin, asset_class="ETF", quantity=10,
                      avg_price=100, opening_quantity=0, opening_price=0, **extra)
    db.session.add(holding)
    db.session.flush()
    db.session.add(make_tx(date=first, type="transfer", amount=1000, holding_id=holding.id, units=10, unit_price=100))
    db.session.commit()
    return holding


def test_holes_are_runs_of_three_trading_days_or_the_ends(app):
    days = history_filler.trading_days(date(2026, 11, 2), date(2026, 11, 20))
    assert len(days) == 15 and all(d.weekday() < 5 for d in days)
    have = set(days) - {date(2026, 11, 4)} - {date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12)}
    assert history_filler.missing(have, date(2026, 11, 2), date(2026, 11, 20)) == [(date(2026, 11, 10), date(2026, 11, 12))]
    assert history_filler.holes(have, date(2026, 11, 2), date(2026, 11, 20)) == 1
    # before the first close and after the last: wanted whatever their length
    middle = {d for d in days if date(2026, 11, 5) <= d <= date(2026, 11, 18)}
    assert history_filler.missing(middle, date(2026, 11, 2), date(2026, 11, 20)) == [
        (date(2026, 11, 2), date(2026, 11, 4)), (date(2026, 11, 19), date(2026, 11, 20))]
    assert history_filler.missing(set(), date(2026, 11, 2), date(2026, 11, 20)) == [(date(2026, 11, 2), date(2026, 11, 20))]
    assert history_filler.holes(set(), date(2026, 11, 2), date(2026, 11, 20)) == 0


def test_only_the_instruments_held_from_their_first_operation(app, db, store):
    _etf(db)
    db.session.add(Holding(name="Casa", asset_class="Immobile", quantity=1, avg_price=1))  # not on an exchange
    db.session.add(Holding(name="Fondo", ticker="vwce.mi", asset_class="ETF", quantity=1, avg_price=1,
                           purchase_date=date(2026, 9, 1)))  # the same instrument twice: read once, from the earliest
    db.session.commit()
    found = history_filler.targets(TODAY)
    assert [(t.symbol, t.start) for t in found] == [("VWCE.MI", date(2026, 9, 1) - timedelta(days=31))]
    assert len(found[0].holding_ids) == 2


def test_fill_reads_everything_then_only_the_holes_and_falls_back_to_stooq(app, db, store):
    _etf(db, first=date(2026, 11, 3))
    asked = []

    def yahoo(symbol, start, end):
        asked.append(("yahoo", start, end))
        if len(asked) == 1:  # the first time: everything but a hole of a week
            days = [d for d in history_filler.trading_days(start, end) if not date(2026, 10, 12) <= d <= date(2026, 10, 16)]
            return daily(days)
        raise OSError("Yahoo down")

    def stooq(symbol, start, end):
        asked.append(("stooq", start, end))
        return daily(history_filler.trading_days(start, end))

    target = history_filler.targets(TODAY)[0]
    first = history_filler.fill(target, TODAY, sources=(("yahoo", yahoo), ("stooq", stooq)))
    assert first.added > 0 and first.holes == 1 and first.sources == ["yahoo"]
    second = history_filler.fill(target, TODAY, sources=(("yahoo", yahoo), ("stooq", stooq)))
    assert ("stooq", date(2026, 10, 12), date(2026, 10, 16)) in asked  # the hole, from the second source
    assert second.holes == 0 and second.sources == ["stooq"]
    assert set(market_data.sources_of("VWCE.MI")) == {"yahoo", "stooq"}
    rows = history_filler.coverage(TODAY)
    assert rows[0]["symbol"] == "VWCE.MI" and rows[0]["holes"] == 0 and rows[0]["share"] == 100


def test_nothing_read_is_remembered_as_an_error(app, db, store):
    _etf(db, ticker="NOPE.MI")

    def broken(symbol, start, end):
        raise ValueError("symbol not found")
    result = history_filler.fill(history_filler.targets(TODAY)[0], TODAY, sources=(("yahoo", broken),))
    assert result.error and "symbol not found" in result.error
    assert history_filler.coverage(TODAY)[0]["error"]


def test_stooq_symbols_and_answer(app):
    assert history_filler.stooq_symbol("VWCE.MI") == ("vwce.de", "EUR")  # Milan: its Xetra twin
    assert history_filler.stooq_symbol("VWCE.DE") == ("vwce.de", "EUR")
    parsed = history_filler.parse_stooq("Date,Open,High,Low,Close,Volume\n2026-11-02,1,1,1,130.5,10\n2026-11-03,1,1,1,x,1\n",
                                        "EUR")
    assert parsed.points == [(date(2026, 11, 2), Decimal("130.5"), None)]
    with pytest.raises(ValueError):
        history_filler.parse_stooq("No data", "EUR")


def _ecb_zip(rows):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("eurofxref-hist.csv", "Date,USD,JPY,GBP,\n" + "\n".join(rows) + "\n")
    return out.getvalue()


def test_ecb_history_only_for_the_currencies_in_use_and_closes_in_dollars_count_in_euro(app, db, store, client):
    us = _etf(db, ticker="CSPX.L", isin="IE00B5BMR087", first=date(2026, 11, 2))
    db.session.add(make_tx(date=date(2026, 11, 2), amount=10, currency="USD"))
    db.session.commit()
    market_data.store("CSPX.L", daily([date(2026, 11, 2), date(2026, 11, 3)], code="USD", value=500.0))
    assert history_filler.currencies_in_use() == {"USD"}
    raw = _ecb_zip(["2026-11-03,1.25,160.1,0.85,", "2026-11-02,1.20,160.0,N/A,", "2020-01-02,1.10,120,0.8,"])
    assert history_filler.parse_ecb_history(raw, {"USD"}, date(2026, 1, 1)) == [
        (date(2026, 11, 3), "USD", Decimal("0.80000000")), (date(2026, 11, 2), "USD", Decimal("0.83333333"))]
    done = history_filler.fill_rates(TODAY, fetch=lambda address: raw)
    assert done == {"currencies": ["USD"], "added": 2}
    assert ExchangeRate.query.filter_by(currency="JPY").count() == 0  # not in use: not stored
    # the closes in dollars now price the holding, in euro
    symbol, how = market_data.link(us)
    assert (symbol, how) == ("CSPX.L", "ticker")
    days, values = market_data._series("CSPX.L")
    assert days == [date(2026, 11, 2), date(2026, 11, 3)] and values == pytest.approx([500 / 1.2, 501 / 1.25])


def test_run_and_the_daily_turn(app, db, store, monkeypatch):
    _etf(db)
    monkeypatch.setattr(history_filler, "SOURCES", (("yahoo", lambda s, a, b: daily(history_filler.trading_days(a, b))),))
    done = history_filler.run(TODAY, sources=history_filler.SOURCES, fetch=lambda address: b"not a zip")
    assert done.filled[0].added > 0 and done.rates == {"currencies": [], "added": 0} and done.rates_error is None
    assert not history_filler.due()  # «prezzi da internet» off
    settings_store.set_json("ui.settings", {"prices_online": True})
    assert history_filler.due()
    app.config["PRICES_SYNC"] = True
    try:
        history_filler.run_in_background()
    finally:
        app.config["PRICES_SYNC"] = False
    assert not history_filler.due() and settings_store.get(history_filler.LAST_RUN)


def test_the_button_and_the_prices_page(client, db, store, monkeypatch):
    _etf(db)
    page = client.get("/portfolio/prices").get_data(as_text=True)
    assert "Storico dei tuoi titoli" in page and "VWCE.MI" in page and "ancora niente" in page
    off = client.post("/portfolio/market/fill", follow_redirects=True).get_data(as_text=True)
    assert "prezzi da internet sono spenti" in off
    settings_store.set_json("ui.settings", {"prices_online": True})
    monkeypatch.setattr(history_filler, "SOURCES", (("yahoo", lambda s, a, b: daily(history_filler.trading_days(a, b))),))
    monkeypatch.setattr(history_filler, "_bytes", lambda address: b"x")
    app = client.application
    app.config["PRICES_SYNC"] = True
    try:
        done = client.post("/portfolio/market/fill", follow_redirects=True).get_data(as_text=True)
    finally:
        app.config["PRICES_SYNC"] = False
    assert "Aggiornamento dei dati avviato" in done and "Riempi i buchi ora" in done
    assert history_filler.status()["summary"]["instruments"] == 1


def test_the_network_readers(app, monkeypatch):
    real_text, seen = history_filler._text, []
    monkeypatch.setattr(history_filler, "_text", lambda address: seen.append(address) or
                        "Date,Open,High,Low,Close,Volume\n2026-11-02,1,1,1,130.5,10\n")
    got = history_filler.read_stooq("VWCE.MI", date(2026, 11, 1), date(2026, 11, 20))
    assert got.points[0][1] == Decimal("130.5") and "s=vwce.de" in seen[0] and "d1=20261101" in seen[0]

    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False
    monkeypatch.setattr(history_filler.urllib.request, "urlopen", lambda request, timeout: Answer(b"\xef\xbb\xbfok"))
    assert real_text("https://example.org") == "ok" and history_filler._bytes("https://example.org") == b"\xef\xbb\xbfok"


def test_pence_and_currencies_without_rates(app, db, store):
    london = _etf(db, ticker="VUSA.L", isin="IE00B3XXRP09")
    market_data.store("VUSA.L", daily([date(2026, 11, 2)], code="GBp", value=8000.0))
    assert market_data.plain_currency("GBp") == "GBP" and market_data.plain_currency(None) is None
    assert market_data.link(london) == (None, "currency")  # no pound rates yet
    db.session.add(ExchangeRate(currency="GBP", on=date(2026, 11, 1), rate=Decimal("1.15"), source="ecb"))
    db.session.commit()
    from app.services import request_cache
    request_cache.clear()
    assert market_data.link(london) == ("VUSA.L", "ticker")
    assert market_data._series("VUSA.L")[1] == pytest.approx([80 * 1.15])  # pence → pounds → euro


def test_the_background_thread(app, db, store, monkeypatch):
    calls = []
    monkeypatch.setattr(history_filler, "run", lambda progress=None: calls.append("run") or history_filler.Run([]))
    history_filler._running.add("k")
    history_filler._thread(app, None, "k")
    assert calls == ["run"] and "k" not in history_filler._running

    def boom(progress=None):
        raise RuntimeError("x")
    monkeypatch.setattr(history_filler, "run", boom)
    history_filler._thread(app, None, "k")  # logged, never raised
    assert history_filler._status["k"]["summary"]["errors"] == ["errore imprevisto"]


def test_an_isin_gets_its_ticker_and_a_second_run_reads_only_the_last_rates(app, db, store, monkeypatch):
    from app.services import currency, price_feed
    holding = _etf(db, ticker=None)
    unknown = _etf(db, ticker=None, isin="XX0000000000")

    def resolve(h):
        if h.isin == "XX0000000000":
            raise ValueError("ISIN non trovato")
        h.ticker = "VWCE.MI"
    monkeypatch.setattr(price_feed, "_resolve_ticker", resolve)
    errors = []
    found = history_filler.targets(TODAY, errors)
    assert [t.symbol for t in found] == ["VWCE.MI"] and db.session.get(Holding, holding.id).ticker == "VWCE.MI"
    assert errors[0].symbol == "XX0000000000" and "non trovato" in errors[0].error and unknown.ticker is None
    # rates already there from the first day needed: only the ECB's last 90 days
    db.session.add(make_tx(date=date(2026, 10, 1), amount=5, currency="USD"))
    db.session.add(ExchangeRate(currency="USD", on=date(2026, 9, 1), rate=Decimal("0.9"), source="ecb"))
    db.session.commit()
    monkeypatch.setattr(currency, "download_ecb", lambda history=True: 61)
    assert history_filler.fill_rates(TODAY, fetch=lambda address: pytest.fail("no history needed")) == {
        "currencies": ["USD"], "added": 61}


def test_the_ecb_history_goes_into_the_shared_price_database(app, store):
    raw = _ecb_zip(["2026-11-03,1.25,160.1,0.85,", "2026-11-02,1.20,160.0,N/A,", "bad,1,1,1,"])
    assert history_filler.store_ecb_history(raw, codes=("USD", "GBP")) == 3
    assert market_data.history("ECB.USD") == [(date(2026, 11, 2), Decimal("1.2")), (date(2026, 11, 3), Decimal("1.25"))]
    assert market_data.history("ECB.GBP") == [(date(2026, 11, 3), Decimal("0.85"))]
    assert market_data.days("ECB.JPY") == []  # not asked
