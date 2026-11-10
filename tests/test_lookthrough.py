"""F57: look-through of the funds from the issuer's holdings file, the portfolio's exposure, overlaps, pages."""
import io
from datetime import date

import openpyxl
import pytest

from app.models.wealth import Holding, HoldingExposure
from app.services import backup, lookthrough

ISHARES_CSV = """iShares Core MSCI World UCITS ETF
Fund Holdings as of,"Nov 07, 2026"
Inception Date,"Sep 25, 2009"

Ticker,Name,Sector,Asset Class,Market Value,Weight (%),Notional Value,Shares,Price,Location,Exchange,Market Currency
AAPL,APPLE INC,Information Technology,Equity,"4,000,000.00",40.00,"4,000,000.00","20,000.00",200.00,United States,NASDAQ,USD
MSFT,MICROSOFT CORP,Information Technology,Equity,"3,000,000.00",30.00,"3,000,000.00","7,500.00",400.00,United States,NASDAQ,USD
ASML,ASML HOLDING NV,Information Technology,Equity,"1,000,000.00",10.00,"1,000,000.00","1,500.00",666.67,Netherlands,Euronext Amsterdam,EUR
NESN,NESTLE SA,Consumer Staples,Equity,"1,500,000.00",15.00,"1,500,000.00","15,000.00",100.00,Switzerland,SIX Swiss Exchange,CHF
EUR,EUR CASH,Cash and/or Derivatives,Cash,"500,000.00",5.00,"500,000.00","500,000.00",1.00,-,-,EUR

"The content contained herein is owned or licensed by BlackRock and/or its third-party information providers."
"""


def xtrackers_xlsx() -> bytes:
    """An Xtrackers-like workbook: a title, the date, then the weights as fractions."""
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["Xtrackers S&P 500 UCITS ETF"])
    sheet.append(["Dati al 31.10.2026"])
    sheet.append([])
    sheet.append(["Name", "ISIN", "Country", "Currency", "Industry Classification", "Weighting"])
    sheet.append(["APPLE INC.", "US0378331005", "Stati Uniti", "USD", "Information Technology", 0.5])
    sheet.append(["ALPHABET INC CLASS A", "US02079K3059", "United States", "USD", "Communication Services", 0.3])
    sheet.append(["TOYOTA MOTOR CORP", "JP3633400001", "Japan", "JPY", "Consumer Discretionary", 0.2])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


@pytest.fixture()
def holdings(db):
    world = Holding(name="iShares World", asset_class="ETF", quantity=10, avg_price=100)
    sp500 = Holding(name="Xtrackers S&P 500", asset_class="ETF", quantity=5, avg_price=100)
    apple = Holding(name="Apple", asset_class="Azione", quantity=1, avg_price=250, region="Nord America",
                    sector="Tecnologia", currency="USD")
    fund = Holding(name="Fondo Alfa", asset_class="Fondo comune", quantity=1, avg_price=250)
    db.session.add_all([world, sp500, apple, fund])
    db.session.commit()
    return world, sp500, apple, fund


def test_read_ishares_csv(app):
    with app.test_request_context():
        parsed = lookthrough.read_file("IWDA_holdings.csv", ISHARES_CSV.encode())
    assert parsed.as_of == date(2026, 11, 7) and parsed.source == "iShares CSV" and parsed.rows == 5
    e = parsed.exposures
    assert e["country"] == {"US": 70, "NL": 10, "CH": 15}  # the cash's «-» has no country
    assert e["sector"] == {"Tecnologia": 80, "Beni di consumo di base": 15, "Liquidità": 5}
    assert e["currency"] == {"USD": 70, "EUR": 15, "CHF": 15}
    assert e["holding"] == {"APPLE INC": 40, "MICROSOFT CORP": 30, "NESTLE SA": 15, "ASML HOLDING NV": 10}
    assert e["asset_class"] == {"Azionario": 95, "Monetario e liquidità": 5}


def test_read_xlsx_with_fractions_and_italian_names(app):
    with app.test_request_context():
        parsed = lookthrough.read_file("export.xlsx", xtrackers_xlsx())
    assert parsed.as_of == date(2026, 10, 31) and parsed.source == "Xtrackers XLSX"
    assert parsed.exposures["country"] == {"US": 80, "JP": 20}
    assert parsed.exposures["sector"] == {"Tecnologia": 50, "Servizi di comunicazione": 30,
                                          "Beni di consumo discrezionali": 20}


def test_read_italian_csv_and_spreadsheet_xml(app):
    italian = ("iShares Core MSCI World\nPartecipazioni del fondo al;07/11/2026\n\n"
               "Ticker dell'emittente;Nome;Settore;Asset Class;Valore di mercato;Ponderazione (%);Località;Valuta di mercato\n"
               "AAPL;APPLE INC;IT;Azioni;1.000,00;62,5;Stati Uniti;USD\n"
               "SAP;SAP;IT;Azioni;600,00;37,5;Germania;EUR\n")
    xml = ('<?xml version="1.0"?><ss:Workbook xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">'
           '<ss:Worksheet ss:Name="Holdings"><ss:Table>'
           '<ss:Row><ss:Cell><ss:Data ss:Type="String">Fund Holdings as of</ss:Data></ss:Cell>'
           '<ss:Cell><ss:Data ss:Type="String">Nov 07, 2026</ss:Data></ss:Cell></ss:Row>'
           '<ss:Row><ss:Cell><ss:Data ss:Type="String">Name</ss:Data></ss:Cell>'
           '<ss:Cell><ss:Data ss:Type="String">Weight (%)</ss:Data></ss:Cell>'
           '<ss:Cell><ss:Data ss:Type="String">Location</ss:Data></ss:Cell></ss:Row>'
           '<ss:Row><ss:Cell><ss:Data ss:Type="String">AT&amp;T INC</ss:Data></ss:Cell>'
           '<ss:Cell><ss:Data ss:Type="Number">100</ss:Data></ss:Cell>'
           '<ss:Cell><ss:Data ss:Type="String">Korea (South)</ss:Data></ss:Cell></ss:Row>'
           '</ss:Table></ss:Worksheet></ss:Workbook>')
    with app.test_request_context():
        parsed = lookthrough.read_file("holdings.csv", italian.encode("utf-8"))
        assert parsed.as_of == date(2026, 11, 7)
        assert parsed.exposures["country"] == {"US": 62.5, "DE": 37.5}
        assert parsed.exposures["asset_class"] == {"Azionario": 100}
        parsed = lookthrough.read_file("IWDA.xls", xml.encode())
        assert parsed.exposures == {"country": {"KR": 100}, "holding": {"AT&T INC": 100}}
        with pytest.raises(lookthrough.LookThroughError, match="Non trovo la tabella"):
            lookthrough.read_file("a.csv", b"a;b;c\n1;2;3\n4;5;6\n")
        with pytest.raises(lookthrough.LookThroughError, match="vuoto"):
            lookthrough.read_file("a.csv", b"")


def test_helpers():
    assert [lookthrough.number(v) for v in ("4,63", "1,234.5", "1.234,5", "1,234,567", "4.63%", "(0.5)", "-", None)] \
        == [4.63, 1234.5, 1234.5, 1234567, 4.63, -0.5, None, None]
    assert lookthrough.country_code("Stati Uniti") == lookthrough.country_code("USA") == "US"
    assert lookthrough.country_code("Paesi Bassi") == lookthrough.country_code("the Netherlands") == "NL"
    assert lookthrough.country_code("Atlantide") is None
    assert lookthrough.company_key("Alphabet Inc. Class C") == lookthrough.company_key("ALPHABET INC CLASS A")
    assert lookthrough._date_in("7 novembre 2026") == date(2026, 11, 7)
    assert lookthrough._date_in("2026-02-30") is None


def test_portfolio_exposure(app, db, holdings):
    world, sp500, apple, fund = holdings
    with app.test_request_context():
        lookthrough.import_file(world, "IWDA_holdings.csv", ISHARES_CSV.encode())
        lookthrough.import_file(sp500, "export.xlsx", xtrackers_xlsx())
        db.session.commit()
        result = lookthrough.portfolio(Holding.query.all())
    # 1000 € iShares, 500 € Xtrackers, 250 € Apple shares (manual region), 250 € fund without anything
    assert result["total"] == 2000 and result["covered_pct"] == 75.0
    rows = lambda kind: {r["name"]: r["value"] for r in result[kind]}  # noqa: E731
    assert rows("country") == {"Stati Uniti": 1100, "Svizzera": 150, "Paesi Bassi": 100, "Giappone": 100,
                               "Nord America": 250, "Non coperto": 300}  # 50 € of cash + the fund
    assert result["country"][0] == {"name": "Stati Uniti", "value": 1100, "pct": 55.0, "uncovered": False}
    assert result["country"][-1]["uncovered"]
    assert rows("sector") == {"Tecnologia": 1300, "Beni di consumo di base": 150, "Servizi di comunicazione": 150,
                              "Beni di consumo discrezionali": 100, "Liquidità": 50, "Non coperto": 250}
    assert rows("currency") == {"USD": 1350, "EUR": 150, "CHF": 150, "JPY": 100, "Non coperto": 250}
    top = result["companies"][0]
    assert (lookthrough.company_key(top["name"]), top["value"], top["pct"]) == ("apple", 900, 45.0)
    assert sorted(top["via"]) == [("Apple", 100.0), ("Xtrackers S&P 500", 50.0), ("iShares World", 40.0)]
    assert [c["value"] for c in result["companies"][1:]] == [300, 150, 150, 100, 100]
    [pair] = result["overlaps"]
    assert (pair["overlap"], pair["common"]) == (40, 1)  # Apple: min(40, 50)
    assert {pair["a"].id, pair["b"].id} == {world.id, sp500.id}


def test_top_ten_and_others(app, db, holdings):
    world = holdings[0]
    with app.test_request_context():
        lookthrough.save(world, {"country": {code: 8.0 for code in "US GB FR DE IT ES JP CA AU CH NL SE".split()}},
                         date(2026, 11, 1), "a mano")
        result = lookthrough.portfolio([world])
    names = [r["name"] for r in result["country"]]
    assert len(names) == 12 and names[10] == "Altri" and names[11] == "Non coperto"
    assert result["country"][10]["value"] == 160 and result["country"][11]["value"] == 40  # 2 × 8 %; 4 % left


def test_manual_entry_and_clear(app, db, holdings):
    world = holdings[0]
    with app.test_request_context():
        lookthrough.manual(world, {"country": [("Stati Uniti", "62,5"), ("Giappone", "6"), ("", "")],
                                   "sector": [("Information Technology", "25")]})
        db.session.commit()
        summary = lookthrough.summary(world)
        assert summary["country"] == [("Stati Uniti", 62.5), ("Giappone", 6.0)]
        assert summary["sector"] == [("Tecnologia", 25.0)] and summary["sources"] == ["a mano"]
        for rows, message in (({"country": [("Atlantide", "5")]}, "Paese non riconosciuto"),
                              ({"country": [("Italia", "")]}, "un peso tra 0 e 100"),
                              ({"sector": [("Energia", "70"), ("Finanza", "40")]}, "superano il 100"),
                              ({"country": [("", "")]}, "almeno un paese")):
            with pytest.raises(lookthrough.LookThroughError, match=message):
                lookthrough.manual(world, rows)
        assert lookthrough.clear(world) == 3


def test_backup_lists_the_table():
    assert HoldingExposure in backup.MODELS
    assert backup.MODELS.index(HoldingExposure) == backup.MODELS.index(Holding) + 1


def test_pages(client, db, holdings):
    world, sp500, apple, fund = holdings
    page = client.get(f"/portfolio/{world.id}").get_data(as_text=True)
    assert "Composizione (spacchettamento)" in page and "Carica il file dell'emittente" in page
    page = client.post(f"/portfolio/{world.id}/lookthrough/upload", follow_redirects=True,
                       data={"file": (io.BytesIO(ISHARES_CSV.encode()), "IWDA_holdings.csv")},
                       content_type="multipart/form-data").get_data(as_text=True)
    assert "Composizione letta da iShares CSV: 5 righe, dati al 07/11/2026." in page
    assert "Dati al 07/11/2026" in page and "APPLE INC" in page
    page = client.post(f"/portfolio/{sp500.id}/lookthrough/upload", follow_redirects=True, data={
        "file": (io.BytesIO(xtrackers_xlsx()), "export.xlsx"), "as_of": "2026-11-05"},
        content_type="multipart/form-data").get_data(as_text=True)
    assert "dati al 05/11/2026" in page
    page = client.post(f"/portfolio/{sp500.id}/lookthrough/upload", follow_redirects=True, data={
        "file": (io.BytesIO(b"x;y;z\n1;2;3\n4;5;6\n"), "a.csv")},
        content_type="multipart/form-data").get_data(as_text=True)
    assert "Non trovo la tabella" in page
    page = client.post(f"/portfolio/{sp500.id}/lookthrough/upload", follow_redirects=True).get_data(as_text=True)
    assert "Scegli il file" in page

    page = client.get("/portfolio/composition").get_data(as_text=True)
    for text in ("Per paese", "Per settore", "Per valuta", "Stati Uniti", "Non coperto", "Prime 20 società",
                 "Sovrapposizione tra fondi", "makeBarChart", "makeDoughnutChart"):
        assert text in page
    assert "Il 75 % del valore" in page

    page = client.post(f"/portfolio/{fund.id}/lookthrough/manual", follow_redirects=True, data={
        "country_name": ["Italia", ""], "country_weight": ["40", ""], "sector_name": ["Finanza"],
        "sector_weight": ["30"]}).get_data(as_text=True)
    assert "Composizione salvata." in page
    page = client.post(f"/portfolio/{fund.id}/lookthrough/manual", follow_redirects=True, data={
        "country_name": ["Atlantide"], "country_weight": ["40"]}).get_data(as_text=True)
    assert "Paese non riconosciuto" in page
    page = client.post(f"/portfolio/{fund.id}/lookthrough/clear", follow_redirects=True).get_data(as_text=True)
    assert "Composizione cancellata" in page
    assert HoldingExposure.query.filter_by(holding_id=fund.id).count() == 0
    assert "Composizione (spacchettamento)" not in client.get(f"/portfolio/{apple.id}").get_data(as_text=True)


def test_fallbacks_and_market_values(app, db):
    btp = Holding(name="BTP 2030", asset_class="Obbligazione", quantity=1, avg_price=300, isin="IT0005000001")
    enel = Holding(name="Enel", asset_class="Azione", quantity=1, avg_price=100, region="Italia", sector="Utilities")
    db.session.add_all([btp, enel])
    db.session.commit()
    values = "Holding name,Region,Market value\nNESTLE,Switzerland,300\nSAP,Germany,100\nTOTAL,,\n"
    with app.test_request_context():
        parsed = lookthrough.read_file("vanguard.csv", values.encode())
        assert parsed.source == "Vanguard CSV"
        assert parsed.exposures["country"] == {"CH": 75, "DE": 25}  # weights from the market values
        result = lookthrough.portfolio([btp, enel])
    assert {r["name"]: r["value"] for r in result["country"]} == {"Italia": 400}  # the ISIN and the region
    assert {r["name"]: r["value"] for r in result["sector"]} == {"Obbligazionario": 300, "Utilities": 100}
    assert {r["name"]: r["value"] for r in result["currency"]} == {"EUR": 400}
    assert result["covered_pct"] == 0 and result["overlaps"] == []


def test_a_country_given_as_its_iso_code():
    from app.services.lookthrough import country_code
    assert country_code("us") == "US" and country_code("IT") == "IT"
    assert country_code("Stati Uniti") == "US" and country_code("ZZ") is None
