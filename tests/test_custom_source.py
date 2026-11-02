"""F22: price sources of the user's own — an address and where to read the price (JSON, HTML, CSV)."""
import io
import json
from datetime import date
from decimal import Decimal

import pytest

from app.models.wealth import Holding
from app.services import price_feed, settings_store
from app.services.instrument_sources import base, custom
from app.services.instrument_sources.custom import CustomSource

ISIN = "IT0000000001"


@pytest.fixture()
def pages(monkeypatch):
    """The answers by address; the addresses asked for."""
    answers, asked = {}, []
    monkeypatch.setattr(base, "_wait", lambda site: None)

    def fake(source, url):
        asked.append(url)
        if url not in answers:
            raise OSError("no route")
        return answers[url]

    monkeypatch.setattr(custom, "download", fake)
    return answers, asked


def _source(**values):
    return custom.validate(CustomSource(**({"name": "Fondo", "url": "https://fondo.example/q?isin={ISIN}&d={DATA}",
                                            "format": "json", "path": "data.0.nav"} | values)))


def test_formats(pages):
    answers, asked = pages
    json_source = _source(date_path="data.0.date")
    answers[custom.address(json_source, ISIN, None)] = json.dumps({"data": [{"nav": "12,345", "date": "2026-10-10"}]})
    quote = custom.quote(json_source, ISIN, None)
    assert quote.price == Decimal("12.345") and quote.on == date(2026, 10, 10) and quote.currency == "EUR"
    assert asked == [f"https://fondo.example/q?isin={ISIN}&d={date.today().isoformat()}"]
    html_source = _source(format="html", path="Valore quota", url="https://fondo.example/{ISIN}.html", currency="usd")
    page = "<table><tr><td>Valore quota</td><td>1.234,56 €</td></tr></table>"
    assert custom.read(html_source, page, date(2026, 1, 2)).price == Decimal("1234.56")
    assert html_source.currency == "USD"
    regex = _source(format="html", path=r"re:NAV:\s*([\d.,]+)", url="https://f.example/{TICKER}", divide_100=True)
    assert custom.read(regex, "<p>NAV: 98,50</p>").price == Decimal("0.985")
    csv_source = _source(format="csv", path="Chiusura", url="https://f.example/{ISIN}.csv")
    assert custom.read(csv_source, "Data;Chiusura\n2026-10-09;10,1\n2026-10-10;10,3\n").price == Decimal("10.3")
    assert custom.read(_source(format="csv", path="2", url="https://f.example/{ISIN}.csv"), "d,p\nx,7.5\n").price == Decimal("7.5")


def test_broken_answers(pages):
    with pytest.raises(base.Broken, match="non trovato"):
        custom.read(_source(), json.dumps({"data": []}))
    with pytest.raises(base.Broken, match="non leggibile"):
        custom.read(_source(), "<html>")
    with pytest.raises(base.Broken, match="non è un prezzo"):
        custom.read(_source(path="data.0.x"), json.dumps({"data": [{"x": "n/d"}]}))
    with pytest.raises(base.Broken, match="non trova"):
        custom.read(_source(format="html", path=r"re:NAV (\d+)"), "<p>niente</p>")
    with pytest.raises(base.Broken, match="non trovato"):
        custom.read(_source(format="html", path="Quota"), "<p>niente</p>")
    with pytest.raises(base.Broken, match="righe"):
        custom.read(_source(format="csv", path="1"), "solo intestazione\n")
    with pytest.raises(base.Broken, match="colonna"):
        custom.read(_source(format="csv", path="Prezzo"), "a;b\n1;2\n")
    with pytest.raises(ValueError, match="ISIN"):
        custom.address(_source(), None, "VWCE")
    with pytest.raises(ValueError, match="ticker"):
        custom.address(_source(url="https://f.example/{TICKER}"), ISIN, None)


def test_validation_and_storage(app, db):
    for bad, message in ((dict(name="a/b"), "Nome"), (dict(url="ftp://x/{ISIN}"), "https"),
                         (dict(url="https://x.example/"), "{ISIN}"), (dict(format="xml"), "Formato"),
                         (dict(path=" "), "dove leggere"), (dict(format="html", path="re:("), "regolare"),
                         (dict(currency="euro"), "Valuta")):
        with pytest.raises(ValueError, match=message):
            _source(**bad)
    custom.save(_source())
    custom.save(_source(name="Altro", format="csv", path="2"))
    custom.save(_source(name="Fondo nuovo"), replacing="Fondo")
    assert [s.name for s in custom.all_sources()] == ["Altro", "Fondo nuovo"]
    assert custom.labels() == {"custom:Altro": "Altro", "custom:Fondo nuovo": "Fondo nuovo"}
    assert custom.get("Altro").format == "csv" and custom.get("Nessuna") is None
    custom.delete("Altro")
    assert [s.name for s in custom.all_sources()] == ["Fondo nuovo"]
    settings_store.set_json(custom.SETTING, [{"name": "x"}, "rotto", {"name": "y", "url": "https://y/{ISIN}", "extra": 1}])
    assert [s.name for s in custom.all_sources()] == ["y"]


def test_only_the_internet_and_small_answers(monkeypatch):
    monkeypatch.setattr(base, "_wait", lambda site: None)
    monkeypatch.setattr(custom.socket, "getaddrinfo", lambda host, port: [(0, 0, 0, "", ("192.168.1.10", 0))])
    with pytest.raises(ValueError, match="rete locale"):
        custom.check_public("http://router.local/x")

    def no_name(host, port):
        raise OSError("nope")

    monkeypatch.setattr(custom.socket, "getaddrinfo", no_name)
    with pytest.raises(base.NotFound):
        custom.check_public("https://nessuno.example/x")
    monkeypatch.setattr(custom.socket, "getaddrinfo", lambda host, port: [(0, 0, 0, "", ("93.184.216.34", 0))])

    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(custom.urllib.request, "urlopen", lambda request, timeout: Answer(b'{"p": 5}'))
    assert custom.download(_source(), "https://ok.example/x") == '{"p": 5}'
    monkeypatch.setattr(custom.urllib.request, "urlopen", lambda request, timeout: Answer(b"x" * (custom.MAX_BYTES + 1)))
    with pytest.raises(base.Broken, match="troppo grande"):
        custom.download(_source(), "https://ok.example/x")


def test_daily_price_from_it(app, db, pages, monkeypatch):
    answers, _ = pages
    custom.save(_source(url="https://fondo.example/q?isin={ISIN}"))
    answers[f"https://fondo.example/q?isin={ISIN}"] = json.dumps({"data": [{"nav": "20.5"}]})
    fund = Holding(name="Fondo X", asset_class="Fondo", isin=ISIN, quantity=10, avg_price=18, price_source="custom:Fondo")
    gone = Holding(name="Fondo Y", asset_class="Fondo", isin=ISIN, quantity=1, avg_price=1, price_source="custom:Sparita")
    db.session.add_all([fund, gone])
    db.session.commit()
    results = {r.holding.name: r for r in price_feed.update_all([fund, gone])}
    assert results["Fondo X"].price == Decimal("20.5") and results["Fondo X"].source == "custom:Fondo"
    assert "non c'è più" in results["Fondo Y"].error
    assert fund.current_price == Decimal("20.5")


def test_settings_page(app, client, db, pages, monkeypatch):
    answers, _ = pages
    page = client.get("/settings/price-sources").get_data(as_text=True)
    assert "Fonti tue" in page and "Aggiungi una fonte" in page
    form = {"name": "Fondo", "url": "https://fondo.example/q?isin={ISIN}", "format": "json", "path": "nav",
            "currency": "EUR"}
    answers[f"https://fondo.example/q?isin={ISIN}"] = json.dumps({"nav": 7})
    tested = client.post("/settings/price-sources/custom", data=form | {"test": "1", "test_isin": ISIN},
                         follow_redirects=True).get_data(as_text=True)
    assert "Prova riuscita: 7" in tested and custom.all_sources() == []  # a test saves nothing
    assert "serve l" in client.post("/settings/price-sources/custom", data=form | {"test": "1"},
                                    follow_redirects=True).get_data(as_text=True)
    client.post("/settings/price-sources/custom", data=form)
    assert custom.get("Fondo") is not None
    fund = Holding(name="F", asset_class="Fondo", quantity=1, avg_price=1, price_source="custom:Fondo")
    db.session.add(fund)
    db.session.commit()
    assert 'value="custom:Fondo" selected' in client.get(f"/portfolio/{fund.id}/edit").get_data(as_text=True)
    assert "Formato" in client.post("/settings/price-sources/custom", data=form | {"format": "xml"},
                                    follow_redirects=True).get_data(as_text=True)
    client.post("/settings/price-sources/custom/delete", data={"name": "Fondo"})
    db.session.refresh(fund)
    assert custom.all_sources() == [] and fund.price_source == "auto"
