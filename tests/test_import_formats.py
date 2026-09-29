"""Bank layouts (UniCredit, BPER, BancoPosta, ING, Revolut, N26), Word 97-2003 .doc, manual mapping of
Excel files and the downloadable PDF report."""
import io
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.transaction import Transaction
from app.services import bank_import, statement_readers, transfer
from tests.statements import fineco_xlsx, xlsx

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "bank_statements"
sys.path.insert(0, str(SAMPLES))
import generate as sample_generator  # noqa: E402


def _csv(*lines: str) -> bytes:
    return "\n".join(lines).encode()


# ── Revolut ────────────────────────────────────────────────────────────────────

REVOLUT_HEADER = "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance"


def test_revolut_fees_states_and_currencies(app):
    preview = bank_import.analyze_statement("account-statement_2026-08.csv", _csv(
        REVOLUT_HEADER,
        "ATM,Current,2026-08-02 10:00:00,2026-08-02 10:01:00,Cash at BANCOMAT,-100.00,1.99,EUR,COMPLETED,898.01",
        "CARD_PAYMENT,Current,2026-08-03 09:00:00,2026-08-04 09:00:00,Github,-4.00,0.00,USD,COMPLETED,96.00",
        "CARD_PAYMENT,Current,2026-08-05 09:00:00,,Amazon,-24.99,0.00,EUR,PENDING,",
        "CARD_PAYMENT,Current,2026-08-06 09:00:00,,Zara,-59.90,0.00,EUR,REVERTED,",
        "CARD_PAYMENT,Current,2026-08-07 09:00:00,,Shop,-5.00,0.00,EUR,DECLINED,",
        "TOPUP,Current,2026-08-08 09:00:00,2026-08-08 09:00:00,Payment from Mario Rossi,300.00,0.00,EUR,COMPLETED,1198.01",
    ))
    assert preview.bank.key == "revolut"
    assert preview.pending_skipped == 3  # pending, reverted and declined rows are never booked
    got = [(r.date, r.description, r.amount, r.currency, r.type) for r in preview.rows]
    assert got == [
        (date(2026, 8, 2), "Cash at BANCOMAT", Decimal("-100.00"), "EUR", "expense"),
        # the fee is a separate expense, so it adds up under Commissioni
        (date(2026, 8, 2), "Commissione Revolut: Cash at BANCOMAT", Decimal("-1.99"), "EUR", "expense"),
        (date(2026, 8, 3), "Github", Decimal("-4.00"), "USD", "expense"),  # Started Date, original currency
        (date(2026, 8, 8), "Payment from Mario Rossi", Decimal("300.00"), "EUR", "income"),
    ]
    assert preview.rows[1].category == "Commissioni"
    assert bank_import.build_transaction(preview.rows[2].to_dict(), "revolut").currency == "USD"


def test_revolut_sample_matches_the_generator(app):
    filename = "revolut_2026-09.csv"
    preview = bank_import.analyze_statement(filename, (SAMPLES / filename).read_bytes())
    source = sample_generator.revolut_movements(date(2026, 9, 1), date(2026, 9, 24), 55)
    booked = [m for m in source if m["state"] == "COMPLETED"]
    expected = [(m["date"], Decimal(f"{m['amount']:.2f}")) for m in booked]
    expected += [(m["date"], -Decimal(f"{m['fee']:.2f}")) for m in booked if m["fee"]]
    assert sorted((r.date, r.amount) for r in preview.rows) == sorted(expected)
    assert preview.pending_skipped == len(source) - len(booked) == 2
    assert {r.currency for r in preview.rows} == {"EUR", "USD"}


# ── N26 ────────────────────────────────────────────────────────────────────────

def test_n26_current_export(app):
    preview = bank_import.analyze_statement("export.csv", _csv(
        '"Booking Date","Value Date","Partner Name","Partner Iban","Type","Payment Reference","Account Name",'
        '"Amount (EUR)","Original Amount","Original Currency","Exchange Rate"',
        '"2026-08-01","2026-08-01","ACME SPA","IT60X0542811101000000123456","Income","Stipendio agosto",'
        '"Main Account","2200.00","","",""',
        '"2026-08-03","2026-08-03","ESSELUNGA","","Presentment","","Main Account","-45.10","","",""',
        '"2026-08-04","2026-08-04","AMAZON US","","Presentment","","Main Account","-18.40","20.00","USD","1.087"',
    ))
    assert preview.bank.key == "n26"
    assert [(r.description, r.details, r.amount, r.currency, r.category) for r in preview.rows] == [
        ("ACME SPA", "Stipendio agosto", Decimal("2200.00"), "EUR", "Stipendio"),
        ("ESSELUNGA", None, Decimal("-45.10"), "EUR", "Alimentari"),    # details: the Payment Reference
        ("AMAZON US", None, Decimal("-18.40"), "EUR", "Altro"),  # booked in EUR; the original USD is informational
    ]


def test_n26_older_export(app):
    preview = bank_import.analyze_statement("n26-csv-transactions.csv", _csv(
        '"Date","Payee","Account number","Transaction type","Payment reference","Amount (EUR)",'
        '"Amount (Foreign Currency)","Type Foreign Currency","Exchange Rate"',
        '"2026-07-02","Spotify","","MasterCard Payment","","-10.99","","",""',
        '"2026-07-27","ACME SPA","IT60X0542811101000000123456","Income","STIPENDIO","2100.00","","",""',
    ))
    assert preview.bank.key == "n26"
    assert [(r.date, r.description, r.amount) for r in preview.rows] == [
        (date(2026, 7, 2), "Spotify", Decimal("-10.99")), (date(2026, 7, 27), "ACME SPA", Decimal("2100.00")),
    ]


# ── Italian banks ──────────────────────────────────────────────────────────────

def test_unicredit_csv(app):
    preview = bank_import.analyze_statement("ElencoMovimenti.csv", _csv(
        "Data Registrazione;Data valuta;Descrizione;Importo (EUR)",
        "01.08.2026;01.08.2026;PAGAMENTO POS LIDL ITALIA;-70,46",
        "27.08.2026;27.08.2026;BONIFICO DA ACME SPA STIPENDIO;1.980,00",
    ))
    assert preview.bank.key == "unicredit"
    assert [(r.date, r.amount) for r in preview.rows] == [
        (date(2026, 8, 1), Decimal("-70.46")), (date(2026, 8, 27), Decimal("1980.00")),
    ]


def test_bper_xlsx(app):
    preview = bank_import.analyze_statement("movimenti.xlsx", xlsx([
        ["BPER Banca - Movimenti conto corrente"],
        [],
        ["Data contabile", "Data valuta", "Causale ABI", "Descrizione", "Importo", "Divisa"],
        [datetime(2026, 7, 5), datetime(2026, 7, 5), "43 - PAGAMENTO POS", "NETFLIX.COM", -17.99, "EUR"],
        [datetime(2026, 7, 27), datetime(2026, 7, 27), "48 - BONIFICO", "ACME SPA STIPENDIO", 2010, "EUR"],
    ]))
    assert preview.bank.key == "bper"
    assert [(r.description, r.details, r.amount, r.category) for r in preview.rows] == [
        ("NETFLIX.COM", "43 - PAGAMENTO POS", Decimal("-17.99"), "Abbonamenti"),
        ("ACME SPA STIPENDIO", "48 - BONIFICO", Decimal("2010"), "Stipendio"),
    ]


@pytest.mark.parametrize("debit, credit, description", [
    ("Addebiti (euro)", "Accrediti (euro)", "Descrizione operazioni"),
    ("ADDEBITI", "ACCREDITI", "DESCRIZIONE OPERAZIONI"),      # upper case
    ("Addébiti", "Accréditi", "Descrizióne operazióni"),      # accents are ignored
])
def test_bancoposta_headers_case_and_accents(app, debit, credit, description):
    preview = bank_import.analyze_statement("lista.xlsx", xlsx([
        ["Data Contabile", "Data Valuta", debit, credit, description],
        ["01/06/2026", "01/06/2026", "41,27", "", "PAGAMENTO POS FARMACIA COMUNALE"],
        ["27/06/2026", "27/06/2026", "", "1.820,00", "BONIFICO DA ACME SPA STIPENDIO"],
    ]))
    assert preview.bank.key == "poste"
    assert [(r.amount, r.category) for r in preview.rows] == [
        (Decimal("-41.27"), "Salute"), (Decimal("1820.00"), "Stipendio"),
    ]


def test_ing_xlsx(app):
    preview = bank_import.analyze_statement("movimenti.xlsx", xlsx([
        ["ING - Conto Corrente Arancio"],
        ["Data contabile", "Data valuta", "Uscite", "Entrate", "Causale", "Descrizione operazione"],
        ["02/05/2026", "02/05/2026", 18.4, None, "PAGAMENTO CARTA", "PAGAMENTO POS PIZZERIA NAPOLI"],
        ["27/05/2026", "27/05/2026", None, 2280, "BONIFICO SEPA", "Bonifico da ACME SPA per STIPENDIO"],
    ]))
    assert preview.bank.key == "ing"
    assert [(r.amount, r.details) for r in preview.rows] == [
        (Decimal("-18.4"), "PAGAMENTO CARTA"), (Decimal("2280"), "BONIFICO SEPA"),
    ]


# ── Detection ──────────────────────────────────────────────────────────────────

def test_header_key_ignores_case_accents_and_punctuation():
    assert bank_import.header_key("  Descrizióne  OPERAZIONI ") == "descrizione operazioni"
    assert bank_import.header_key("Importo (€)") == "importo"
    assert bank_import.header_key("Amount (EUR)") == "amount eur"


def test_bank_name_in_a_movement_does_not_change_the_bank(app):
    """Only the rows above the header and the filename identify the bank, not the movements."""
    lines = ["Data;Descrizione;Importo", "01/06/2026;RICARICA REVOLUT;-50,00", "02/06/2026;BONIFICO N26;-20,00"]
    assert bank_import.analyze_statement("estratto.csv", _csv(*lines)).bank.key == "generic"

    rows = [["Data_Operazione", "Data_Valuta", "Entrate", "Uscite", "Descrizione", "Descrizione_Completa", "Stato", "Moneymap"],
            ["01/06/2026", "01/06/2026", None, -50, "Bonifico", "Ricarica Revolut Mario", "Contabilizzato", "Altro"]]
    assert bank_import.analyze_statement("movimenti.xlsx", xlsx(rows)).bank.key == "fineco"


def test_bank_named_in_filename_or_preamble(app):
    plain = ["Data;Descrizione;Importo", "01/06/2026;PAGAMENTO POS CONAD;-20,00"]
    assert bank_import.analyze_statement("unicredit_giugno.csv", _csv(*plain)).bank.key == "unicredit"
    assert bank_import.analyze_statement("x.csv", _csv("BPER Banca", *plain)).bank.key == "bper"
    assert bank_import.analyze_statement("x.csv", _csv("Conto BancoPosta", *plain)).bank.key == "poste"
    # "imposte" contains "poste": markers are not matched inside other words
    assert bank_import.analyze_statement("imposte.csv", _csv(*plain)).bank.key == "generic"


def test_every_new_bank_can_be_forced(app):
    rows = {
        "unicredit": ["Data Registrazione;Descrizione;Importo (EUR)", "01/06/2026;CONAD;-20,00"],
        "bper": ["Data contabile;Causale ABI;Descrizione;Importo", "01/06/2026;43;CONAD;-20,00"],
        "poste": ["Data Contabile;Addebiti;Accrediti;Descrizione operazioni", "01/06/2026;20,00;;CONAD"],
        "ing": ["Data contabile;Uscite;Entrate;Causale;Descrizione operazione", "01/06/2026;20,00;;POS;CONAD"],
        "revolut": [REVOLUT_HEADER, "CARD_PAYMENT,Current,2026-06-01 10:00,2026-06-01 10:00,CONAD,-20.00,0,EUR,COMPLETED,1"],
        "n26": ['"Booking Date","Partner Name","Amount (EUR)"', '"2026-06-01","CONAD","-20.00"'],
    }
    for bank, lines in rows.items():
        preview = bank_import.analyze_statement("x.csv", _csv(*lines), bank=bank)
        assert (bank, [r.amount for r in preview.rows]) == (bank, [Decimal("-20.00")])


def test_new_banks_are_offered_in_the_form(client, db):
    html = client.get("/export/").get_data(as_text=True)
    for name in ("UniCredit", "BPER Banca", "Poste Italiane (BancoPosta)", "ING", "Revolut", "N26"):
        assert f">{name}</option>" in html


@pytest.mark.parametrize("filename, bank, count", [
    ("revolut_2026-09.csv", "Revolut", 15),
    ("n26_2026-08.csv", "N26", 25),
    ("bper_2026-07.xlsx", "BPER Banca", 26),
    ("bancoposta_2026-06.xlsx", "Poste Italiane (BancoPosta)", 26),
    ("ing_2026-05.xlsx", "ING", 24),
    ("unicredit_2026-08_2026-09.csv", "UniCredit", 51),
    ("estratto_conto_word97_2025-10.doc", "Altra banca (generico)", 23),
])
def test_new_samples_through_the_web_flow(client, db, filename, bank, count):
    from tests.form_helper import form_data
    response = client.post("/export/bank", data={"file": (io.BytesIO((SAMPLES / filename).read_bytes()), filename),
                                                 "bank": "auto"}, content_type="multipart/form-data")
    html = response.get_data(as_text=True)
    assert response.status_code == 200 and bank in html
    client.post("/export/bank/confirm", data=form_data(html, "preview-form"))
    assert Transaction.query.count() == count
    tags = Transaction.query.first().tags
    assert tags[:2] == ["importato", bank_import.analyze_statement(filename, (SAMPLES / filename).read_bytes()).bank.key]


# ── Word 97-2003 (.doc) ────────────────────────────────────────────────────────

def test_doc_table_rows_become_tab_separated_lines():
    raw = (SAMPLES / "estratto_conto_word97_2025-10.doc").read_bytes()
    lines = statement_readers.doc_text_lines(raw)
    assert lines[:4] == ["Estratto conto - Banca Demo", "Intestatario: MARIO ROSSI", "Periodo: 01/10/2025 - 31/10/2025",
                         "Data\tDescrizione\tImporto"]
    assert "Documento generato per test - dati fittizi." in lines


def test_doc_empty_cells_and_fields():
    text = "Titolo \x13 PAGE \x14" + "1\x15\rA\x07\x07C\x07\x07D\x07E\x07F\x07\x07Fine"
    assert statement_readers._doc_lines(text) == ["Titolo 1", "A\t\tC", "D\tE\tF", "Fine"]


def test_doc_without_extension_is_recognized(app):
    raw = (SAMPLES / "estratto_conto_word97_2025-10.doc").read_bytes()
    assert len(bank_import.analyze_statement("allegato", raw).rows) == 23


def test_broken_doc_explains_what_to_do(app):
    with pytest.raises(bank_import.StatementImportError, match=r"\.docx o PDF"):
        bank_import.analyze_statement("rotto.doc", b"\xd0\xcf\x11\xe0" + b"\0" * 2000)


# ── Manual column mapping: Excel and .ods ──────────────────────────────────────

def _mapping_upload(client, content: bytes, filename: str, **columns):
    data = {"file": (io.BytesIO(content), filename)}
    data.update({f"col_{k}": v for k, v in columns.items()})
    return client.post("/export/import", data=data, content_type="multipart/form-data")


def test_manual_mapping_reads_xlsx_with_a_preamble(client, db):
    content = xlsx([
        ["Estratto conto Banca Demo"],
        ["Intestatario: MARIO ROSSI", "", ""],
        [],
        ["Giorno", "Importo", "Causale", "Categoria"],
        [datetime(2026, 6, 1), -12.5, "Bar", "Svago"],
        ["02/06/2026", 1500, "Stipendio", "Stipendio"],
        [],
    ])
    columns = client.post("/export/import/columns", data={"file": (io.BytesIO(content), "banca.xlsx")},
                          content_type="multipart/form-data").get_json()
    assert columns == {"headers": ["Giorno", "Importo", "Causale", "Categoria"], "rows": 2, "header_line": 4}

    response = _mapping_upload(client, content, "banca.xlsx", date="Giorno", amount="Importo",
                               description="Causale", category="Categoria")
    assert response.status_code == 302
    rows = Transaction.query.order_by(Transaction.date).all()
    assert [(t.date, t.description, t.type, float(t.amount), t.category) for t in rows] == [
        (date(2026, 6, 1), "Bar", "expense", 12.5, "Svago"),
        (date(2026, 6, 2), "Stipendio", "income", 1500.0, "Stipendio"),
    ]


@pytest.mark.parametrize("filename", ["banca_generica_2026-02.xls", "estratto_conto_libreoffice_2025-12.ods"])
def test_manual_mapping_reads_xls_and_ods_headers(client, db, filename):
    columns = client.post("/export/import/columns", data={
        "file": (io.BytesIO((SAMPLES / filename).read_bytes()), filename),
    }, content_type="multipart/form-data").get_json()
    assert columns["headers"][:2] in (["Data operazione", "Descrizione"], ["Data", "Descrizione"])
    assert columns["rows"] >= 10


def test_manual_mapping_xls_import(client, db):
    filename = "banca_generica_2026-02.xls"  # binary Excel 97-2003 with Dare/Avere: map Avere as the amount
    raw = (SAMPLES / filename).read_bytes()
    headers, rows, first_line = transfer.read_table(filename, raw)
    assert (headers, first_line) == (["Data operazione", "Descrizione", "Dare", "Avere"], 4)
    income = [r for r in rows if r["Avere"]]
    _mapping_upload(client, _csv("Data;Descrizione;Importo", *(
        f"{r['Data operazione']};{r['Descrizione']};{r['Avere']}" for r in income)), "avere.csv",
        date="Data", amount="Importo", description="Descrizione")
    assert Transaction.query.count() == len(income) > 0


def test_manual_mapping_error_line_numbers_match_the_spreadsheet(client, db):
    content = xlsx([["Titolo"], ["Data", "Importo", "Causale"], ["01/06/2026", 10, "Ok"], ["non una data", 5, "Male"]])
    _mapping_upload(client, content, "x.xlsx", date="Data", amount="Importo", description="Causale")
    assert Transaction.query.count() == 0
    with client.session_transaction() as session:
        assert "Riga 4" in session["_flashes"][0][1]


def test_manual_mapping_rejects_other_formats(client, db):
    response = client.post("/export/import/columns", data={"file": (io.BytesIO(b"%PDF-1.4"), "x.pdf")},
                           content_type="multipart/form-data")
    assert response.status_code == 400 and "Formato non supportato" in response.get_json()["error"]
    _mapping_upload(client, fineco_xlsx(), "movimenti.docx", date="Data", amount="Importo", description="Causale")
    with client.session_transaction() as session:
        assert "Formato non supportato" in session["_flashes"][0][1]


# ── PDF report ─────────────────────────────────────────────────────────────────

def test_pdf_report_download(client, sample_data):
    import pdfplumber
    response = client.get("/export/pdf/download?year=2026")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")
    assert 'filename="report_finanziario_2026.pdf"' in response.headers["Content-Disposition"]
    with pdfplumber.open(io.BytesIO(response.data)) as pdf:
        text = "\n".join(page.extract_text() for page in pdf.pages)
    for expected in ("Report Finanziario 2026", "Conto Economico", "Andamento Mensile", "Rendiconto Finanziario",
                     "€ 5.800,00", "Stipendio", "Alimentari", "-€ 500,00", "Giu"):
        assert expected in text, expected


def test_pdf_report_for_an_empty_year(client, db):
    response = client.get("/export/pdf/download?year=2019")
    assert response.status_code == 200 and response.data.startswith(b"%PDF")


def test_printable_report_offers_the_pdf_download(client, sample_data):
    html = client.get("/export/pdf?year=2026").get_data(as_text=True)
    assert "/export/pdf/download?year=2026" in html and "Stampa dal browser" in html
