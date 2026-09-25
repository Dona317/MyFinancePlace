import io
import re
from datetime import date
from decimal import Decimal

import pytest

from app.models.transaction import Transaction
from app.services import bank_import
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
    categories = {r.details: r.category for r in preview.rows}
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


def test_preview_then_confirm_imports_selected_rows(client, db):
    html = _upload(client, fineco_xlsx(), "movimenti.xlsx").get_data(as_text=True)
    assert "Fineco" in html and "ESSELUNGA" in html

    # Keep rows 0 (Esselunga) and 1 (Netflix); override Esselunga's category
    response = client.post("/export/bank/confirm", data={
        "payload": _payload(html), "include": ["0", "1"],
        "category-0": "Spesa casa", "type-0": "expense",
    })
    assert response.status_code == 302
    txs = Transaction.query.order_by(Transaction.id).all()
    assert [(t.description[:20], t.category, float(t.amount), t.type) for t in txs] == [
        ("Pagamento Visa Debit", "Spesa casa", 87.5, "expense"),
        ("NETFLIX.COM Amsterda", "Abbonamenti", 17.99, "expense"),
    ]
    assert txs[0].tags == ["importato", "fineco"] and txs[0].import_ref


def test_reimport_flags_duplicates(client, db):
    html = _upload(client, fineco_xlsx(), "movimenti.xlsx").get_data(as_text=True)
    client.post("/export/bank/confirm", data={"payload": _payload(html), "include": [str(i) for i in range(6)]})
    assert Transaction.query.count() == 6

    html = _upload(client, fineco_xlsx(), "movimenti.xlsx").get_data(as_text=True)
    assert "6 movimenti erano già stati importati" in html
    # Submitting the old payload again must not create duplicates either
    client.post("/export/bank/confirm", data={"payload": _payload(html), "include": [str(i) for i in range(6)]})
    assert Transaction.query.count() == 6


def test_confirm_rejects_tampered_payload(client, db):
    response = client.post("/export/bank/confirm", data={"payload": "forged", "include": ["0"]})
    assert response.status_code == 302 and response.location.endswith("/export/")
    assert Transaction.query.count() == 0


def test_upload_error_is_reported(client, db):
    response = _upload(client, b"not,a,statement\n1,2,3\n", "x.csv")
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert "Intestazione" in session["_flashes"][0][1]
