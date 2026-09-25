import pytest

from app.models.transaction import Transaction


@pytest.mark.parametrize("url", [
    "/dashboard",
    "/accounting/income-statement?year=2026",
    "/accounting/cash-flow?year=2026",
    "/lifestyle/?year=2026",
    "/transactions/",
    "/export/",
])
def test_pages_render_with_data(client, sample_data, url):
    assert client.get(url).status_code == 200


@pytest.mark.parametrize("url", ["/dashboard", "/accounting/income-statement", "/accounting/cash-flow", "/lifestyle/"])
def test_pages_render_empty(client, app, url):
    assert client.get(url).status_code == 200


def test_income_statement_shows_categories(client, sample_data):
    html = client.get("/accounting/income-statement?year=2026").get_data(as_text=True)
    assert "Stipendio" in html and "Alimentari" in html
    assert "€ 5.800,00" in html


def test_transaction_filters(client, sample_data):
    html = client.get("/transactions/?q=esselunga").get_data(as_text=True)
    assert "Spesa" in html and "Affitto" not in html

    html = client.get("/transactions/?type=income&month=2026-05").get_data(as_text=True)
    assert "1 transazioni trovate" in html

    html = client.get("/transactions/?category=Nope").get_data(as_text=True)
    assert "Nessun risultato" in html


def test_api_create_and_get_transaction(client, db):
    payload = {
        "description": "Pranzo", "amount": 12.5, "date": "2026-06-15",
        "type": "expense", "category": "Svago", "tags": ["lavoro"],
    }
    response = client.post("/transactions/api", json=payload)
    assert response.status_code == 201, response.get_json()
    created = response.get_json()
    assert created["description"] == "Pranzo" and created["tags"] == ["lavoro"]

    fetched = client.get(f"/transactions/api/{created['id']}").get_json()
    assert fetched["amount"] == 12.5
    assert Transaction.query.count() == 1


def test_api_rejects_invalid_type(client, db):
    response = client.post("/transactions/api", json={
        "description": "X", "amount": 1, "date": "2026-06-15", "type": "gift",
    })
    assert response.status_code == 422
