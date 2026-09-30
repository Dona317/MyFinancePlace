import re

import pytest

from app.models.transaction import Transaction
from tests.form_helper import assert_divs_balanced


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
    assert_divs_balanced(client.get(url).get_data(as_text=True))


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


def test_theme_toggle_in_topbar(client, app):
    html = client.get("/transactions/").get_data(as_text=True)
    topbar = html.split('class="topbar-actions"')[1]
    toggle = re.search(r'<button type="button" id="theme-toggle"(.*?)</button>', topbar, re.S)
    assert toggle, "light/dark toggle missing from the top right"
    # a single icon: the sun in light mode, the moon in dark mode (CSS shows one of the two)
    assert "bi-sun-fill theme-icon-light" in toggle.group(1) and "bi-moon-stars-fill theme-icon-dark" in toggle.group(1)
    assert 'aria-label="Passa alla modalità scura"' in toggle.group(1)
    assert "data-theme-choice" not in html and "theme-switch" not in html
    # the theme is applied before paint: the saved choice, else the system preference
    head = html.split("</head>")[0]
    assert "mfp-theme" in head and "prefers-color-scheme: dark" in head


def test_settings_button_next_to_theme_switch(client, app):
    html = client.get("/transactions/").get_data(as_text=True)
    after_switch = html.split('class="topbar-actions"')[1].split('id="theme-toggle"')[1]
    button = re.search(r'<a href="(/settings/)" class="btn btn-ghost btn-icon topbar-settings"(.*?)>', after_switch, re.S)
    assert button and 'aria-label="Impostazioni"' in button.group(2) and "aria-current" not in button.group(2)
    # highlighted while on the settings pages
    assert 'aria-current="page"' in client.get("/settings/").get_data(as_text=True).split("topbar-settings")[1][:300]


def test_theme_tokens_are_well_formed():
    """A missing ';' in theme.css silently drops the next token (e.g. a chart colour turns black)."""
    from pathlib import Path

    css = (Path(__file__).parents[1] / "app/static/css/theme.css").read_text()
    for block in re.findall(r"\{(.*?)\}", css, re.S):
        body = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
        for declaration in filter(None, (d.strip() for d in body.split(";"))):
            assert declaration.count(":") == 1 and declaration.startswith("--"), declaration


def test_static_files_carry_a_version(client, app):
    """CSS and JS links change when the file changes, so browsers don't keep showing the old look."""
    html = client.get("/transactions/").get_data(as_text=True)
    for name in ("css/theme.css", "css/main.css", "js/main.js", "js/charts.js"):
        assert re.search(rf'/static/{name}\?v=\d+"', html), name
