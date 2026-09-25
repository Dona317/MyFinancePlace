import io
from datetime import date
from decimal import Decimal

import pytest

from app.models.transaction import Transaction
from app.services import transfer


@pytest.mark.parametrize("raw, expected", [
    ("1.234,56", Decimal("1234.56")),
    ("1,234.56", Decimal("1234.56")),
    ("-45,90", Decimal("-45.90")),
    ("€ 12.5", Decimal("12.5")),
])
def test_parse_amount(raw, expected):
    assert transfer.parse_amount(raw) == expected


def test_parse_amount_invalid():
    with pytest.raises(ValueError):
        transfer.parse_amount("abc")


@pytest.mark.parametrize("raw", ["2026-06-15", "15/06/2026", "15.06.2026"])
def test_parse_date(raw):
    assert transfer.parse_date(raw) == date(2026, 6, 15)


def test_rows_to_transactions_uses_sign_for_type():
    rows = [
        {"Data": "01/06/2026", "Importo": "-12,50", "Causale": "Bar"},
        {"Data": "02/06/2026", "Importo": "100", "Causale": "Rimborso"},
        {"Data": "bad", "Importo": "1", "Causale": "X"},
    ]
    mapping = {"date": "Data", "amount": "Importo", "description": "Causale"}
    txs, errors = transfer.rows_to_transactions(rows, mapping)
    assert [(t.type, t.amount) for t in txs] == [("expense", Decimal("12.50")), ("income", Decimal("100"))]
    assert errors == ["Riga 4: data non riconosciuta: 'bad'"]


def test_period_bounds():
    today = date(2026, 12, 10)
    assert transfer.period_bounds("month", today) == (date(2026, 12, 1), date(2027, 1, 1))
    assert transfer.period_bounds("last_year", today) == (date(2025, 1, 1), date(2026, 1, 1))
    assert transfer.period_bounds("all", today) == (None, None)


def test_export_csv(client, sample_data):
    response = client.get("/export/csv?period=all")
    assert response.status_code == 200
    assert "attachment" in response.headers["Content-Disposition"]
    body = response.get_data(as_text=True)
    assert body.startswith("﻿id;date;description")
    assert body.count("\n") == 9  # header + 8 transactions


def test_export_json(client, sample_data):
    data = client.get("/export/json").get_json(force=True)
    assert len(data["transactions"]) == 8
    assert data["transactions"][0]["date"] == "2025-12-01"


def test_export_tax_includes_income_and_deductible_only(client, sample_data):
    body = client.get("/export/tax/2026").get_data(as_text=True)
    assert "Stipendio" in body and "Netflix" in body
    assert "Affitto" not in body and "ETF" not in body


def test_export_pdf_report(client, sample_data):
    response = client.get("/export/pdf?year=2026")
    assert response.status_code == 200
    assert "Report Finanziario 2026" in response.get_data(as_text=True)


def test_import_csv(client, db):
    csv_content = "Data;Importo;Causale;Categoria\n01/06/2026;-12,50;Bar;Svago\n02/06/2026;1.500,00;Stipendio;Stipendio\n"
    response = client.post("/export/import", data={
        "file": (io.BytesIO(csv_content.encode()), "movimenti.csv"),
        "col_date": "Data", "col_amount": "Importo", "col_description": "Causale", "col_category": "Categoria",
    }, content_type="multipart/form-data")
    assert response.status_code == 302
    rows = Transaction.query.order_by(Transaction.date).all()
    assert [(t.description, t.type, float(t.amount), t.category) for t in rows] == [
        ("Bar", "expense", 12.5, "Svago"), ("Stipendio", "income", 1500.0, "Stipendio"),
    ]


def test_import_csv_rejects_invalid_rows_atomically(client, db):
    csv_content = "Data,Importo,Causale\n2026-06-01,10,Ok\nnot-a-date,5,Bad\n"
    client.post("/export/import", data={
        "file": (io.BytesIO(csv_content.encode()), "x.csv"),
        "col_date": "Data", "col_amount": "Importo", "col_description": "Causale",
    }, content_type="multipart/form-data")
    assert Transaction.query.count() == 0
