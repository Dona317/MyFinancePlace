"""F112: «Incolla il link» — the history of a holding from the page of a site (justETF, Borsa Italiana, any page with
the ISIN in its address) read from justETF by the ISIN, the link saved for the daily update; justETF as the third
automatic source of the filler."""
import io
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.wealth import Holding
from app.services import history_filler, history_links, market_data, settings_store
from tests.conftest import make_tx

TODAY = date(2026, 11, 20)
VWCE = "IE00BK5BQT80"


@pytest.fixture()
def store(app, tmp_path, monkeypatch):
    monkeypatch.delenv(market_data.ENV, raising=False)
    app.instance_path = str(tmp_path)
    yield


def _etf(db, ticker="VWCE.MI", isin=VWCE, first=date(2026, 11, 2)):
    holding = Holding(name="Vanguard FTSE All-World", ticker=ticker, isin=isin, asset_class="ETF", quantity=10,
                      avg_price=100, opening_quantity=0, opening_price=0)
    db.session.add(holding)
    db.session.flush()
    db.session.add(make_tx(date=first, type="transfer", amount=1000, holding_id=holding.id, units=10, unit_price=100))
    db.session.commit()
    return holding


def chart(start, end, value=140.0):
    """justETF's answer: every calendar day, the weekends repeating the Friday."""
    series, day = [], start
    while day <= end:
        series.append({"date": day.isoformat(), "value": {"raw": value + day.toordinal() % 7, "localized": "x"}})
        day += timedelta(days=1)
    return {"latestQuote": {"raw": value}, "series": series + [{"date": "bad", "value": {}}]}


def test_links_recognised_by_site_and_isin(app):
    direct = history_links.recognise(f"https://www.justetf.com/it/etf-profile.html?isin={VWCE}")
    assert (direct.site, direct.isin, direct.direct) == ("justetf", VWCE, True)
    borsa = history_links.recognise(f"www.borsaitaliana.it/borsa/etf/scheda/{VWCE}.html?lang=it")
    assert (borsa.site, borsa.name, borsa.isin, borsa.direct) == ("borsaitaliana", "Borsa Italiana", VWCE, False)
    other = history_links.recognise(f"https://example.org/fondo/{VWCE.lower()}")
    assert (other.site, other.name, other.isin) == ("other", "example.org", VWCE)
    with pytest.raises(ValueError, match="CSV"):
        history_links.recognise("https://it.investing.com/etfs/vanguard-ftse-all-world-ucits-acc-historical-data")
    with pytest.raises(ValueError, match="ISIN"):
        history_links.recognise("https://global.morningstar.com/it/investimenti/etf/0P0001I9HA/quotazione")
    with pytest.raises(ValueError, match="ISIN"):  # twelve characters, a wrong check digit
        history_links.recognise("https://www.justetf.com/it/etf-profile.html?isin=IE00BK5BQT81")
    with pytest.raises(ValueError, match="link"):
        history_links.recognise("ftp://nowhere")


def test_justetf_answer_without_weekends(app):
    daily = history_links.parse_justetf(chart(date(2026, 11, 13), date(2026, 11, 17)), "USD")
    assert [p[0] for p in daily.points] == [date(2026, 11, 13), date(2026, 11, 16), date(2026, 11, 17)]
    assert daily.currency == "USD" and isinstance(daily.points[0][1], Decimal)
    asked = []
    got = history_links.read_justetf(VWCE, date(2026, 11, 13), date(2026, 11, 17),
                                     fetch=lambda address: asked.append(address) or chart(date(2026, 11, 13), date(2026, 11, 13)))
    assert len(got.points) == 1 and f"/etfs/{VWCE}/" in asked[0] and "currency=EUR" in asked[0]
    assert "dateFrom=2026-11-13" in asked[0] and "dateTo=2026-11-17" in asked[0]
    with pytest.raises(ValueError):
        history_links.read_justetf(VWCE, TODAY, TODAY, fetch=lambda address: {"series": []})


def test_paste_a_link_reads_the_history_and_saves_it(app, db, store):
    _etf(db)
    asked = []

    def fetch(address):
        asked.append(address)
        return chart(date(2026, 9, 24), TODAY)
    done = history_links.apply("VWCE.MI", f"https://www.borsaitaliana.it/borsa/etf/scheda/{VWCE}.html", TODAY, fetch)
    assert done.added == len(history_filler.trading_days(date(2026, 9, 24), TODAY)) and done.last == TODAY
    assert "dateFrom=2026-09-25" in asked[0]  # a month before the first operation, a week more
    assert market_data.sources_of("VWCE.MI") == ["justetf"]
    assert history_links.links() == {"VWCE.MI": f"https://www.borsaitaliana.it/borsa/etf/scheda/{VWCE}.html"}
    assert history_links.isin_of("VWCE.MI") == VWCE and history_links.isin_of("NOPE") is None
    with pytest.raises(ValueError, match="non è tra i titoli"):
        history_links.apply("NOPE.MI", f"https://www.justetf.com/it/etf-profile.html?isin={VWCE}", TODAY, fetch)
    with pytest.raises(ValueError, match="ISIN IE00B5BMR087"):  # the page of another instrument
        history_links.apply("VWCE.MI", "https://www.justetf.com/it/etf-profile.html?isin=IE00B5BMR087", TODAY, fetch)
    history_links.forget("VWCE.MI")
    history_links.forget("VWCE.MI")
    assert history_links.links() == {}


def test_pence_are_not_read_from_justetf(app, db, store):
    _etf(db, ticker="VUSA.L", isin="IE00B3XXRP09")
    market_data.store("VUSA.L", market_data.Daily("GBp", "LSE", None, [(date(2026, 11, 2), Decimal("8000"), None)]))
    assert history_links.quoted_in("VUSA.L") is None and history_links.quoted_in("NEW.MI") == "EUR"
    with pytest.raises(ValueError, match="pence"):
        history_links.apply("VUSA.L", "https://www.justetf.com/it/etf-profile.html?isin=IE00B3XXRP09", TODAY,
                            lambda address: chart(TODAY, TODAY))
    assert history_links.sources_for(history_filler.targets(TODAY)[0]) == []


def test_justetf_is_the_third_source_of_the_filler(app, db, store, monkeypatch):
    _etf(db)
    asked = []
    monkeypatch.setattr(history_links, "read_justetf", lambda isin, start, end, code="EUR", fetch=None:
                        asked.append((isin, code)) or market_data.Daily(code, "justETF", None,
                                                                        [(d, Decimal("150"), None) for d in history_filler.trading_days(start, end)]))
    monkeypatch.setattr(history_filler, "SOURCES", (("yahoo", lambda s, a, b: (_ for _ in ()).throw(OSError("down"))),))
    target = history_filler.targets(TODAY)[0]
    result = history_filler.fill(target, TODAY)
    assert result.sources == ["justetf"] and result.holes == 0 and asked[0] == (VWCE, "EUR")
    # the ISIN of the link saved wins over the instrument's own; a link no longer readable: its own
    settings_store.set_json(history_links.KEY, {"VWCE.MI": "https://www.justetf.com/it/etf-profile.html?isin=IE00B5BMR087"})
    history_links.sources_for(target)[0][1]("VWCE.MI", TODAY, TODAY)
    assert asked[-1][0] == "IE00B5BMR087"
    settings_store.set_json(history_links.KEY, {"VWCE.MI": "https://it.investing.com/etfs/x"})
    history_links.sources_for(target)[0][1]("VWCE.MI", TODAY, TODAY)
    assert asked[-1][0] == VWCE
    target.isin = None
    settings_store.set_json(history_links.KEY, {})
    assert history_links.sources_for(target) == []


def test_the_network_reader(app, monkeypatch):
    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False
    seen = []
    monkeypatch.setattr(history_links.urllib.request, "urlopen",
                        lambda request, timeout: seen.append(request) or Answer(json.dumps({"series": []}).encode()))
    assert history_links._json("https://www.justetf.com/api/x") == {"series": []}
    assert seen[0].get_header("Accept") == "application/json"


def test_the_page_and_its_buttons(client, db, store, monkeypatch):
    _etf(db)
    page = client.get("/dati/prezzi").get_data(as_text=True)
    assert "Incolla il link" in page and 'value="VWCE.MI"' in page and "Link salvato" not in page
    link = f"https://www.justetf.com/it/etf-profile.html?isin={VWCE}"
    off = client.post("/dati/prezzi/link", data={"symbol": "VWCE.MI", "url": link}, follow_redirects=True)
    assert "prezzi da internet sono spenti" in off.get_data(as_text=True)
    settings_store.set_json("ui.settings", {"prices_online": True})
    real = history_links.read_justetf
    monkeypatch.setattr(history_links, "read_justetf", lambda isin, start, end, code="EUR", fetch=None:
                        real(isin, start, end, code, fetch=lambda address: chart(date(2026, 11, 2), date(2026, 11, 6))))
    done = client.post("/dati/prezzi/link", data={"symbol": "vwce.mi", "url": link}, follow_redirects=True)
    text = done.get_data(as_text=True)
    assert "5 chiusure lette, dal 02/11/2026 al 06/11/2026" in text and "Link salvato" in text and "justETF" in text
    borsa = client.post("/dati/prezzi/link", data={"symbol": "VWCE.MI",
                                                   "url": f"https://www.borsaitaliana.it/borsa/etf/scheda/{VWCE}.html"},
                        follow_redirects=True).get_data(as_text=True)
    assert "link di Borsa Italiana, letto da justETF con l&#39;ISIN" in borsa or "link di Borsa Italiana, letto da justETF con l'ISIN" in borsa
    bad = client.post("/dati/prezzi/link", data={"symbol": "VWCE.MI", "url": "https://it.investing.com/x"},
                      follow_redirects=True).get_data(as_text=True)
    assert "Carica lo storico" in bad

    def down(*args, **kwargs):
        raise OSError("timeout")
    monkeypatch.setattr(history_links, "read_justetf", down)
    assert "Storico non letto da justETF: timeout" in client.post(
        "/dati/prezzi/link", data={"symbol": "VWCE.MI", "url": link}, follow_redirects=True).get_data(as_text=True)
    gone = client.post("/dati/prezzi/link/togli", data={"symbol": "VWCE.MI"}, follow_redirects=True).get_data(as_text=True)
    assert "Link tolto" in gone and "Link salvato" not in gone
