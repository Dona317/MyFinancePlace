"""F113: the price database shared by every archive — the links pasted and the listings found (ISIN → ticker) kept
there, not in an archive — and the whole of it exported and imported (a zip of two CSV files) without losing
anything already there."""
import io
import zipfile
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from app.models.wealth import Holding
from app.services import history_links, market_data, price_feed, settings_store

VWCE = "IE00BK5BQT80"


@pytest.fixture()
def store(app, tmp_path, monkeypatch):
    monkeypatch.delenv(market_data.ENV, raising=False)
    app.instance_path = str(tmp_path)
    yield tmp_path


def daily(days, value=100.0, code="EUR"):
    return market_data.Daily(code, "X", None, [(d, Decimal(str(value + i)), None) for i, d in enumerate(days)])


def test_a_store_of_schema_1_gets_the_link_column(app, store):
    old = create_engine(f"sqlite:///{store / market_data.FILE}")
    with old.begin() as conn:
        conn.execute(text("CREATE TABLE meta (key VARCHAR(40) PRIMARY KEY, value TEXT)"))
        conn.execute(text("INSERT INTO meta VALUES ('schema', '1')"))
        conn.execute(text("CREATE TABLE instruments (id INTEGER PRIMARY KEY, symbol VARCHAR(40) NOT NULL UNIQUE, "
                          "isin VARCHAR(12), name TEXT, currency VARCHAR(8), exchange VARCHAR(40), first_day DATE, "
                          "last_day DATE, synced_at DATETIME, error TEXT)"))
        conn.execute(text("INSERT INTO instruments (symbol, isin) VALUES ('VWCE.MI', :isin)"), {"isin": VWCE})
    old.dispose()
    market_data._engines.clear()
    assert market_data.schema_version() == 2
    market_data.set_link("VWCE.MI", "https://www.justetf.com/x")
    assert market_data.links() == {"VWCE.MI": "https://www.justetf.com/x"}


def test_links_are_shared_and_the_old_ones_move_there(app, db, store):
    assert market_data.links() == {}  # no store yet: nothing, and no file made
    assert not (store / market_data.FILE).exists()
    settings_store.set_json(history_links.KEY, {"VWCE.MI": f"https://www.justetf.com/it/etf-profile.html?isin={VWCE}"})
    assert history_links.links() == {"VWCE.MI": f"https://www.justetf.com/it/etf-profile.html?isin={VWCE}"}
    assert settings_store.get_json(history_links.KEY, {}) == {}  # moved out of the archive
    assert market_data.links() == history_links.links()
    history_links.forget("VWCE.MI")
    history_links.forget("NONE")
    assert market_data.links() == {}


def test_a_ticker_found_once_is_not_looked_up_again(app, db, store, monkeypatch):
    asked = []
    monkeypatch.setattr(price_feed, "lookup", lambda isin: asked.append(isin) or [
        price_feed.Candidate("VWCE.MI", "Vanguard", "ETF", "Milano", isin)])
    first = Holding(name="Vanguard", isin=VWCE, asset_class="ETF", quantity=1, avg_price=1)
    price_feed._resolve_ticker(first)
    assert first.ticker == "VWCE.MI" and asked == [VWCE]
    assert market_data.symbol_for_isin(VWCE) == "VWCE.MI" and market_data.symbol_for_isin(None) is None
    again = Holding(name="Vanguard", isin=VWCE.lower(), asset_class="ETF", quantity=1, avg_price=1)
    price_feed._resolve_ticker(again)  # another archive: from the store
    assert again.ticker == "VWCE.MI" and asked == [VWCE]
    # two listings: the one with more closes
    market_data.store("VWCE.DE", daily([date(2026, 11, 2), date(2026, 11, 3)]), VWCE)
    assert market_data.symbol_for_isin(VWCE) == "VWCE.DE"
    assert market_data.symbol_for_isin("XX0000000000") is None


def test_a_broken_store_does_not_stop_the_lookup(app, db, store, monkeypatch):
    monkeypatch.setattr(price_feed, "lookup", lambda isin: [price_feed.Candidate("SWDA.MI", "x", "ETF",
                                                                                 "Milano", isin)])

    def broken(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(market_data, "remember_listing", broken)
    holding = Holding(name="iShares", isin="IE00B4L5Y983", asset_class="ETF", quantity=1, avg_price=1)
    price_feed._resolve_ticker(holding)
    assert holding.ticker == "SWDA.MI"


def test_export_and_import_keep_everything(app, store):
    assert market_data.totals()["closes"] == 0 and market_data.totals()["where"] is None
    market_data.store("VWCE.MI", daily([date(2026, 11, 2), date(2026, 11, 3)]), VWCE, "Vanguard")
    market_data.store("CSPX.L", daily([date(2026, 11, 2)], 500.0, "USD"), "IE00B5BMR087")
    market_data.set_link("VWCE.MI", "https://www.justetf.com/x")
    market_data.remember_listing("SWDA.MI", "IE00B4L5Y983")  # a listing with no close yet
    totals = market_data.totals()
    assert (totals["instruments"], totals["closes"], totals["first"], totals["last"]) == (3, 3, date(2026, 11, 2), date(2026, 11, 3))
    assert totals["where"].endswith(market_data.FILE)
    raw = market_data.export_zip()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert set(archive.namelist()) == {"instruments.csv", "closes.csv", "meta.json"}
        assert "VWCE.MI,2026-11-03,101," in archive.read("closes.csv").decode()
        assert "https://www.justetf.com/x" in archive.read("instruments.csv").decode()

    # another computer: one close of its own (kept), a different link (kept), the rest added
    other = store / "other"
    other.mkdir()
    app.instance_path = str(other)
    market_data.store("VWCE.MI", daily([date(2026, 11, 3)], 999.0))
    market_data.set_link("VWCE.MI", "https://mine")
    done = market_data.import_zip(raw)
    assert (done.instruments, done.closes, done.kept, done.skipped) == (2, 2, 1, 0)
    assert market_data.history("VWCE.MI") == [(date(2026, 11, 2), Decimal("100")), (date(2026, 11, 3), Decimal("999"))]
    assert market_data.links() == {"VWCE.MI": "https://mine"}
    assert market_data.symbol_for_isin("IE00B4L5Y983") == "SWDA.MI"
    assert market_data.sources_of("CSPX.L") == ["yahoo"]
    again = market_data.import_zip(raw)  # twice: nothing new
    assert (again.instruments, again.closes, again.kept) == (0, 0, 3)


def test_import_rejects_and_skips(app, store):
    with pytest.raises(ValueError):
        market_data.import_zip(b"not a zip")
    only = io.BytesIO()
    with zipfile.ZipFile(only, "w") as archive:
        archive.writestr("closes.csv", "symbol,day,close\n")
    with pytest.raises(ValueError, match="mancanti"):
        market_data.import_zip(only.getvalue())
    odd = io.BytesIO()
    with zipfile.ZipFile(odd, "w") as archive:
        archive.writestr("instruments.csv", "symbol,isin,name,currency,exchange,link\n,,,,,\nNEW.MI,,,EUR,,\n")
        archive.writestr("closes.csv", "symbol,day,close,adj_close,source\nNEW.MI,2026-11-02,10,9.5,\nNEW.MI,2026-11-04,12,=,\n"
                                       "NEW.MI,bad,1,,x\nNEW.MI,2026-11-03,0,,x\nLOOSE.MI,2026-11-02,5,,stooq\n"
                                       "CL.F,2020-04-20,-37.63,,yahoo\n")
    done = market_data.import_zip(odd.getvalue())
    assert (done.instruments, done.closes, done.skipped) == (3, 4, 3)  # the empty listing, the bad day, the zero
    assert market_data.sources_of("NEW.MI") == ["file"] and market_data.sources_of("LOOSE.MI") == ["stooq"]
    assert market_data.history("CL.F") == [(date(2020, 4, 20), Decimal("-37.63"))]  # oil below zero: a real close
    assert market_data.history("NEW.MI")[-1] == (date(2026, 11, 4), Decimal("12"))
    small = market_data.export_zip(smallest=True)
    with zipfile.ZipFile(io.BytesIO(small)) as archive:
        assert archive.getinfo("closes.csv").compress_type == zipfile.ZIP_LZMA
        assert "NEW.MI,2026-11-04,12,=," in archive.read("closes.csv").decode()


def test_the_page_export_and_import(client, db, store):
    page = client.get("/dati/prezzi").get_data(as_text=True)
    assert "Database dei prezzi" in page and "condiviso da tutti gli archivi" in page
    empty = client.get("/dati/prezzi/esporta", follow_redirects=True).get_data(as_text=True)
    assert "ancora vuoto" in empty
    market_data.store("VWCE.MI", daily([date(2026, 11, 2)]), VWCE)
    got = client.get("/dati/prezzi/esporta")
    assert got.mimetype == "application/zip" and "MyFinancePlace_prezzi_" in got.headers["Content-Disposition"]
    raw = got.data
    none = client.post("/dati/prezzi/importa", data={}, follow_redirects=True).get_data(as_text=True)
    assert "Scegli il file .zip" in none
    bad = client.post("/dati/prezzi/importa", data={"file": (io.BytesIO(b"x"), "x.zip")},
                      content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "File non letto" in bad
    same = client.post("/dati/prezzi/importa", data={"file": (io.BytesIO(raw), "prezzi.zip")},
                       content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "0 titoli nuovi, 0 chiusure nuove, 1 già presenti" in same
    odd = io.BytesIO()
    with zipfile.ZipFile(odd, "w") as archive:
        archive.writestr("instruments.csv", "symbol\n")
        archive.writestr("closes.csv", "symbol,day,close\nA.MI,bad,1\n")
    skipped = client.post("/dati/prezzi/importa", data={"file": (io.BytesIO(odd.getvalue()), "p.zip")},
                          content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "1 righe non leggibili saltate" in skipped


def _seed(tmp_path):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr("instruments.csv", "symbol,isin,name,currency,exchange,link\nENEL.MI,IT0003128367,Enel,EUR,,\n")
        archive.writestr("closes.csv", "symbol,day,close,adj_close,source\nENEL.MI,2000-01-03,5.1,,yahoo\n"
                                       "ENEL.MI,2000-01-04,5.2,,yahoo\n")
    path = tmp_path / "seed.zip"
    path.write_bytes(raw.getvalue())
    return path


def test_an_empty_store_starts_from_the_shipped_one(app, store, monkeypatch):
    assert market_data.seed_path() is None  # tests: off
    app.config["MARKET_SEED"] = True
    try:
        monkeypatch.setattr(market_data, "SEED", store / "missing.zip")
        assert market_data.seed_path() is None and market_data.seed_if_empty() is None
        monkeypatch.setattr(market_data, "SEED", _seed(store))
        done = market_data.seed_if_empty()
        assert (done.instruments, done.closes) == (1, 2)
        assert market_data.seed_if_empty() is None  # not empty any more
        assert market_data.symbol_for_isin("IT0003128367") == "ENEL.MI"
    finally:
        app.config["MARKET_SEED"] = False


def test_the_filler_seeds_first_and_the_button(client, db, store, monkeypatch):
    from app.services import history_filler
    app = client.application
    assert "Questa installazione non ha il database di partenza" in client.post(
        "/dati/prezzi/partenza", follow_redirects=True).get_data(as_text=True)
    app.config["MARKET_SEED"] = True
    try:
        monkeypatch.setattr(market_data, "SEED", _seed(store))
        page = client.get("/dati/prezzi").get_data(as_text=True)
        assert "Importa il database di partenza" in page
        done = client.post("/dati/prezzi/partenza", follow_redirects=True).get_data(as_text=True)
        assert "Database di partenza importato: 1 titoli nuovi, 2 chiusure nuove" in done
        other = store / "fresh"
        other.mkdir()
        app.instance_path = str(other)
        with app.app_context():
            history_filler.run(date(2026, 11, 20), sources=(), fetch=lambda address: b"x")
            assert market_data.totals()["closes"] == 2

            def broken(raw):
                raise ValueError("bad")
            monkeypatch.setattr(market_data, "import_zip", broken)
            app.instance_path = str(store / "third")
            history_filler.run(date(2026, 11, 20), sources=(), fetch=lambda address: b"x")  # goes on all the same
    finally:
        app.config["MARKET_SEED"] = False


def test_an_empty_store_is_seeded_on_the_first_visit_with_or_without_internet(client, store, monkeypatch):
    app = client.application
    assert market_data.seed_in_background() is False  # the tests: no shipped database
    app.config["MARKET_SEED"] = True
    monkeypatch.setattr(market_data, "SEED", _seed(store))
    monkeypatch.setattr(market_data, "_seeded", set())
    try:
        client.get("/dashboard")  # «Prezzi da internet» off: the shipped prices come all the same
        assert market_data.totals()["closes"] == 2
        assert market_data.seed_in_background() is False  # once per store and process
        # another store, already filled: checked, nothing to do
        other = store / "full"
        other.mkdir()
        app.instance_path = str(other)
        market_data.store("X.MI", market_data.Daily("EUR", None, None, [(date(2026, 1, 2), Decimal(1), None)]))
        with app.test_request_context():
            assert market_data.seed_in_background() is False
        # in a thread outside the tests; an error is logged, never raised
        app.instance_path = str(store / "fresh")
        app.config["PRICES_SYNC"] = False
        started = []
        monkeypatch.setattr("threading.Thread", lambda target, args, **kw: started.append((target, args)) or
                            type("T", (), {"start": lambda self: None})())
        with app.test_request_context():
            assert market_data.seed_in_background() is True
        target, args = started[0]
        target(*args)
        with app.app_context():
            assert market_data.totals()["closes"] == 2

        def broken():
            raise OSError("disk full")
        monkeypatch.setattr(market_data, "seed_if_empty", broken)
        target(*args)  # logged
    finally:
        app.config["MARKET_SEED"] = False
        app.config["PRICES_SYNC"] = True
