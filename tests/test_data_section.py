"""Dati (23 Nov 2026): Cambi — the currencies in use and where their rates are missing; Prezzi storici; the state
of the market data update for the pill at the bottom (the X hides it, the update goes on)."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.currency import ExchangeRate
from app.models.wealth import Holding
from app.services import fx_status, history_filler, market_data, settings_store
from tests.conftest import make_tx

TODAY = date(2026, 11, 20)


@pytest.fixture()
def store(app, tmp_path, monkeypatch):
    monkeypatch.delenv(market_data.ENV, raising=False)
    app.instance_path = str(tmp_path)
    yield


def test_rates_report_says_what_is_missing(app, db, store):
    db.session.add_all([make_tx(date=date(2026, 9, 1), amount=10, currency="USD"),
                        make_tx(date=date(2026, 11, 2), amount=10, currency="USD"),
                        make_tx(date=date(2026, 11, 2), amount=5, currency="GBP")])
    for day in (date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 19), date(2026, 10, 20)):
        db.session.add(ExchangeRate(currency="USD", on=day, rate=Decimal("0.9"), source="ecb"))
    db.session.commit()
    rows = {r["code"]: r for r in fx_status.report(TODAY)}
    usd, gbp = rows["USD"], rows["GBP"]
    assert usd["needed_from"] == date(2026, 9, 1) and usd["count"] == 4
    assert usd["uncovered"] == 1 and usd["status"] == "missing"  # the September movement: before the first rate
    assert usd["late_start"] and usd["stale"] and usd["holes"] == [(date(2026, 10, 5), date(2026, 10, 16))]
    assert gbp["count"] == 0 and gbp["status"] == "missing" and gbp["uncovered"] == 1
    assert fx_status.problems(TODAY) == 2


def test_the_pages_and_the_menu(client, db, store):
    db.session.add(make_tx(date=date(2026, 11, 2), amount=10, currency="USD"))
    db.session.commit()
    page = client.get("/dati/cambi").get_data(as_text=True)
    assert "Le valute che usi" in page and "USD" in page and "contato 1:1" in page
    menu = page.split('class="sidebar-nav"')[1]
    assert 'href="/dati/cambi"' in menu and 'href="/dati/prezzi"' in menu and "nav-badge-warn" in menu
    assert client.get("/dati/").headers["Location"].endswith("/dati/cambi")
    assert "Storico dei tuoi titoli" in client.get("/dati/prezzi").get_data(as_text=True)
    assert 'id="data-progress"' in page  # the pill, in every page


def test_the_ecb_button(client, db, store, monkeypatch):
    assert "Nessuna valuta" in client.post("/dati/cambi/bce", follow_redirects=True).get_data(as_text=True)
    monkeypatch.setattr(history_filler, "fill_rates", lambda: {"currencies": ["USD"], "added": 3})
    assert "Cambi BCE di USD: 3 nuovi" in client.post("/dati/cambi/bce", follow_redirects=True).get_data(as_text=True)

    def broken():
        raise OSError("offline")
    monkeypatch.setattr(history_filler, "fill_rates", broken)
    assert "Cambi BCE non letti: offline" in client.post("/dati/cambi/bce", follow_redirects=True).get_data(as_text=True)


def test_update_runs_in_the_background_and_tells_its_state(client, db, store, monkeypatch, app):
    assert client.get("/dati/stato").get_json()["state"] in ("idle", "done")
    assert "spenti" in client.post("/dati/aggiorna", follow_redirects=True).get_data(as_text=True)
    settings_store.set_json("ui.settings", {"prices_online": True})
    db.session.add(Holding(name="ETF", ticker="VWCE.MI", asset_class="ETF", quantity=1, avg_price=1,
                           purchase_date=date(2026, 11, 2)))
    db.session.commit()
    steps = []
    monkeypatch.setattr(history_filler, "fill", lambda target, today=None, sources=None:
                        steps.append(history_filler.status()["done"]) or history_filler.Filled(target.symbol, added=5))
    monkeypatch.setattr(history_filler, "fill_rates", lambda today=None, fetch=None: {"currencies": [], "added": 0})
    app.config["PRICES_SYNC"] = True
    try:
        response = client.post("/dati/aggiorna?next=/portfolio/prices", follow_redirects=False)
    finally:
        app.config["PRICES_SYNC"] = False
    assert response.headers["Location"].endswith("/portfolio/prices") and steps == [0]
    state = client.get("/dati/stato").get_json()
    assert state["state"] == "done" and state["summary"]["closes"] == 5 and state["total"] == 2
    # the portfolio's button goes the same way
    assert client.post("/portfolio/market/fill").status_code == 307
