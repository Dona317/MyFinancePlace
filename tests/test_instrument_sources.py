"""
F19a-bis: ISINs looked up and prices read on five preset sites (Yahoo, OpenFIGI, justETF, Borsa Italiana, Morningstar),
chosen and ordered in Settings. The pages in tests/fixtures/instrument_sources are written by hand with the structure of
the real ones; the network is canned.
"""
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.wealth import Holding
from app.services import instrument_sources as sources
from app.services import price_feed, settings_store
from app.services.instrument_sources import base, borsaitaliana, justetf, morningstar, openfigi
from tests.test_price_feed import _yahoo, web  # noqa: F401 - web is a fixture

PAGES = Path(__file__).parent / "fixtures" / "instrument_sources"
ETF, BTP, FUND = "IE00BK5BQT80", "IT0005436693", "LU0000000001"


def page(name: str) -> str:
    return (PAGES / name).read_text(encoding="utf-8")


@pytest.fixture()
def sites(web):  # noqa: F811
    answers, calls = web
    answers.update({
        "api.openfigi.com": json.loads(page("openfigi.json")),
        f"etf-profile.html?isin={ETF}": page("justetf_profile.html"),
        f"api/etfs/{ETF}/quote": json.loads(page("justetf_quote.json")),
        f"risultati.html?q={BTP}": page("borsaitaliana_search_btp.html"),
        f"scheda/{BTP}.html": page("borsaitaliana_btp.html"),
        f"risultati.html?q={ETF}": page("borsaitaliana_search_etf.html"),
        f"etf/scheda/{ETF}.html": page("borsaitaliana_etf.html"),
        f"SecuritySearch.ashx?q={FUND}": page("morningstar_search.txt"),
        "snapshot.aspx?id=F00000XYZ1": page("morningstar_fund.html"),
    })
    return answers, calls


def _json_answers(answers):
    """The canned JSON answers reach the adapters as text, like the real network."""
    for key, value in list(answers.items()):
        if isinstance(value, (dict, list)):
            answers[key] = json.dumps(value)


# ── One reader per site ────────────────────────────────────────────────────────

def test_openfigi(app, sites):
    answers, _ = sites
    _json_answers(answers)
    with app.test_request_context():
        found = openfigi.find(ETF)
        assert [(c.symbol, c.exchange, c.asset_class, c.source) for c in found] == [
            ("VWCE.MI", "Milano", "ETF", "openfigi"), ("VWCE.DE", "Xetra", "ETF", "openfigi")]  # GR = GY; QX unknown
        answers["api.openfigi.com"] = json.dumps([{"warning": "No identifier found."}])
        with pytest.raises(base.NotFound):
            openfigi.find(ETF)
        answers["api.openfigi.com"] = json.dumps({"error": "x"})
        with pytest.raises(base.Broken):
            openfigi.find(ETF)
        answers["api.openfigi.com"] = json.dumps([{"data": [{"ticker": "X", "exchCode": "QX", "marketSector": "Equity"}]}])
        with pytest.raises(base.NotFound, match="borsa conosciuta"):
            openfigi.find(ETF)
        answers["api.openfigi.com"] = "<html>"
        with pytest.raises(base.Broken):
            openfigi.find(ETF)
    kinds = [openfigi.asset_class(i) for i in (
        {"marketSector": "Equity", "securityType": "Common Stock"}, {"marketSector": "Govt", "securityType": "BTP"},
        {"marketSector": "Equity", "securityType": "Open-End Fund"}, {"marketSector": "Equity", "securityType": "Equity Option"},
        {"marketSector": "Comdty", "securityType": "Index"})]
    assert kinds == ["Azione", "Obbligazione", "Fondo", "Derivato", None]


def test_justetf(app, sites):
    answers, _ = sites
    _json_answers(answers)
    with app.test_request_context():
        (found,) = justetf.find(ETF)
        assert (found.symbol, found.name, found.price_source) == (
            "VWCE", "Vanguard FTSE All-World UCITS ETF (USD) Accumulating", "justetf")
        quote = justetf.quote(ETF)
        assert (quote.price, quote.on, quote.currency) == (Decimal("131.42"), date(2026, 10, 9), "EUR")
        answers[f"etf-profile.html?isin={ETF}"] = "<html><h1>Cerca ETF</h1></html>"
        with pytest.raises(base.NotFound):
            justetf.find(ETF)
        answers[f"etf-profile.html?isin={ETF}"] = f"<html>{ETF}</html>"
        with pytest.raises(base.Broken):
            justetf.find(ETF)
        answers[f"api/etfs/{ETF}/quote"] = json.dumps({"latestQuote": {"localized": "131,5"}})
        with pytest.raises(base.Broken):
            justetf.quote(ETF)


def test_borsa_italiana(app, sites):
    answers, _ = sites
    with app.test_request_context():
        (bond,) = borsaitaliana.find(BTP)
        assert (bond.name, bond.asset_class, bond.exchange, bond.price_source) == (
            "Btp-1ag31 0,6%", "Obbligazione", "Borsa Italiana", "borsaitaliana")
        quote = borsaitaliana.quote(BTP)
        assert (quote.price, quote.on) == (Decimal("0.8547"), date(2026, 10, 9))  # 85,47 % of the face value
        assert borsaitaliana.quote(ETF).price == Decimal("131.30") and borsaitaliana.find(ETF)[0].asset_class == "ETF"
        answers[f"risultati.html?q={BTP}"] = "<html>Nessun risultato</html>"
        with pytest.raises(base.NotFound):
            borsaitaliana.find(BTP)
        answers[f"risultati.html?q={BTP}"] = page("borsaitaliana_search_btp.html")
        answers[f"scheda/{BTP}.html"] = "<html><p>nuova grafica</p></html>"
        with pytest.raises(base.Broken):
            borsaitaliana.find(BTP)
        with pytest.raises(base.Broken):
            borsaitaliana.quote(BTP)


def test_morningstar(app, sites):
    answers, _ = sites
    with app.test_request_context():
        found = morningstar.find(FUND)
        assert [(c.name, c.asset_class, c.price_source) for c in found][0] == (
            "Fondo Esempio Azionario Europa A Acc", "Fondo", "morningstar")
        quote = morningstar.quote(FUND)
        assert (quote.price, quote.on, quote.currency) == (Decimal("12.345"), date(2026, 10, 9), "EUR")
        answers["snapshot.aspx?id=F00000XYZ1"] = "<html>NAV non disponibile</html>"
        with pytest.raises(base.Broken):
            morningstar.quote(FUND)
        answers[f"SecuritySearch.ashx?q={FUND}"] = ""
        with pytest.raises(base.NotFound):
            morningstar.find(FUND)
        answers[f"SecuritySearch.ashx?q={FUND}"] = "Fondo|{not json|x"
        with pytest.raises(base.Broken):
            morningstar.find(FUND)


# ── Search on every site switched on ───────────────────────────────────────────

def test_search_by_isin_on_every_site_with_a_month_of_memory(app, db, sites):
    answers, calls = sites
    _json_answers(answers)
    answers[f"SecuritySearch.ashx?q={ETF}"] = ""
    answers[f"search?q={ETF}"] = {"quotes": [{"symbol": "VWCE.MI", "longname": "Vanguard", "quoteType": "ETF",
                                              "exchange": "MIL", "exchDisp": "Milan"}]}
    with app.test_request_context():
        found, errors = price_feed.search(ETF, date(2026, 10, 10))
        assert [(c.symbol, c.source) for c in found] == [
            ("VWCE.MI", "yahoo"), ("VWCE.DE", "openfigi"), ("VWCE", "justetf"), ("", "borsaitaliana")]
        assert errors == []  # Morningstar does not know it: no result, not an error
        assert any("morningstar" in url for url in calls)
        asked = len(calls)
        assert price_feed.search(ETF.lower(), date(2026, 10, 20))[0][0].symbol == "VWCE.MI" and len(calls) == asked
        price_feed.search(ETF, date(2026, 11, 20))  # more than a month: asked again
        assert len(calls) > asked

        answers["api.openfigi.com"] = "<html>"
        settings_store.set_json(price_feed.LOOKUP_CACHE, {})
        found, errors = price_feed.search(ETF, date(2026, 10, 10))
        assert errors == ["OpenFIGI: risposta non leggibile"] and found  # the others still answer
        assert price_feed.search("  ") == ([], [])


def test_the_memory_keeps_the_newest_searches(app, db, sites, monkeypatch):
    answers, _ = sites
    _json_answers(answers)
    monkeypatch.setattr(price_feed, "CACHE_SIZE", 2)
    with app.test_request_context():
        for i, isin in enumerate((ETF, BTP, "IE00B4L5Y983")):
            answers[f"search?q={isin}"] = {"quotes": [{"symbol": f"X{i}.MI", "quoteType": "ETF", "exchange": "MIL"}]}
            price_feed.search(isin, date(2026, 10, 1) + timedelta(days=i))
        assert set(settings_store.get_json(price_feed.LOOKUP_CACHE, {})) == {BTP, "IE00B4L5Y983"}


def test_choosing_and_ordering_the_sites(client, app, db, sites):
    answers, calls = sites
    _json_answers(answers)
    page_html = client.get("/settings/price-sources").get_data(as_text=True)
    assert "OpenFIGI" in page_html and "I prezzi da internet sono spenti" in page_html
    assert "/settings/price-sources" in client.get("/settings/").get_data(as_text=True)
    with app.test_request_context():
        assert sources.chosen() == ["yahoo", "openfigi", "justetf", "borsaitaliana", "morningstar"]  # all on at first
    client.post("/settings/price-sources", data={"on-morningstar": "1", "order-morningstar": "1", "on-borsaitaliana": "1",
                                                 "order-borsaitaliana": "2", "order-yahoo": "9", "order-openfigi": "x"})
    with app.test_request_context():
        assert sources.chosen() == ["morningstar", "borsaitaliana"]
        found, _errors = price_feed.search(FUND)
    assert [c.source for c in found] == ["morningstar", "morningstar"]
    assert not any("yahoo" in url or "openfigi" in url for url in calls)
    rows = {r["key"]: r for r in sources.settings_rows()}
    assert rows["morningstar"]["position"] == 1 and not rows["yahoo"]["on"]


# ── Prices from the sites ──────────────────────────────────────────────────────

def test_bonds_funds_and_etfs_priced_by_their_sites(app, db, sites):
    answers, _ = sites
    _json_answers(answers)
    btp = Holding(name="BTP 2031", isin=BTP, asset_class="Obbligazione", quantity=10000, avg_price=Decimal("0.9"))
    fund = Holding(name="Fondo", isin=FUND, asset_class="Fondo", quantity=100, avg_price=10)
    etf = Holding(name="All-World", ticker="VWCE.DE", isin=ETF, asset_class="ETF", quantity=5, avg_price=100)
    db.session.add_all([btp, fund, etf])
    db.session.commit()
    with app.test_request_context():
        results = {r.holding.name: r for r in price_feed.update_all([btp, fund, etf])}
    assert (results["BTP 2031"].source, results["BTP 2031"].price) == ("borsaitaliana", Decimal("0.854700"))
    assert btp.value == 8547.0  # 10.000 € of face value at 85,47
    assert (results["Fondo"].source, results["Fondo"].price) == ("morningstar", Decimal("12.345000"))
    assert (results["All-World"].source, results["All-World"].price) == ("justetf", Decimal("131.420000"))  # Yahoo down


def test_morningstar_is_a_reserve_for_etfs(app, db, sites):
    answers, _ = sites
    answers[f"SecuritySearch.ashx?q={ETF}"] = page("morningstar_search.txt")
    answers.pop(f"api/etfs/{ETF}/quote")  # justETF does not answer either
    etf = Holding(name="All-World", ticker="VWCE.DE", isin=ETF, asset_class="ETF", quantity=1, avg_price=100)
    db.session.add(etf)
    db.session.commit()
    with app.test_request_context():
        (result,) = price_feed.update_all([etf])
    assert (result.source, result.price) == ("morningstar", Decimal("12.345000"))


def test_a_chosen_site_and_what_goes_wrong(app, db, sites):
    answers, _ = sites
    no_isin = Holding(name="Senza ISIN", ticker="VWCE.DE", asset_class="ETF", quantity=1, avg_price=1, price_source="justetf")
    bond = Holding(name="Obbligazione", isin=BTP, asset_class="Obbligazione", quantity=1, avg_price=1)
    db.session.add_all([no_isin, bond])
    db.session.commit()
    sources.save(sources.DEFAULT_ORDER, set())  # every site off
    with app.test_request_context():
        results = {r.holding.name: r for r in price_feed.update_all([no_isin, bond])}
    assert "serve l'ISIN" in results["Senza ISIN"].error
    assert "nessuna fonte attiva" in results["Obbligazione"].error


def test_the_search_route_says_where_each_result_comes_from(client, db, sites):
    answers, _ = sites
    _json_answers(answers)
    answers["api.openfigi.com"] = json.dumps([{"warning": "No identifier found."}])
    client.post("/settings/save", data={"prices_online": "on", "module_portfolio": "on"})
    data = client.get(f"/portfolio/lookup?q={BTP}").get_json()
    assert data["results"][0]["source_name"] == "Borsa Italiana" and data["results"][0]["price_source"] == "borsaitaliana"
    assert any(e.startswith("Yahoo Finance:") for e in data["errors"])
    form = client.get("/portfolio/new").get_data(as_text=True)
    assert "Borsa Italiana" in form and 'value="morningstar"' in form


# ── The shared helpers ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, value", [("1.234,56", "1234.56"), ("1,234.56", "1234.56"), ("99,85 %", "99.85"),
                                         ("123.4", "123.4"), ("", None), ("n.d.", None)])
def test_number(text, value):
    assert base.number(text) == (Decimal(value) if value else None)


@pytest.mark.parametrize("text, value", [("09/10/2026", date(2026, 10, 9)), ("09/10/26 - 17.35.00", date(2026, 10, 9)),
                                         ("2026-10-09", date(2026, 10, 9)), ("31/02/2026", None), ("ieri", None), (None, None)])
def test_day(text, value):
    assert base.day(text) == value


def test_one_request_a_second_per_site(monkeypatch):
    clock, slept = [100.0], []
    monkeypatch.setattr(base.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(base.time, "sleep", lambda seconds: slept.append(round(seconds, 2)))
    monkeypatch.setattr(base, "_last", {})
    base._wait("justetf")
    clock[0] += 0.25
    base._wait("justetf")
    base._wait("openfigi")  # another site: no wait
    assert slept == [0.75]


def test_fetch_posts_json(monkeypatch):
    import io

    seen = {}

    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake(request, timeout):
        seen.update(method=request.get_method(), body=request.data, kind=request.get_header("Content-type"))
        return Answer(b'[{"data": []}]')

    monkeypatch.setattr(base.urllib.request, "urlopen", fake)
    monkeypatch.setattr(base, "MIN_INTERVAL", 0)
    assert base.post_json("openfigi", "https://api.openfigi.com/v3/mapping", [{"idValue": ETF}]) == [{"data": []}]
    assert seen == {"method": "POST", "body": b'[{"idValue": "IE00BK5BQT80"}]', "kind": "application/json"}
    assert base.get_json("x", "https://example.org") == [{"data": []}]
