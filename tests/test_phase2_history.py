"""
Fase 2: the price history used by the archive — closes loaded from a CSV file, holdings linked to the history by
ticker or ISIN, past prices taken from the stored closes when newer, and the value day by day.
"""
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.wealth import Holding, HoldingPrice
from app.services import market_data, performance, wealth

YAHOO_CSV = b"Date,Open,High,Low,Close,Adj Close,Volume\n2026-10-01,1,1,1,100.5,99.5,10\n2026-10-02,1,1,1,null,null,0\n" \
            b"2026-10-05,1,1,1,102,101,10\n"
ITALIAN_CSV = "﻿Data;Chiusura\n02/10/2026;1.234,50\n01.10.2026;1.230,00\nbad;row\n".encode()


@pytest.fixture()
def store(app, tmp_path, monkeypatch):
    monkeypatch.delenv(market_data.ENV, raising=False)
    app.instance_path = str(tmp_path)
    with app.app_context():
        yield


def _closes(symbol: str, points, isin=None, currency="EUR"):
    daily = market_data.Daily(currency, "MIL", None, [(d, Decimal(str(c)), None) for d, c in points])
    market_data.store(symbol, daily, isin, source="file")


def test_closes_from_a_file(store):
    daily = market_data.read_csv(YAHOO_CSV, "EUR")
    assert [(d, c, a) for d, c, a in daily.points] == [(date(2026, 10, 1), Decimal("100.5"), Decimal("99.5")),
                                                       (date(2026, 10, 5), Decimal("102"), Decimal("101"))]
    daily = market_data.read_csv(ITALIAN_CSV)
    assert [(d, c) for d, c, _a in daily.points] == [(date(2026, 10, 1), Decimal("1230.00")),
                                                     (date(2026, 10, 2), Decimal("1234.50"))]
    with pytest.raises(ValueError, match="date column"):
        market_data.read_csv(b"Foo,Bar\n1,2\n")
    with pytest.raises(ValueError, match="no row"):
        market_data.read_csv(b"Date,Close\nx,y\n")
    with pytest.raises(ValueError, match="empty"):
        market_data.read_csv(b"")


def test_holdings_linked_by_ticker_or_isin(store, db):
    assert not market_data.available()
    etf = Holding(name="VWCE", ticker="vwce.mi", asset_class="ETF", quantity=1, avg_price=100)
    assert market_data.link(etf) == (None, "missing")
    _closes("VWCE.MI", [(date(2026, 10, 1), 100)], isin="IE00BK5BQT80")
    _closes("AAPL", [(date(2026, 10, 1), 200)], currency="USD")
    assert market_data.available()
    by_isin = Holding(name="All-World", isin="ie00bk5bqt80", asset_class="ETF", quantity=1, avg_price=100)
    bond = Holding(name="BTP", ticker="VWCE.MI", asset_class="Obbligazione", quantity=1, avg_price=100)
    apple = Holding(name="Apple", ticker="AAPL", asset_class="Azione", currency="USD", quantity=1, avg_price=150)
    assert market_data.link(etf) == ("VWCE.MI", "ticker")
    assert market_data.link(by_isin) == ("VWCE.MI", "isin")
    assert market_data.link(bond) == (None, "class")
    assert market_data.link(apple) == (None, "currency")


def test_past_prices_take_the_newer_close(store, db):
    etf = Holding(name="VWCE", ticker="VWCE.MI", asset_class="ETF", quantity=10, avg_price=90, current_price=120)
    manual = Holding(name="Fondo", asset_class="Fondo comune", quantity=1, avg_price=50)
    db.session.add_all([etf, manual])
    db.session.flush()
    db.session.add_all([HoldingPrice(holding_id=etf.id, on=date(2026, 10, 1), price=100),
                        HoldingPrice(holding_id=manual.id, on=date(2026, 10, 1), price=55)])
    db.session.commit()
    _closes("VWCE.MI", [(date(2026, 9, 30), 95), (date(2026, 10, 15), 110)])
    assert wealth.prices_on(date(2026, 10, 5)) == {etf.id: 100.0, manual.id: 55.0}   # the recorded one is newer
    assert wealth.prices_on(date(2026, 10, 20)) == {etf.id: 110.0, manual.id: 55.0}  # the close is newer


def test_the_value_day_by_day(store, db):
    today = date(2026, 11, 13)   # a Friday
    etf = Holding(name="VWCE", ticker="VWCE.MI", asset_class="ETF", quantity=10, avg_price=100, current_price=130,
                  purchase_date=date(2026, 11, 2))
    db.session.add(etf)
    db.session.commit()
    before = performance.daily_values([etf], 30, today)   # no closes: the current price (no price recorded)
    assert set(before["value"]) == {1300.0} and before["linked"] == 0
    _closes("VWCE.MI", [(date(2026, 11, 2) + timedelta(days=i), 100 + i) for i in range(10)])
    series = performance.daily_values([etf], 30, today)
    assert series["linked"] == 1 and series["labels"][0] == "02/11/26" and len(series["labels"]) == 10  # weekdays
    assert series["value"][:2] == [1000.0, 1010.0] and series["value"][-1] == 1300.0  # today: the current price
    assert set(series["invested"]) == {1000.0}
    assert performance.daily_values([], 30, today)["labels"] == []


def test_the_pages(client, app, db, store):
    db.session.add_all([Holding(name="Enel", ticker="ENEL.MI", asset_class="Azione", quantity=10, avg_price=6,
                                purchase_date=date.today() - timedelta(days=60)),
                        Holding(name="BTP", asset_class="Obbligazione", quantity=1000, avg_price=100)])
    db.session.commit()
    page = client.get("/portfolio/prices").get_data(as_text=True)
    assert 'id="links"' in page and "non collegato" in page and "del nominale" in page
    assert "Scrivi il simbolo" in client.post("/portfolio/market/import", data={"symbol": ""},
                                              follow_redirects=True).get_data(as_text=True)
    sent = {"symbol": "enel.mi", "isin": "IT0003128367", "file": (io.BytesIO(b"Date,Close\nfoo,bar\n"), "enel.csv")}
    assert "File non letto" in client.post("/portfolio/market/import", data=sent, content_type="multipart/form-data",
                                           follow_redirects=True).get_data(as_text=True)
    rows = "".join(f"{(date.today() - timedelta(days=i)).isoformat()},{6 + i / 100}\n" for i in range(70))
    sent["file"] = (io.BytesIO(("Date,Close\n" + rows).encode()), "enel.csv")
    page = client.post("/portfolio/market/import", data=sent, content_type="multipart/form-data",
                       follow_redirects=True).get_data(as_text=True)
    assert "Storico di ENEL.MI: 70 chiusure" in page and "dal ticker" in page
    page = client.get("/portfolio/performance?days=90").get_data(as_text=True)
    assert "Valore giorno per giorno" in page and "1 titoli con lo storico giornaliero" in page


def test_the_command_line_import(app, store, tmp_path):
    path = tmp_path / "closes.csv"
    path.write_bytes(YAHOO_CSV)
    runner = app.test_cli_runner()
    result = runner.invoke(args=["market", "import", str(path), "vwce.mi", "--isin", "IE00BK5BQT80"])
    assert "VWCE.MI" in result.output and "+2 closes" in result.output
    path.write_bytes(b"x\n")
    assert runner.invoke(args=["market", "import", str(path), "X"]).exit_code != 0
