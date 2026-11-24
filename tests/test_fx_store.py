"""F116: the exchange rates in the shared price database — the main ones with the starting database, any other the
ECB publishes added from Dati → Cambi, one it does not from a CSV file — and brought up to date once a day."""
import io
import zipfile
from datetime import date
from decimal import Decimal

import pytest

from app.services import fx_store, history_filler, market_data, settings_store

TODAY = date(2026, 11, 20)


@pytest.fixture()
def store(app, tmp_path, monkeypatch):
    monkeypatch.delenv(market_data.ENV, raising=False)
    app.instance_path = str(tmp_path)
    yield


def ecb_zip(rows, header="Date,USD,JPY,GBP,TWD,"):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("eurofxref-hist.csv", header + "\n" + "\n".join(rows) + "\n")
    return out.getvalue()


RAW = ecb_zip(["2026-11-03,1.25,160.1,0.85,", "2026-11-02,1.20,160.0,N/A,", "bad,1,1,1,"])


def test_the_ecb_history_by_currency(app, store):
    assert fx_store.parse_ecb_history(RAW, ("USD", "GBP", "CHF")) == {
        "USD": [(date(2026, 11, 2), Decimal("1.20")), (date(2026, 11, 3), Decimal("1.25"))],
        "GBP": [(date(2026, 11, 3), Decimal("0.85"))]}
    assert fx_store.listed() == []  # no price database yet
    assert fx_store.store_ecb(RAW, ("USD", "GBP")) == 3
    assert market_data.history("FX.USD") == [(date(2026, 11, 2), Decimal("1.2")), (date(2026, 11, 3), Decimal("1.25"))]
    rows = fx_store.listed()
    assert [(r["code"], r["first"], r["last"], r["count"], r["sources"]) for r in rows] == [
        ("GBP", date(2026, 11, 3), date(2026, 11, 3), 1, ["ecb"]),
        ("USD", date(2026, 11, 2), date(2026, 11, 3), 2, ["ecb"])]
    assert "USD" not in fx_store.addable() and "JPY" in fx_store.addable() and "TWD" not in fx_store.addable()


def test_add_from_the_ecb_and_from_a_file(app, store):
    assert fx_store.add_from_ecb("jpy", fetch=lambda address: RAW) == 2
    with pytest.raises(ValueError):
        fx_store.add_from_ecb("TWD", fetch=lambda address: RAW)  # the ECB does not publish it
    with pytest.raises(ValueError):
        fx_store.add_from_ecb("CHF", fetch=lambda address: RAW)  # published, but not in this file
    daily = fx_store.add_from_csv("twd", b"Data;Cambio\n02/11/2026;34,5\n03/11/2026;34,7\n")
    assert len(daily.points) == 2 and market_data.sources_of("FX.TWD") == ["file"]
    for code in ("EUR", "TW", "12A"):
        with pytest.raises(ValueError):
            fx_store.add_from_csv(code, b"Date,Close\n2026-11-02,1\n")


def test_brought_up_to_date_once_a_day(app, store):
    assert fx_store.refresh(TODAY, fetch=lambda address: pytest.fail("nothing to bring up to date")) == 0
    fx_store.store_ecb(RAW, ("USD",))
    fx_store.add_from_csv("TWD", b"Date,Close\n2026-11-02,34.5\n")  # from a file: not from the ECB
    later = ecb_zip(["2026-11-19,1.30,161,0.86,", "2026-11-03,1.25,160.1,0.85,"])
    asked = []
    assert fx_store.refresh(TODAY, fetch=lambda address: asked.append(address) or later) == 2
    assert asked == [history_filler.ECB_HISTORY] and market_data.days("FX.USD")[-1] == date(2026, 11, 19)
    assert fx_store.refresh(TODAY, fetch=lambda address: pytest.fail("up to date")) == 0
    # a currency the ECB stopped publishing (the lev, Bulgaria in the euro): not asked for every day
    fx_store.store_ecb(ecb_zip(["2025-12-31,1.9558,1,1,"], header="Date,BGN,JPY,GBP,TWD,"), ("BGN",))
    assert fx_store.refresh(TODAY, fetch=lambda address: pytest.fail("the lev is gone")) == 0


def test_the_filler_brings_them_up_to_date_and_goes_on_without(app, db, store, monkeypatch):
    fx_store.store_ecb(RAW, ("USD",))
    later = ecb_zip(["2026-11-19,1.30,161,0.86,"])
    history_filler.run(TODAY, sources=(), fetch=lambda address: later)
    assert market_data.days("FX.USD")[-1] == date(2026, 11, 19)

    def broken(today=None, fetch=None):
        raise OSError("no network")
    monkeypatch.setattr(fx_store, "refresh", broken)
    assert history_filler.run(TODAY, sources=(), fetch=lambda address: later).rates_error is None


def test_the_page_and_its_forms(client, db, store, monkeypatch):
    page = client.get("/dati/cambi").get_data(as_text=True)
    assert "Cambi nel database dei prezzi" in page and "Ancora nessun cambio" in page and 'value="USD"' in page
    off = client.post("/dati/cambi/aggiungi", data={"code": "USD"}, follow_redirects=True).get_data(as_text=True)
    assert "prezzi da internet sono spenti" in off
    settings_store.set_json("ui.settings", {"prices_online": True})
    monkeypatch.setattr(fx_store, "_ecb_zip", lambda fetch=None: RAW)
    done = client.post("/dati/cambi/aggiungi", data={"code": "usd"}, follow_redirects=True).get_data(as_text=True)
    assert "USD aggiunta: 2 cambi BCE" in done and "Dollaro USA" in done
    bad = client.post("/dati/cambi/aggiungi", data={"code": "XXX"}, follow_redirects=True).get_data(as_text=True)
    assert "Cambi di XXX non letti dalla BCE" in bad
    no_file = client.post("/dati/cambi/file", data={"code": "TWD"}, follow_redirects=True).get_data(as_text=True)
    assert "Scegli il file CSV dei cambi" in no_file
    loaded = client.post("/dati/cambi/file", data={"code": "twd", "file": (io.BytesIO(b"Date,Close\n2026-11-02,34.5\n"), "twd.csv")},
                         content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "TWD: 1 cambi dal 02/11/2026 al 02/11/2026" in loaded
    unreadable = client.post("/dati/cambi/file", data={"code": "TWD", "file": (io.BytesIO(b"nothing"), "x.csv")},
                             content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "File non letto" in unreadable
    no_code = client.post("/dati/cambi/file", data={"code": "EUR", "file": (io.BytesIO(b"Date,Close\n2026-11-02,1\n"), "x.csv")},
                          content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "tre lettere" in no_code
