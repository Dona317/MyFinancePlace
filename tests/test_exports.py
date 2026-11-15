"""Exports: every file is named YYYYMMDD_NAME.format, and the Excel of a CSV button has the CSV's cells."""
import io
import re
from datetime import date

from openpyxl import load_workbook

from app.routes.helpers import export_name
from tests.conftest import make_tx

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_export_name_is_the_day_then_the_name():
    assert export_name("transazioni_all", "csv") == f"{date.today():%Y%m%d}_transazioni_all.csv"


def test_csv_and_excel_of_the_transactions_hold_the_same_cells(client, db):
    db.session.add(make_tx(description="Spesa grande", amount=-500, category="Casa"))
    db.session.commit()
    csv_response = client.get("/export/csv?period=all")
    assert csv_response.status_code == 200
    disposition = csv_response.headers["Content-Disposition"]
    assert re.search(r'filename="\d{8}_transazioni_all\.csv"', disposition)
    csv_text = csv_response.get_data(as_text=True).lstrip("﻿")

    xlsx_response = client.get("/export/csv?period=all&format=xlsx")
    assert xlsx_response.mimetype == XLSX
    assert re.search(r'filename="\d{8}_transazioni_all\.xlsx"', xlsx_response.headers["Content-Disposition"])
    sheet = load_workbook(io.BytesIO(xlsx_response.data)).active
    cells = [[cell if cell is not None else "" for cell in row] for row in sheet.iter_rows(values_only=True)]
    expected = [line.split(";") for line in csv_text.splitlines()]
    assert [[str(c) for c in row] for row in cells] == expected
