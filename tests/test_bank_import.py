import io
import sys
import re
from pathlib import Path
from datetime import date
from decimal import Decimal

import pytest

from app.models.transaction import Transaction
from app.services import bank_import
from tests.form_helper import form_data
from tests.statements import fineco_xlsx, intesa_xlsx, intesa_legacy_html, generic_csv


# ── Parsing ────────────────────────────────────────────────────────────────────

def test_fineco_statement(app):
    preview = bank_import.analyze_statement("movimenti.xlsx", fineco_xlsx())
    assert preview.bank.key == "fineco"
    assert preview.pending_skipped == 1  # "Autorizzato" AMAZON row
    rows = {(r.description, r.date): r for r in preview.rows}
    assert len(preview.rows) == 6

    salary = rows[("Bonifico da ACME SPA per STIPENDIO GIUGNO", date(2026, 6, 27))]
    assert (salary.type, salary.category, salary.amount) == ("income", "Stipendio", Decimal("2800"))
    assert salary.details == "Bonifico SEPA Italia"

    grocery = rows[("Pagamento Visa Debit presso ESSELUNGA MILANO", date(2026, 6, 3))]
    assert (grocery.type, grocery.category, grocery.amount) == ("expense", "Alimentari", Decimal("-87.5"))

    transfer = rows[("Giroconto verso conto deposito", date(2026, 6, 10))]
    assert transfer.type == "transfer"

    gym = rows[("PALESTRA FIT", date(2026, 6, 12))]
    assert gym.category == "Sport"  # no rule matched → bank's own (Moneymap) category

    assert preview.rows[0].date == date(2026, 6, 3)  # sorted by date
    assert preview.total_income == Decimal("2800")


def test_identical_rows_get_distinct_fingerprints(app):
    preview = bank_import.analyze_statement("movimenti.xlsx", fineco_xlsx())
    netflix = [r for r in preview.rows if r.description.startswith("NETFLIX")]
    assert len(netflix) == 2
    assert netflix[0].import_ref != netflix[1].import_ref
    assert all(r.category == "Abbonamenti" for r in netflix)


def test_intesa_statement(app):
    preview = bank_import.analyze_statement("ListaMovimenti.xlsx", intesa_xlsx())
    assert preview.bank.key == "intesa"
    assert preview.pending_skipped == 1  # "Non contabilizzato"
    categories = {r.description: r.category for r in preview.rows}
    assert {r.details for r in preview.rows} == {"Accredito stipendio", "Pagamento POS", "Addebito diretto"}
    assert categories == {
        "ACME SPA emolumenti luglio": "Stipendio",
        "CONAD CITY ROMA": "Alimentari",
        "ENEL ENERGIA bolletta luce": "Casa",
        "LIBRERIA FELTRINELLI": "Svago",  # matched through the bank category "Tempo libero"
    }
    assert preview.total_expenses == Decimal("148.5")


def test_intesa_legacy_html_xls(app):
    preview = bank_import.analyze_statement("movimenti.xls", intesa_legacy_html())
    assert preview.bank.key == "intesa"
    amounts = [(r.amount, r.type, r.category) for r in preview.rows]
    assert amounts == [(Decimal("-32.40"), "expense", "Salute"), (Decimal("1250.00"), "income", "Rimborsi")]


def test_generic_csv(app):
    preview = bank_import.analyze_statement("account-statement.csv", generic_csv())
    assert preview.bank.key == "generic"
    assert [(r.date, r.description, r.amount, r.category) for r in preview.rows] == [
        (date(2026, 8, 1), "Uber", Decimal("-14.20"), "Trasporto"),
        (date(2026, 8, 3), "Payment from Mario Rossi", Decimal("200.00"), "Altro"),
    ]


def test_forced_bank_layout_that_does_not_match(app):
    with pytest.raises(bank_import.StatementImportError, match="Intestazione"):
        bank_import.analyze_statement("x.xlsx", intesa_xlsx(), bank="fineco")


def test_unreadable_files(app):
    with pytest.raises(bank_import.StatementImportError):
        bank_import.analyze_statement("x.pdf", b"%PDF-1.4 ...")
    with pytest.raises(bank_import.StatementImportError):
        bank_import.analyze_statement("x.csv", b"")


@pytest.mark.parametrize("text, expected", [
    ("POS CARREFOUR EXPRESS", "Alimentari"),
    ("ADDEBITO SDD TIM SPA", "Abbonamenti"),
    ("IMPOSTA DI BOLLO", "Commissioni"),
    ("Q8 STAZIONE 123", "Trasporto"),
    ("COMPASS", "Altro"),
])
def test_categorize(text, expected):
    assert bank_import.categorize(text) == expected


# ── Web flow ───────────────────────────────────────────────────────────────────

def _upload(client, content: bytes, filename: str, bank: str = "auto"):
    return client.post("/export/bank", data={"file": (io.BytesIO(content), filename), "bank": bank},
                       content_type="multipart/form-data")


def _payload(html: str) -> str:
    return re.search(r'name="payload" value="([^"]+)"', html).group(1)


def _confirm(client, html: str, **overrides):
    """Submit the preview form exactly as the browser would, with optional edits."""
    return client.post("/export/bank/confirm", data=form_data(html, "preview-form", **overrides))


def test_preview_then_confirm_imports_selected_rows(client, db):
    html = _upload(client, fineco_xlsx(), "movimenti.xlsx").get_data(as_text=True)
    assert "Fineco" in html and "ESSELUNGA" in html

    # Keep rows 0 (Esselunga) and 1 (Netflix); override Esselunga's category
    response = _confirm(client, html, include=["0", "1"], **{"category-0": "Spesa casa"})
    assert response.status_code == 302
    txs = Transaction.query.order_by(Transaction.id).all()
    assert [(t.description[:20], t.category, float(t.amount), t.type) for t in txs] == [
        ("Pagamento Visa Debit", "Spesa casa", 87.5, "expense"),
        ("NETFLIX.COM Amsterda", "Abbonamenti", 17.99, "expense"),
    ]
    assert txs[0].tags == ["importato", "fineco"] and txs[0].import_ref


def test_every_field_of_the_preview_can_be_edited(client, db):
    html = _upload(client, fineco_xlsx(), "movimenti.xlsx").get_data(as_text=True)
    _confirm(client, html, include=["0", "6"], **{
        "date-0": "2026-06-04", "description-0": "Spesa Esselunga corretta", "amount-0": "88,40",
        "type-0": "expense", "category-0": "Alimentari",
        # row 6 does not exist in the statement: added by hand in the preview
        "date-6": "2026-06-15", "description-6": "Contanti prelevati", "amount-6": "50",
        "type-6": "expense", "category-6": "Altro",
    })
    first, added = Transaction.query.order_by(Transaction.id).all()
    assert (first.date, first.description, float(first.amount)) == (date(2026, 6, 4), "Spesa Esselunga corretta", 88.4)
    assert first.import_ref  # the correction keeps the statement fingerprint: re-importing still detects it
    assert (added.description, float(added.amount), added.import_ref) == ("Contanti prelevati", 50.0, None)
    assert "manuale" in added.tags


def test_invalid_edited_rows_are_not_saved(client, db):
    html = _upload(client, fineco_xlsx(), "movimenti.xlsx").get_data(as_text=True)
    _confirm(client, html, include=["0", "1"], **{"amount-1": "abc"})
    assert Transaction.query.count() == 1
    with client.session_transaction() as session:
        assert any("Righe non salvate" in message for _, message in session["_flashes"])


@pytest.mark.parametrize("amount", ["NaN", "sNaN", "Infinity", "1e40", "0"])
def test_preview_rejects_unusable_amounts_without_crashing(client, db, amount):
    html = _upload(client, fineco_xlsx(), "movimenti.xlsx").get_data(as_text=True)
    response = _confirm(client, html, include=["0", "1"], **{"amount-0": amount})
    assert response.status_code == 302
    assert Transaction.query.count() == 1  # only row 1 saved


def test_uploads_over_16_mb_are_accepted(client, db, app):
    """No upload size limit (it used to be 16 MB): a 17 MB file reaches the reader instead of a 413 error."""
    assert app.config["MAX_CONTENT_LENGTH"] is None
    response = _upload(client, b"\xd0\xcf\x11\xe0" + b"\0" * (17 * 1024 * 1024), "vecchio.doc")
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert ".docx" in session["_flashes"][0][1]  # read and understood, not rejected for its size


def test_large_statement_with_long_descriptions_is_imported_whole(client, db):
    """No limits: thousands of rows, descriptions longer than 255 characters, all saved from the preview."""
    from datetime import timedelta
    from tests.statements import xlsx
    header = ["Data_Operazione", "Data_Valuta", "Entrate", "Uscite", "Descrizione", "Descrizione_Completa", "Stato", "Moneymap"]
    long_tail = " dettaglio" * 60  # ~600 characters
    rows = [header] + [
        [f"{date(2020, 1, 1) + timedelta(days=i):%d/%m/%Y}"] * 2 + [None, -(i + 1), "Pagamento", f"NEGOZIO {i}{long_tail}", "Contabilizzato", "Shopping"]
        for i in range(6000)
    ]
    html = _upload(client, xlsx(rows), "grande.xlsx").get_data(as_text=True)
    _confirm(client, html)
    assert Transaction.query.count() == 6000  # rows past the old 5,000th are no longer dropped
    tx = Transaction.query.filter(Transaction.description.like("NEGOZIO 5999 %")).one()
    assert len(tx.description) > 600 and tx.bank_description == f"{tx.description} (Pagamento)"


def test_reimport_flags_duplicates(client, db):
    html = _upload(client, fineco_xlsx(), "movimenti.xlsx").get_data(as_text=True)
    _confirm(client, html)  # every row is selected by default
    assert Transaction.query.count() == 6

    html_again = _upload(client, fineco_xlsx(), "movimenti.xlsx").get_data(as_text=True)
    assert "6 movimenti erano già stati importati" in html_again
    # Submitting the first preview again must not create duplicates either
    _confirm(client, html)
    assert Transaction.query.count() == 6


def test_confirm_rejects_tampered_payload(client, db):
    response = client.post("/export/bank/confirm", data={"payload": "forged", "include": ["0"]})
    assert response.status_code == 302 and response.location.endswith("/export/")
    assert Transaction.query.count() == 0


def test_unreadable_file_asks_before_using_ai(client, db):
    response = _upload(client, b"not,a,statement\n1,2,3\n", "x.csv")
    assert response.status_code == 302 and "/export/bank/ai/" in response.location
    page = client.get(response.location).get_data(as_text=True)
    assert "Intestazione" in page  # why the file could not be read
    assert "non è ancora configurata" in page  # AI is off in tests: the page explains how to set it up


def test_unsupported_file_is_reported(client, db):
    response = _upload(client, b"\xd0\xcf\x11\xe0" + b"\0" * 100, "vecchio.doc")
    assert response.status_code == 302 and response.location.endswith("/export/")
    with client.session_transaction() as session:
        assert ".docx" in session["_flashes"][0][1]


# ── Sample statements shipped in samples/bank_statements ──────────────────────

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "bank_statements"


@pytest.mark.parametrize("filename, bank", [
    ("fineco_2026-06_2026-07.xlsx", "fineco"),
    ("fineco_2026-07_2026-09.xlsx", "fineco"),
    ("intesa_sanpaolo_2026-04_2026-09.xlsx", "intesa"),
    ("intesa_sanpaolo_legacy_2026-03.xls", "intesa"),
    ("unicredit_2026-08_2026-09.csv", "generic"),
    ("revolut_2026-09.csv", "generic"),
    ("banca_generica_2026-02.xls", "generic"),  # binary Excel 97-2003, read with xlrd
    ("fineco_estratto_conto_2026-07_2026-08.pdf", "fineco"),
    ("intesa_sanpaolo_lista_movimenti_2026-09.pdf", "intesa"),
    ("banca_popolare_2026-05.txt", "generic"),
    ("estratto_conto_word_2026-01.docx", "generic"),
    ("estratto_conto_libreoffice_2025-12.ods", "generic"),
    ("estratto_conto_2025-11.rtf", "generic"),
])
def test_sample_statements_parse(app, filename, bank):
    preview = bank_import.analyze_statement(filename, (SAMPLES / filename).read_bytes())
    assert preview.bank.key == bank
    assert len(preview.rows) >= 10
    assert preview.total_expenses > 0


def test_overlapping_sample_statements_are_deduplicated(app, db):
    first = bank_import.analyze_statement("a.xlsx", (SAMPLES / "fineco_2026-06_2026-07.xlsx").read_bytes())
    db.session.add_all([bank_import.build_transaction(r.to_dict(), "fineco") for r in first.rows])
    db.session.commit()

    second = bank_import.analyze_statement("b.xlsx", (SAMPLES / "fineco_2026-07_2026-09.xlsx").read_bytes())
    july_in_both = [r for r in second.rows if r.date.month == 7 and r.import_ref in {x.import_ref for x in first.rows}]
    assert second.duplicates == len(july_in_both) > 0


# ── PDF, TXT, Word, OpenDocument, RTF: compare with the generator's ground truth ──

sys.path.insert(0, str(SAMPLES))
import generate as sample_generator  # noqa: E402  (pure-Python part only; no fpdf/xlwt needed)


@pytest.mark.parametrize("filename, period, seed, salary, rent", [
    ("fineco_estratto_conto_2026-07_2026-08.pdf", (date(2026, 7, 1), date(2026, 8, 31)), 77, 2450.0, 850.0),
    ("intesa_sanpaolo_lista_movimenti_2026-09.pdf", (date(2026, 9, 1), date(2026, 9, 24)), 88, 2180.0, 720.0),
    ("banca_popolare_2026-05.txt", (date(2026, 5, 1), date(2026, 5, 31)), 99, 1890.0, 590.0),
    ("estratto_conto_word_2026-01.docx", (date(2026, 1, 1), date(2026, 1, 31)), 111, 2300.0, 780.0),
    ("estratto_conto_libreoffice_2025-12.ods", (date(2025, 12, 1), date(2025, 12, 31)), 122, 2100.0, 700.0),
    ("estratto_conto_2025-11.rtf", (date(2025, 11, 1), date(2025, 11, 30)), 133, 1950.0, 620.0),
])
def test_document_formats_extract_every_movement_exactly(app, filename, period, seed, salary, rent):
    expected = sample_generator.movements(*period, seed, salary=salary, rent=rent)
    preview = bank_import.analyze_statement(filename, (SAMPLES / filename).read_bytes())
    got = sorted((r.date, r.amount) for r in preview.rows)
    assert got == sorted((m["date"], Decimal(f"{m['amount']:.2f}")) for m in expected)


def test_pdf_wrapped_descriptions_are_joined(app):
    filename = "fineco_estratto_conto_2026-07_2026-08.pdf"
    preview = bank_import.analyze_statement(filename, (SAMPLES / filename).read_bytes())
    rent = next(r for r in preview.rows if "AFFITTO" in r.description)
    assert rent.description == "Bonifico SEPA - Bonifico a IMMOBILIARE CASA BELLA SRL per AFFITTO 07/2026"
    assert rent.category == "Casa"
    assert all("SALDO" not in r.description and "Pagina" not in r.description for r in preview.rows)


def test_fixed_width_text_uses_dare_avere_columns(app):
    text = (
        "BANCA DEMO\n\n"
        "Data        Descrizione                         Dare       Avere\n"
        "02/03/2026  PAGAMENTO POS CONAD                 45,10\n"
        "03/03/2026  BONIFICO DA CLIENTE XYZ                       1.200,00\n"
        "            SALDO FINALE                                  9.999,99\n"
    )
    preview = bank_import.analyze_statement("estratto.txt", text.encode())
    assert [(r.description, r.amount) for r in preview.rows] == [
        ("PAGAMENTO POS CONAD", Decimal("-45.10")), ("BONIFICO DA CLIENTE XYZ", Decimal("1200.00")),
    ]


def test_text_lines_without_header_fallback(app):
    text = (
        "Movimenti del mese\n"
        "05/06/2026 NETFLIX.COM AMSTERDAM 17,99\n"
        "27/06/2026 07/06/2026 ACCREDITO STIPENDIO ACME 2.450,00 3.100,00\n"
        "28/06/2026 COMMISSIONI 2,00-\n"
    )
    preview = bank_import.analyze_statement("note.txt", text.encode())
    assert preview.bank.key == "generic"
    assert [(r.description, r.amount, r.type) for r in preview.rows] == [
        ("NETFLIX.COM AMSTERDAM", Decimal("-17.99"), "expense"),
        ("ACCREDITO STIPENDIO ACME", Decimal("2450.00"), "income"),  # income hint; trailing balance ignored
        ("COMMISSIONI", Decimal("-2.00"), "expense"),               # trailing minus sign
    ]


BLANK_PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
             b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF")


@pytest.mark.parametrize("filename, content, message", [
    ("scansione.pdf", BLANK_PDF, "scansione"),
    ("vecchio.doc", b"\xd0\xcf\x11\xe0" + b"\0" * 100, ".docx"),
    ("foto.jpg", b"\xff\xd8\xff\xe0" + b"\0" * 20, "immagini"),
    ("archivio.zip", b"PK\x03\x04" + b"\0" * 30, "Formato non riconosciuto"),
])
def test_unsupported_documents_explain_what_to_do(app, filename, content, message):
    with pytest.raises(bank_import.StatementImportError, match=message):
        bank_import.analyze_statement(filename, content)


def test_same_movement_on_two_banks_is_not_a_duplicate(app, db):
    fineco = bank_import.analyze_statement("f.xlsx", fineco_xlsx())
    db.session.add_all([bank_import.build_transaction(r.to_dict(), "fineco") for r in fineco.rows])
    db.session.commit()
    # Same movements exported by another bank (generic CSV): nothing may be skipped
    lines = ["Data;Descrizione;Importo"] + [
        f"{r.date:%d/%m/%Y};{r.description};{str(r.amount).replace('.', ',')}" for r in fineco.rows
    ]
    other = bank_import.analyze_statement("altra_banca.csv", "\n".join(lines).encode())
    assert other.bank.key == "generic"
    assert other.duplicates == 0 and len(other.rows) == len(fineco.rows)


def test_transfers_are_shown_without_sign(client, db):
    db.session.add(Transaction(date=date(2026, 6, 20), description="Giroconto verso deposito", amount=200,
                               currency="EUR", type="transfer", category="Giroconto", tags=[]))
    db.session.commit()
    for url in ("/transactions/", "/dashboard"):
        html = client.get(url).get_data(as_text=True)
        assert "⇄ € 200,00" in html


def test_upload_pdf_through_web_flow(client, db):
    filename = "intesa_sanpaolo_lista_movimenti_2026-09.pdf"
    html = _upload(client, (SAMPLES / filename).read_bytes(), filename).get_data(as_text=True)
    assert "Intesa Sanpaolo" in html and "TRENITALIA WEB" in html
    _confirm(client, html)
    assert Transaction.query.count() == 21
