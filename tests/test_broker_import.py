"""
F19c: a broker's statement (Degiro or any CSV/Excel with the right columns) becomes the holdings' operations after a
review, without duplicates on a second import; the current account's movements of a holding are linked to it.
"""
import io
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import broker_import, transfer
from app.services.bank_import.model import StatementRow
from app.services.bank_import.rows import _investment
from tests.form_helper import form_data

SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "dati_fittizi" / "broker"
DEGIRO = (SAMPLES / "degiro_transazioni.csv").read_bytes()
GENERIC = (SAMPLES / "generico_operazioni.csv").read_bytes()


@pytest.fixture()
def degiro(db):
    account = Account(name="Degiro", kind="other")
    vwrl = Holding(name="Vanguard All-World", isin="IE00B3RBWM25", ticker="VWRL.AS", asset_class="ETF", quantity=0,
                   avg_price=0, opening_quantity=0, opening_price=0)
    db.session.add_all([account, vwrl])
    db.session.commit()
    return account, vwrl


def _preview(client, name: str, raw: bytes):
    return client.post("/portfolio/import", data={"file": (io.BytesIO(raw), name)},
                       content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)


def _import(client, name: str, raw: bytes, **overrides) -> str:
    html = _preview(client, name, raw)
    rows = re.findall(r'name="include" value="(\d+)"', html)
    data = form_data(html, "broker-form", include=rows, **overrides)
    return client.post("/portfolio/import/confirm", data=data, follow_redirects=True).get_data(as_text=True)


def test_degiro_layout_and_rows(app, degiro):
    with app.test_request_context():
        preview = broker_import.read("degiro_transazioni.csv", DEGIRO)
    assert preview.layout == "degiro" and preview.unread == []
    apple = [r for r in preview.rows if r.isin == "US0378331005"]
    assert [(r.units, r.price, r.fee) for r in apple] == [
        (Decimal(8), Decimal("161.3125"), Decimal("2.50")),   # bought in dollars: the euro value / units
        (Decimal(-3), Decimal("227.8"), Decimal("2.50"))]     # a sale: negative quantity
    assert {r.holding_id for r in preview.rows if r.isin == "IE00B3RBWM25"} == {degiro[1].id}  # matched by ISIN
    assert len({r.ref for r in preview.rows}) == 6


def test_degiro_import_creates_operations_once(client, db, degiro):
    account, vwrl = degiro
    html = _preview(client, "degiro_transazioni.csv", DEGIRO)
    assert "formato Degiro" in html and "Nuovo titolo: APPLE INC." in html
    assert re.search(r'<option value="\d+" selected>Degiro</option>', html)  # named in the file's name
    page = _import(client, "degiro_transazioni.csv", DEGIRO, account_id=str(account.id))
    assert "6 operazioni importate." in page and "Nuovi titoli:" in page

    db.session.refresh(vwrl)
    assert vwrl.quantity == Decimal(60)  # 25 + 15 + 20
    apple = Holding.query.filter_by(isin="US0378331005").one()
    assert (apple.quantity, apple.asset_class) == (Decimal(5), "Azione")
    assert Holding.query.filter_by(isin="IE00B4WXJJ64").one().asset_class == "ETF"
    trades = Transaction.query.filter(Transaction.units.isnot(None)).all()
    assert len(trades) == 6 and all(t.import_ref for t in trades)
    assert {t.account_id or t.counter_account_id for t in trades} == {account.id}
    assert Transaction.query.filter(Transaction.fee_for_id.isnot(None)).count() == 6

    again = _preview(client, "degiro_transazioni.csv", DEGIRO)
    assert again.count("Già importato") >= 6 and 'name="include"' not in again
    page = _import(client, "degiro_transazioni.csv", DEGIRO)
    assert "0 operazioni importate." in page
    assert Transaction.query.filter(Transaction.units.isnot(None)).count() == 6


def test_generic_layout_bonds_and_sales(client, db):
    page = _import(client, "generico_operazioni.csv", GENERIC)
    assert "4 operazioni importate." in page
    btp = Holding.query.filter_by(isin="IT0005547408").one()
    assert (btp.asset_class, btp.quantity, btp.avg_price) == ("Obbligazione", Decimal(5000), Decimal("1.0015"))
    enel = Holding.query.filter_by(isin="IT0003128367").one()
    assert enel.quantity == Decimal(100)  # 200 bought, 100 sold


def test_already_imported_rows_are_skipped_at_confirm(client, db):
    html = _preview(client, "generico_operazioni.csv", GENERIC)
    data = form_data(html, "broker-form", include=re.findall(r'name="include" value="(\d+)"', html))
    client.post("/portfolio/import/confirm", data=data)
    page = client.post("/portfolio/import/confirm", data=data, follow_redirects=True).get_data(as_text=True)
    assert "4 già presenti sono state ignorate." in page


def test_a_sale_beyond_the_units_is_refused(client, db):
    raw = ("Data;Titolo;ISIN;Quantità;Prezzo\n"
           "01/02/2025;Enel SpA;IT0003128367;-50;7\n").encode()
    page = _import(client, "vendita.csv", raw)
    assert "0 operazioni importate." in page and "Non importate: riga 2" in page


def test_upload_errors(client, db):
    assert "Scegli il file del broker" in client.post("/portfolio/import", follow_redirects=True).get_data(as_text=True)
    page = _preview(client, "vuoto.csv", b"Colonna;Altra\nx;y\n")
    assert "Non trovo le colonne delle operazioni" in page
    page = _preview(client, "solo_quote.csv", b"Data;Titolo;Quantita\n01/02/2025;Enel;5\n")
    assert "Non trovo il prezzo" in page
    page = _preview(client, "versamenti.csv", b"Data;Titolo;Quantita;Prezzo\n01/02/2025;Deposito;;\n")
    assert "Nessuna operazione di compravendita" in page
    page = client.post("/portfolio/import/confirm", data={"payload": "falso"}, follow_redirects=True)
    assert "Anteprima non valida" in page.get_data(as_text=True)
    assert "Analizza file" in client.get("/portfolio/import").get_data(as_text=True)


def test_columns_sides_and_classes(app, db):
    raw = ("Data esecuzione,Operazione,Simbolo,Descrizione,Qty,Controvalore,Commissione\n"
           "2025-03-03,Vendita,ENEL.MI,Enel,10,\"78,50\",\"-1,95\"\n"
           "2025-03-04,Acquisto,ENEL.MI,Enel,10,\"80,00\",0\n"
           "2025-03-04,Acquisto,ENEL.MI,Enel,10,\"80,00\",0\n").encode()
    with app.test_request_context():
        preview = broker_import.read("generico.csv", raw)
    assert preview.layout == "generico"
    assert [(r.on, r.units, r.price, r.fee, r.ticker) for r in preview.rows] == [
        (date(2025, 3, 3), Decimal(-10), Decimal("7.85"), Decimal("1.95"), "ENEL.MI"),
        (date(2025, 3, 4), Decimal(10), Decimal(8), Decimal(0), "ENEL.MI"),
        (date(2025, 3, 4), Decimal(10), Decimal(8), Decimal(0), "ENEL.MI")]
    assert preview.rows[1].ref != preview.rows[2].ref  # the same trade twice in a day is two trades
    assert broker_import._side("xyz") is None and broker_import._side("S") == -1 and broker_import._side("buy") == 1
    assert broker_import.guess_class("BTP Italia 2030") == "Obbligazione"
    assert broker_import.guess_class("Xtrackers MSCI World") == "ETF"
    with pytest.raises(transfer.TableError):
        broker_import._columns(["Data", "Titolo", "Quote"])


def test_match_by_ticker_and_name(app, db):
    enel = Holding(name="Enel", ticker="ENEL.MI", asset_class="Azione", quantity=0, avg_price=0)
    eni = Holding(name="Eni SpA", asset_class="Azione", quantity=0, avg_price=0)
    db.session.add_all([enel, eni])
    db.session.commit()
    raw = ("Data;Ticker;Nome;Quantità;Prezzo\n01/02/2025;ENEL;Enel;5;7\n01/02/2025;;ENI SPA;5;13\n").encode()
    with app.test_request_context():
        preview = broker_import.read("x.csv", raw)
    assert [r.holding_id for r in preview.rows] == [enel.id, eni.id]


def test_suggested_account(client, db):
    db.session.add_all([Account(name="Fineco", kind="current"), Account(name="Directa SIM", kind="other")])
    db.session.commit()
    html = _preview(client, "export.csv", GENERIC)
    assert re.search(r'<option value="\d+" selected>Directa SIM</option>', html)


# ── Bank movements of a holding ────────────────────────────────────────────────

@pytest.fixture()
def bank(db):
    current = Account(name="Conto corrente", kind="current")
    etf = Holding(name="iShares Core MSCI World", isin="IE00B4L5Y983", ticker="SWDA.MI", asset_class="ETF",
                  quantity=10, avg_price=80, opening_quantity=10, opening_price=80, current_price=95)
    db.session.add_all([current, etf])
    db.session.flush()
    buy = Transaction(date=date(2025, 5, 2), description="Acquisto titoli IE00B4L5Y983", amount=Decimal("950.00"),
                      currency="EUR", type="expense", category="Altro", account_id=current.id)
    sale = Transaction(date=date(2025, 9, 1), description="Vendita SWDA", amount=Decimal("500.00"), currency="EUR",
                       type="income", category="Altro", account_id=current.id)
    other = Transaction(date=date(2025, 9, 2), description="Spesa Esselunga", amount=Decimal("80.00"), currency="EUR",
                        type="expense", category="Spesa", account_id=current.id)
    pac = Transaction(date=date(2025, 6, 2), description="PAC mensile", amount=Decimal("100.00"), currency="EUR",
                      type="expense", category="Investimenti", account_id=current.id)
    db.session.add_all([buy, sale, other, pac])
    db.session.commit()
    return current, etf, buy, sale, other, pac


def test_link_movements_of_the_current_account(client, db, bank):
    current, etf, buy, sale, other, pac = bank
    html = client.get(f"/portfolio/{etf.id}/link").get_data(as_text=True)
    assert "Acquisto titoli IE00B4L5Y983" in html and "Vendita SWDA" in html and "PAC mensile" in html
    assert "Esselunga" not in html
    data = form_data(html, "link-form", **{f"link-{buy.id}": "1", f"units-{buy.id}": "10",
                                           f"link-{sale.id}": "1", f"price-{sale.id}": "100",
                                           f"link-{pac.id}": "1"})
    page = client.post(f"/portfolio/{etf.id}/link", data=data, follow_redirects=True).get_data(as_text=True)
    assert "2 movimenti collegati come operazioni" in page and "Indica le quote o il prezzo per i movimenti del 02/06/2025" in page
    db.session.refresh(etf)
    assert etf.quantity == Decimal(15)  # 10 + 10 bought − 5 sold
    db.session.refresh(buy)
    db.session.refresh(sale)
    assert (buy.type, buy.units, buy.unit_price, buy.account_id, buy.counter_account_id) == (
        "transfer", Decimal(10), Decimal(95), current.id, None)
    assert (sale.units, sale.account_id, sale.counter_account_id, sale.category) == (
        Decimal(-5), None, current.id, "Investimenti")
    html = client.get(f"/portfolio/{etf.id}/link").get_data(as_text=True)
    assert "Vendita SWDA" not in html and "PAC mensile" in html


def test_link_page_without_candidates(client, db):
    gold = Holding(name="Oro fisico", asset_class="Altro", quantity=1, avg_price=1)
    db.session.add(gold)
    db.session.commit()
    assert "Nessun movimento da collegare" in client.get(f"/portfolio/{gold.id}/link").get_data(as_text=True)


def test_bank_causale_with_a_held_isin_goes_to_investments(app, bank):
    with app.test_request_context():
        from app.services.bank_import.rows import _held_isins
        isins = _held_isins()
    row = StatementRow(date=date(2025, 5, 2), description="COMPRAVENDITA TITOLI", amount=Decimal("-950"),
                       details="Acquisto ie00b4l5y983 ishares")
    row.type, row.category = "expense", "Altro"
    _investment(row, isins)
    assert row.category == "Investimenti"
    row = StatementRow(date=date(2025, 5, 2), description="Giroconto", amount=Decimal("-950"), details="IE00B4L5Y983")
    row.type, row.category = "transfer", "Giroconto"
    _investment(row, isins)
    assert row.category == "Giroconto"
