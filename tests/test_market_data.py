"""
D10, F69: the market data store — daily closes in a database of their own (shared by the archives, kept from one
app version to the next), read from Yahoo's chart answer, brought up to date from the last close minus a week.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.services import market_data


def _stamp(day: date, hour: int = 8) -> int:
    return int(datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc).timestamp())


def chart(points, currency="EUR", name="Vanguard FTSE All-World UCITS ETF") -> dict:
    """A Yahoo chart answer as the endpoint sends it (closes may be null on a half day)."""
    return {"chart": {"result": [{
        "meta": {"currency": currency, "exchangeName": "MIL", "longName": name, "gmtoffset": 3600},
        "timestamp": [_stamp(d) for d, _c in points],
        "indicators": {"quote": [{"close": [c for _d, c in points]}],
                       "adjclose": [{"adjclose": [c if c is None else c * 0.99 for _d, c in points]}]},
    }], "error": None}}


@pytest.fixture()
def store(app, tmp_path, monkeypatch):
    monkeypatch.delenv(market_data.ENV, raising=False)
    app.instance_path = str(tmp_path)
    with app.app_context():
        yield


def test_the_store_is_a_database_of_its_own_and_upgrades_itself(app, store, tmp_path):
    assert market_data.url() == f"sqlite:///{tmp_path / 'market.sqlite'}"
    assert market_data.schema_version() == market_data.SCHEMA and (tmp_path / "market.sqlite").exists()
    assert market_data.overview() == []


def test_yahoos_answer(store):
    daily = market_data.parse_chart(chart([(date(2026, 11, 2), 130.5), (date(2026, 11, 3), None),
                                           (date(2026, 11, 4), 131.25)]))
    assert daily.currency == "EUR" and daily.exchange == "MIL" and daily.name.startswith("Vanguard")
    assert [(d, c) for d, c, _a in daily.points] == [(date(2026, 11, 2), Decimal("130.5")),
                                                      (date(2026, 11, 4), Decimal("131.25"))]
    assert daily.points[0][2] == Decimal("129.195")
    with pytest.raises(ValueError, match="No data"):
        market_data.parse_chart({"chart": {"result": None, "error": {"description": "No data found"}}})
    with pytest.raises(ValueError):
        market_data.parse_chart({})


def test_sync_from_the_start_then_only_what_is_new(store):
    asked = []

    def reader(symbol, start, end):
        asked.append((symbol, start, end))
        if len(asked) == 1:
            return market_data.parse_chart(chart([(date(2026, 10, 30), 129.0), (date(2026, 11, 2), 130.0)]))
        return market_data.parse_chart(chart([(date(2026, 11, 2), 130.4), (date(2026, 11, 3), 131.0)]))

    first = market_data.sync("vwce.mi", "IE00BK5BQT80", today=date(2026, 11, 2), reader=reader)
    assert (first.symbol, first.added, first.error) == ("VWCE.MI", 2, None)
    assert asked[0] == ("VWCE.MI", market_data.FIRST_DAY, date(2026, 11, 2))
    again = market_data.sync("VWCE.MI", today=date(2026, 11, 4), reader=reader)
    assert again.added == 2 and asked[1][1] == date(2026, 10, 26)  # the last close minus a week
    assert market_data.history("VWCE.MI") == [(date(2026, 10, 30), Decimal("129")), (date(2026, 11, 2), Decimal("130.4")),
                                              (date(2026, 11, 3), Decimal("131"))]  # the correction of the 2nd kept
    assert market_data.close_on("VWCE.MI", date(2026, 11, 1)) == (date(2026, 10, 30), Decimal("129"))  # a Sunday
    assert market_data.close_on("VWCE.MI", date(2020, 1, 1)) is None
    assert market_data.history("VWCE.MI", date(2026, 11, 1), date(2026, 11, 2)) == [(date(2026, 11, 2), Decimal("130.4"))]
    [row] = market_data.overview()
    assert (row["isin"], row["currency"], row["count"], row["first_day"], row["last_day"]) == (
        "IE00BK5BQT80", "EUR", 3, date(2026, 10, 30), date(2026, 11, 3))


def test_errors_are_recorded_and_the_others_go_on(store):
    def reader(symbol, start, end):
        if symbol == "SWDA.MI":
            raise OSError("network unreachable")
        return market_data.parse_chart(chart([(date(2026, 11, 2), 10.0)]))

    found = market_data.sync_main_funds(today=date(2026, 11, 2), reader=reader)
    assert len(found) == len(market_data.MAIN_FUNDS)
    assert [f.symbol for f in found if f.error] == ["SWDA.MI"] and sum(f.added for f in found) == len(found) - 1
    rows = {r["symbol"]: r for r in market_data.overview()}
    assert rows["SWDA.MI"]["error"] == "network unreachable" and rows["SWDA.MI"]["count"] == 0
    assert rows["SWDA.MI"]["isin"] == "IE00B4L5Y983"


def test_the_command_line(app, store, monkeypatch):
    monkeypatch.setattr(market_data, "read_yahoo",
                        lambda symbol, start, end: market_data.parse_chart(chart([(date(2026, 11, 2), 5.0)])))
    runner = app.test_cli_runner()
    assert "Name the Yahoo symbols" in runner.invoke(args=["market", "sync"]).output
    result = runner.invoke(args=["market", "sync", "ENEL.MI"])
    assert "ENEL.MI" in result.output and "+1 closes" in result.output
    assert "ENEL.MI" in runner.invoke(args=["market", "status"]).output

    def down(symbol, start, end):
        raise OSError("blocked")

    monkeypatch.setattr(market_data, "read_yahoo", down)
    result = runner.invoke(args=["market", "sync", "--main"])
    assert "ERROR blocked" in result.output and result.exit_code != 0


def test_the_prices_page(client, app, db, store, monkeypatch):
    from app.models.wealth import Holding

    db.session.add(Holding(name="Enel", ticker="ENEL.MI", asset_class="Azione", quantity=10, avg_price=6))
    db.session.commit()
    page = client.get("/portfolio/prices").get_data(as_text=True)
    assert 'id="market"' in page and "Ancora vuoto" in page
    page = client.post("/portfolio/market/sync", follow_redirects=True).get_data(as_text=True)
    assert "prezzi da internet sono spenti" in page
    client.post("/settings/save", data={"prices_online": "on", "module_portfolio": "on"})
    asked = []
    monkeypatch.setattr(market_data, "read_yahoo", lambda symbol, start, end: asked.append(symbol) or
                        market_data.parse_chart(chart([(date(2026, 11, 2), 5.0)])))
    page = client.post("/portfolio/market/sync", follow_redirects=True).get_data(as_text=True)
    assert "Storico aggiornato" in page and "ENEL.MI" in asked and "VWCE.MI" in asked
    assert "ENEL.MI" in client.get("/portfolio/prices").get_data(as_text=True)
