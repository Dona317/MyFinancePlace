"""Report → Riepilogo (F2): the year as a category × month table, like the spreadsheet it replaces."""
from datetime import date

from app.services import analytics, categories
from tests.conftest import make_tx


def _data(db):
    categories.ensure_defaults()
    db.session.add_all([
        make_tx(date=date(2026, 1, 27), category="Stipendio", type="income", amount=2000),
        make_tx(date=date(2026, 2, 27), category="Stipendio", type="income", amount=2000),
        make_tx(date=date(2026, 1, 5), category="Luce", amount=60),       # subcategory of Bollette
        make_tx(date=date(2026, 1, 9), category="Bollette", amount=40),
        make_tx(date=date(2026, 2, 5), category="Gas", amount=90),
        make_tx(date=date(2026, 2, 6), category=None, amount=10),         # uncategorized
        make_tx(date=date(2026, 2, 7), category="Casa", type="transfer", amount=500),  # not in the table
        make_tx(date=date(2025, 1, 5), category="Luce", amount=50),       # the year before, same months
        make_tx(date=date(2025, 3, 5), category="Luce", amount=999),      # the year before, a month not shown
    ])
    db.session.commit()


def test_rows_columns_and_totals(app, db):
    _data(db)
    with app.test_request_context():
        table = analytics.summary_table(2026, 2)
    assert table["labels"] == ["Gen", "Feb"] and table["months"] == 2
    income, expenses = table["income"], table["expense"]
    assert [(r["name"], r["months"]) for r in income["rows"]] == [("Stipendio", [2000.0, 2000.0])]
    bollette = expenses["rows"][0]
    assert (bollette["name"], bollette["months"], bollette["total"], bollette["average"]) == ("Bollette", [100.0, 90.0], 190.0, 95.0)
    assert [(c["name"], c["months"]) for c in bollette["children"]] == [("Gas", [0.0, 90.0]), ("Luce", [60.0, 0.0])]  # biggest first
    assert [r["name"] for r in expenses["rows"]] == ["Bollette", analytics.UNCATEGORIZED]
    assert expenses["total"]["months"] == [100.0, 100.0]
    # columns add up to the month totals of the dashboard
    series = analytics.monthly_series(2026)
    assert income["total"]["months"] == series["income"][:2] and expenses["total"]["months"] == series["expenses"][:2]
    assert table["net"] == {"months": [1900.0, 1900.0], "total": 3800.0, "average": 1900.0}
    assert table["savings"] == {"months": [95.0, 95.0], "total": 95.0}


def test_change_on_the_same_months_of_the_year_before(app, db):
    _data(db)
    with app.test_request_context():
        table = analytics.summary_table(2026, 2)
    bollette = table["expense"]["rows"][0]
    assert bollette["previous"] == 50.0 and bollette["change"] == 280.0  # March 2025 (999) is not compared
    luce = bollette["children"][1]
    assert luce["previous"] == 50.0 and luce["change"] == 20.0
    assert table["income"]["rows"][0]["change"] is None  # nothing the year before
    assert table["expense"]["total"]["previous"] == 50.0


def test_summary_page_links_and_csv(client, db):
    _data(db)
    html = client.get("/reports/summary?year=2026").get_data(as_text=True)
    assert "Riepilogo" in html and 'class="report-tab active"' in html
    assert "/transactions/?category=Bollette&amp;month=2026-01&amp;type=expense" in html  # each cell opens its transactions
    assert "--heat: 1.00" in html and "Tasso di risparmio" in html
    assert 'href="/reports/summary"' in client.get("/reports/").get_data(as_text=True)
    csv = client.get("/reports/summary.csv?year=2026").get_data(as_text=True)
    lines = csv.lstrip("﻿").splitlines()
    assert lines[0].startswith("Sezione;Categoria;Gen;Feb")
    assert "Uscite;Bollette › Luce;60,00;0,00;0,00" in csv and lines[-1].startswith("Tasso di risparmio")
    # a year without data falls back to the latest one
    assert client.get("/reports/summary?year=1990").status_code == 200


def test_empty_year(client, db):
    assert "Nessuna entrata o uscita" in client.get("/reports/summary").get_data(as_text=True)
