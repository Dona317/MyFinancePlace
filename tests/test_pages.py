import re

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


@pytest.mark.parametrize("url", [
    "/dashboard", "/transactions/", "/transactions/?category=Nope",
    "/accounting/income-statement", "/accounting/cash-flow", "/lifestyle/", "/export/",
    "/transactions/duplicates", "/settings/ai", "/settings/", "/transactions/new",
])
def test_pages_have_balanced_divs(client, sample_data, url):
    """A stray </div> closes the page container early and breaks the layout (browsers hide it)."""
    html = client.get(url).get_data(as_text=True)
    assert len(re.findall(r"<div\b", html)) == len(re.findall(r"</div>", html))


def test_sidebar_sections_are_collapsible(client, app):
    html = client.get("/transactions/").get_data(as_text=True)
    sections = re.findall(r'<div class="nav-section" data-section="(\w+)">', html)
    assert sections == ["panoramica", "contabilita", "stiledivita", "gestione", "strumenti"]
    for key in sections:
        # each title is a button controlling its own group of links
        assert f'aria-controls="nav-{key}"' in html and f'<div class="nav-section-items" id="nav-{key}">' in html
    assert 'id="sidebar-mini-toggle"' in html  # icons-only mode
    assert 'class="btn btn-ghost btn-icon sidebar-toggle-btn"' in html and 'style="display:none;"' not in html.split("sidebar-toggle-btn")[1][:40]
    # every link keeps its label in a span, so the icons-only mode can hide it and show it as a tooltip
    assert len(re.findall(r'class="nav-item', html)) == len(re.findall(r'<span class="nav-label">', html)) - len(sections) - 1
