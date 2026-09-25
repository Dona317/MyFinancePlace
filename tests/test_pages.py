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
    "/forecast/",
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
    "/transactions/duplicates", "/settings/ai", "/settings/", "/transactions/new", "/forecast/",
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
    assert 'aria-controls="sidebar"' in html and "mfp-sidebar-hidden" in html  # hide the whole column, remembered
    assert 'class="btn btn-ghost btn-icon sidebar-toggle-btn"' in html and 'style="display:none;"' not in html.split("sidebar-toggle-btn")[1][:40]
    # every link keeps its label in a span, so the icons-only mode can hide it and show it as a tooltip
    assert len(re.findall(r'class="nav-item', html)) == len(re.findall(r'<span class="nav-label">', html)) - len(sections) - 1


def test_theme_switch_in_topbar(client, app):
    html = client.get("/transactions/").get_data(as_text=True)
    topbar = html.split('class="topbar-actions"')[1]
    switch = re.search(r'<div class="theme-switch" role="group" aria-label="Tema">(.*?)</div>', topbar, re.S)
    assert switch, "light/dark switch missing from the top right"
    choices = re.findall(r'data-theme-choice="(\w+)" aria-pressed="false"', switch.group(1))
    assert choices == ["light", "dark"] and "Chiara" in switch.group(1) and "Scura" in switch.group(1)
    # the theme is applied before paint: the saved choice, else the system preference
    head = html.split("</head>")[0]
    assert "mfp-theme" in head and "prefers-color-scheme: dark" in head
    assert 'id="theme-toggle"' not in html


def test_settings_button_next_to_theme_switch(client, app):
    html = client.get("/transactions/").get_data(as_text=True)
    after_switch = html.split('class="topbar-actions"')[1].split('class="theme-switch"')[1]
    button = re.search(r'<a href="(/settings/)" class="btn btn-ghost btn-icon topbar-settings"(.*?)>', after_switch, re.S)
    assert button and 'aria-label="Impostazioni"' in button.group(2) and "aria-current" not in button.group(2)
    # highlighted while on the settings pages
    assert 'aria-current="page"' in client.get("/settings/").get_data(as_text=True).split("topbar-settings")[1][:300]
