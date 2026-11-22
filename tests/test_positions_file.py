"""A broker's statement of the positions (Fineco «Portafoglio di sintesi»): no trades, the securities held on a day.
The import compares it with the recorded positions; the differences become purchases and sales to review."""
import io
from datetime import date
from decimal import Decimal

from openpyxl import Workbook

from app.models.wealth import Holding
from app.services import broker_import, portfolio_reading

HEADERS = ["Titolo", "ISIN", "Simbolo", "Mercato", "Strumento", "Valuta", "Quantità", "P.zo medio di carico",
           "Cambio di carico", "Valore di carico", "P.zo di mercato", "Cambio di mercato", "Valore di mercato €",
           "Var%", "Var €", "Var in valuta", "Rateo"]


def fineco_file() -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(["Portafoglio di sintesi"])
    sheet.append([])
    sheet.append(HEADERS)
    sheet.append(["Invesco Physical Gold ETC", "IE00B579F325", "SGLD.MI", "AFF", "ETC", "EUR", 8, 160.16, 1, 1281.28,
                  338.38, 1, 2707.04, 111.27, 1425.76, 1425.76, 0])
    sheet.append(["Vanguard FTSE All-World UCITS ETF (USD) Acc", "IE00BK5BQT80", "VWCE.MI", "AFF", "ETF", "EUR", 66,
                  116.4009, 1, 7682.4594, 169.84, 1, 11209.44, 45.9, 3526.98, 3526.98, 0])
    sheet.append(["Apple Inc", "US0378331005", "AAPL", "NASDAQ", "AZ", "USD", 10, 110, 1.1, 1100, 220, 1.1, 2000,
                  0, 0, 0, 0])
    sheet.append([])
    sheet.append(["Totale", None, None, None, None, None, None, None, None, None, None, "Valore di carico"])
    sheet.append(["EUR", None, None, None, None, None, None, None, None, None, None, 15885.76])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def test_a_positions_file_is_recognised_and_read(app, db):
    with app.app_context():
        held = broker_import.positions("15112026_Fineco_Portafoglio.xlsx", fineco_file())
    assert [h["isin"] for h in held] == ["IE00B579F325", "IE00BK5BQT80", "US0378331005"]
    gold, _world, apple = held
    assert (gold["quantity"], gold["price"], gold["market"]) == (8, Decimal("160.16"), Decimal("338.38"))
    assert apple["price"] == Decimal(110) / Decimal("1.1") and apple["value_eur"] == 0  # cost in dollars → euro
    assert apple["market"] == Decimal(200)  # «Valore di mercato €» / quantity
    assert broker_import.file_date("15112026_Fineco_Portafoglio.xls") == date(2026, 11, 15)
    assert broker_import.file_date("posizioni-2026-11-15.csv") == date(2026, 11, 15)
    assert broker_import.file_date("portafoglio.xls") is None


def test_a_trades_file_is_not_taken_for_positions(app, db):
    with app.app_context():
        assert broker_import.positions("t.csv", broker_import.template("csv")) is None


def test_the_positions_become_operations_to_review_and_confirm(client, db):
    db.session.add(Holding(name="Vanguard FTSE All-World", isin="IE00BK5BQT80", asset_class="ETF", quantity=60,
                           avg_price=100, opening_quantity=60, opening_price=100))
    db.session.commit()
    page = client.post("/portfolio/import", data={"file": (io.BytesIO(fineco_file()), "15112026_Fineco_Portafoglio.xlsx")},
                       content_type="multipart/form-data").get_data(as_text=True)
    assert "Posizioni al 15/11/2026 lette dal file" in page
    # a position, not a trade: average cost (PMC) and units, no buy/sell and no commission
    assert "PMC €" in page and "# quote" in page and "Commissione €" not in page and "Acquisto</td>" not in page
    reading = portfolio_reading.compare(broker_import.positions("f.xlsx", fineco_file()), date(2026, 11, 15))
    units = {row.isin: row.units for row in reading.preview.rows}
    assert units == {"IE00B579F325": 8, "IE00BK5BQT80": 6, "US0378331005": 10}  # 66 held, 60 recorded: 6 bought
    import re
    payload = re.search(r'name="payload" value="([^"]+)"', page).group(1)
    client.post("/portfolio/import/confirm", data={"payload": payload, "include": ["0", "1", "2"]})
    gold = Holding.query.filter_by(isin="IE00B579F325").one()
    assert float(gold.units) == 8 and gold.current_price == Decimal("338.38")
