"""F6: statements in the interchange formats — OFX/QFX (SGML and XML), QIF and CAMT.053."""
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.transaction import Transaction
from app.services import bank_import, categories
from app.services import structured_statements as structured
from tests.form_helper import form_data

SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "bank_statements"

OFX_SGML = b"""OFXHEADER:100
DATA:OFXSGML
VERSION:102

<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>EUR
<BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260603120000<TRNAMT>-45,90<FITID>1<NAME>ESSELUNGA MILANO<MEMO>Pagamento POS
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260627<TRNAMT>2100.00<FITID>2<NAME>ACME SPA &amp; C.<MEMO>STIPENDIO GIUGNO
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20261399<TRNAMT>-1<FITID>3<NAME>Data sbagliata
</BANKTRANLIST>
<LEDGERBAL><BALAMT>3054.10<DTASOF>20260630</LEDGERBAL>
</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""

QIF = """!Type:Bank
D06/13/2026
T-1,234.50
PIMMOBILIARE ROSSI
MAffitto giugno
LCasa:Affitto
^
D06/02/2026
T-30.00
PConto deposito
L[Deposito]
^
D07/01'26
U150.00
PRimborso
LCategoria inventata
^
""".encode()

CAMT = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"><BkToCstmrStmt><Stmt>
<Bal><Tp><CdOrPrtry><Cd>PRCD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">1000.00</Amt><CdtDbtInd>CRDT</CdtDbtInd></Bal>
<Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">1450.00</Amt><CdtDbtInd>CRDT</CdtDbtInd></Bal>
<Ntry><Amt Ccy="EUR">500.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts><BookgDt><DtTm>2026-06-05T10:00:00</DtTm></BookgDt>
 <NtryDtls><TxDtls><RltdPties><Dbtr><Pty><Nm>STUDIO BIANCHI</Nm></Pty></Dbtr></RltdPties>
 <RmtInf><Ustrd>Fattura 12</Ustrd><Ustrd>consulenza</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
<Ntry><Amt Ccy="USD">50.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts><BookgDt><Dt>2026-06-07</Dt></BookgDt>
 <AddtlNtryInf>GITHUB INC abbonamento</AddtlNtryInf></Ntry>
<Ntry><Amt Ccy="EUR">20.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts><Cd>PDNG</Cd></Sts><BookgDt><Dt>2026-06-08</Dt></BookgDt></Ntry>
<Ntry><Amt Ccy="EUR">1.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts>BOOK</Sts><BookgDt><Dt>2026-02-30</Dt></BookgDt></Ntry>
</Stmt></BkToCstmrStmt></Document>
""".encode()


def test_detect():
    assert structured.detect(OFX_SGML) == "ofx" and structured.detect(b"\xef\xbb\xbf<?xml?><?OFX x?><OFX>") == "ofx"
    assert structured.detect(QIF) == "qif" and structured.detect(CAMT) == "camt"
    assert structured.detect(b"Data;Importo\n01/01/2026;10") is None
    assert structured.parse("x.csv", b"Data;Importo") is None


def test_ofx_sgml():
    statement = structured.parse("conto.ofx", OFX_SGML)
    esselunga, salary = statement.movements
    assert (esselunga.date, esselunga.amount, esselunga.description, esselunga.details) == (
        date(2026, 6, 3), Decimal("-45.90"), "ESSELUNGA MILANO", "Pagamento POS")
    assert salary.amount == Decimal("2100.00") and salary.description == "ACME SPA & C."
    assert statement.closing == Decimal("3054.10") and statement.opening is None
    assert statement.unread == ["Movimento 3: data o importo non validi"]


def test_qif_dates_categories_and_transfers():
    statement = structured.parse("conto.qif", QIF)
    transfer, rent, refund = statement.movements  # sorted by date; 13 in the first field: month first
    assert rent.date == date(2026, 6, 13) and rent.amount == Decimal("-1234.50") and rent.category == "Casa:Affitto"
    assert rent.details == "Affitto giugno"
    assert transfer.transfer and transfer.category is None and transfer.date == date(2026, 6, 2)
    assert refund.date == date(2026, 7, 1) and refund.amount == Decimal("150.00")


def test_qif_day_first_by_default_and_unsupported_types():
    statement = structured.parse("a.qif", b"!Type:CCard\nD03/04/2026\nT-5\nPBar\n^\nD2026-04-09\nT-6\nMSolo memo\n^\n")
    assert [m.date for m in statement.movements] == [date(2026, 4, 3), date(2026, 4, 9)]
    assert statement.movements[1].description == "Solo memo"
    with pytest.raises(structured.StructuredFileError, match="Invst"):
        structured.parse("a.qif", b"!Type:Invst\nD03/04/2026\n^\n")
    with pytest.raises(structured.StructuredFileError, match="non contiene movimenti"):
        structured.parse("a.qif", b"!Type:Bank\nDboh\nT-5\n^\n")


def test_camt():
    statement = structured.parse("estratto.xml", CAMT)
    income, github = statement.movements
    assert (income.date, income.amount, income.counterparty, income.description, income.details) == (
        date(2026, 6, 5), Decimal("500.00"), "STUDIO BIANCHI", "STUDIO BIANCHI", "Fattura 12 consulenza")
    assert github.amount == Decimal("-50.00") and github.currency == "USD" and github.description == "GITHUB INC abbonamento"
    assert statement.skipped == 1 and statement.unread == ["Movimento 4: data o importo non validi"]
    assert (statement.opening, statement.closing) == (Decimal("1000.00"), Decimal("1450.00"))


@pytest.mark.parametrize("raw, message", [
    (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"/>',
     "DOCTYPE"),
    (b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"><Stmt>', "non è un XML valido"),
    (b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"></Document>', "non contiene movimenti"),
])
def test_camt_refused(raw, message):
    with pytest.raises(structured.StructuredFileError, match=message):
        structured.parse("x.xml", raw)


def test_preview_keeps_the_file_category_and_the_transfer(app, db):
    categories.ensure_defaults()
    with app.test_request_context():
        preview = bank_import.analyze_statement("conto.qif", QIF)
        camt = bank_import.analyze_statement("estratto.xml", CAMT)
    by_desc = {r.description: r for r in preview.rows}
    assert preview.bank.name == "QIF" and by_desc["IMMOBILIARE ROSSI"].category == "Affitto"
    assert (by_desc["Conto deposito"].type, by_desc["Conto deposito"].category) == ("transfer", "Giroconto")
    assert by_desc["Rimborso"].type == "income"  # "Categoria inventata" is not ours: the usual guess
    assert camt.pending_skipped == 1 and camt.balance_check.ok  # 1000 + 500 - 50 = 1450
    assert camt.rows[0].counterparty == "STUDIO BIANCHI" and camt.rows[1].currency == "USD"
    assert bank_import.layout_named("camt").name.startswith("CAMT") and bank_import.layout_named("boh").key == "generic"


def test_invalid_structured_file_is_an_import_error(app, db):
    with app.test_request_context(), pytest.raises(bank_import.StatementImportError, match="Invst"):
        bank_import.analyze_statement("a.qif", b"!Type:Invst\n^\n")


@pytest.mark.parametrize("name, count", [
    ("conto_ofx_2026-04_2026-05.ofx", 56), ("carta_credito_ofx2_2026-08.qfx", 10),
    ("conto_quicken_2026-03.qif", 27), ("camt053_2026-09.xml", 23),
])
def test_samples(app, db, name, count):
    with app.test_request_context():
        preview = bank_import.analyze_statement(name, (SAMPLES / name).read_bytes())
    assert len(preview.rows) == count and not preview.unread
    if name.startswith("camt"):
        assert preview.balance_check.ok and preview.pending_skipped == 1


def test_upload_preview_confirm_and_duplicates(client, db):
    def upload():
        return client.post("/export/bank", data={"file": (io.BytesIO(CAMT), "estratto.xml"), "bank": "auto"},
                           content_type="multipart/form-data").get_data(as_text=True)

    html = upload()
    assert "CAMT.053" in html and "STUDIO BIANCHI" in html and "Quadratura verificata" in html
    response = client.post("/export/bank/confirm", data=form_data(html, "preview-form"))
    assert response.status_code == 302 and Transaction.query.count() == 2
    flashes = client.get("/transactions/").get_data(as_text=True)
    assert "importati da CAMT.053" in flashes
    again = upload()
    assert "2 movimenti erano già stati importati" in again and again.count("Già importato</span>") == 2
