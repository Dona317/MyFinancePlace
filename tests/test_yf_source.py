"""F119: yfinance as the second source of the daily closes (after the app's own reading of Yahoo, before Stooq and
justETF) — read through a fake library here: no network in the tests."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.models.wealth import Holding
from app.services import history_filler, market_data, yf_source
from tests.conftest import make_tx

TODAY = date(2026, 11, 20)


class Frame:
    """What yfinance's history() gives, as far as the reader uses it (a pandas DataFrame)."""

    def __init__(self, rows, adjusted=True):
        self.index = [datetime(d.year, d.month, d.day, tzinfo=timezone.utc) for d, _c, _a in rows]
        self.data = {"Close": [c for _d, c, _a in rows]}
        if adjusted:
            self.data["Adj Close"] = [a for _d, _c, a in rows]
        self.columns = list(self.data)
        self.empty = not rows

    def __getitem__(self, column):
        return self.data[column]


class Library:
    def __init__(self, frames):
        self.frames, self.asked = frames, []
        library = self

        class Ticker:
            def __init__(self, symbol):
                self.symbol = symbol
                self.history_metadata = {"currency": "EUR", "exchangeName": "MIL", "longName": f"Name of {symbol}"}

            def history(self, **kwargs):
                library.asked.append((self.symbol, kwargs))
                return library.frames.get(self.symbol)

        self.Ticker = Ticker


@pytest.fixture()
def store(app, tmp_path, monkeypatch):
    monkeypatch.delenv(market_data.ENV, raising=False)
    app.instance_path = str(tmp_path)
    yield


def test_the_reader(app):
    rows = [(date(2026, 11, 2), 130.5, 130.5), (date(2026, 11, 3), float("nan"), None), (date(2026, 11, 4), 131.0, 129.9)]
    library = Library({"VWCE.MI": Frame(rows), "NOADJ.MI": Frame(rows[:1], adjusted=False), "EMPTY.MI": Frame([]),
                       "NAN.MI": Frame([(date(2026, 11, 2), float("nan"), None)])})
    daily = yf_source.read("VWCE.MI", date(2026, 11, 1), date(2026, 11, 4), library)
    assert (daily.currency, daily.exchange, daily.name) == ("EUR", "MIL", "Name of VWCE.MI")
    assert daily.points == [(date(2026, 11, 2), Decimal("130.5"), Decimal("130.5")),
                            (date(2026, 11, 4), Decimal("131.0"), Decimal("129.9"))]  # the day without a close left out
    symbol, asked = library.asked[0]
    assert asked["start"] == "2026-11-01" and asked["end"] == "2026-11-05" and asked["auto_adjust"] is False
    assert yf_source.read("NOADJ.MI", date(2026, 11, 1), date(2026, 11, 4), library).points[0][2] is None
    for nothing in ("EMPTY.MI", "NAN.MI", "UNKNOWN.MI"):
        with pytest.raises(ValueError):
            yf_source.read(nothing, date(2026, 11, 1), date(2026, 11, 4), library)


def test_off_in_the_tests_missing_or_on(app, monkeypatch):
    with app.app_context():
        with pytest.raises(ValueError, match="spento"):
            yf_source.read_if_on("VWCE.MI", TODAY, TODAY)  # tests: off
        app.config["YFINANCE"] = True
        try:
            monkeypatch.setattr(yf_source, "available", lambda: False)
            with pytest.raises(ValueError, match="non installato"):
                yf_source.read_if_on("VWCE.MI", TODAY, TODAY)
            monkeypatch.setattr(yf_source, "available", lambda: True)
            monkeypatch.setattr(yf_source, "_library", lambda: Library({"VWCE.MI": Frame([(TODAY, 140.0, None)])}))
            assert yf_source.read_if_on("VWCE.MI", TODAY, TODAY).points[0][1] == Decimal("140.0")
        finally:
            app.config["YFINANCE"] = False


def test_the_library_is_the_real_one_when_installed(app):
    if not yf_source.available():
        pytest.skip("yfinance not installed")
    library = yf_source._library()
    assert hasattr(library, "Ticker")


def test_the_second_source_of_the_filler(app, db, store, monkeypatch):
    holding = Holding(name="Vanguard FTSE All-World", ticker="VWCE.MI", isin="IE00BK5BQT80", asset_class="ETF",
                      quantity=10, avg_price=100, opening_quantity=0, opening_price=0)
    db.session.add(holding)
    db.session.flush()
    db.session.add(make_tx(date=date(2026, 11, 2), type="transfer", amount=1000, holding_id=holding.id, units=10,
                           unit_price=100))
    db.session.commit()
    assert [name for name, _reader in history_filler.SOURCES] == ["yahoo", "yfinance", "stooq"]
    days = history_filler.trading_days(date(2026, 10, 1), TODAY)
    library = Library({"VWCE.MI": Frame([(d, 150.0, 150.0) for d in days])})

    def yahoo_down(symbol, start, end):
        raise OSError("Yahoo: 429 Too Many Requests")
    monkeypatch.setattr(history_filler, "SOURCES", (("yahoo", yahoo_down), *history_filler.SOURCES[1:]))
    monkeypatch.setattr(yf_source, "_library", lambda: library)
    app.config["YFINANCE"] = True
    try:
        result = history_filler.fill(history_filler.targets(TODAY)[0], TODAY)
    finally:
        app.config["YFINANCE"] = False
    assert result.sources == ["yfinance"] and result.holes == 0 and market_data.sources_of("VWCE.MI") == ["yfinance"]
