"""F81: Entrate, Uscite and Ricorrenti are pages of Transazioni — tabs of it (the three cards on top that opened them
went on 16 Nov 2026); «Abbonamenti» became «Ricorrenti», then «Entrate e uscite ricorrenti» (22 Nov 2026)."""
from datetime import date

from tests.conftest import make_tx


def test_the_register_starts_from_the_tabs(client, db):
    """16 Nov: the three cards on top repeated the tabs with the same names and are gone."""
    db.session.add(make_tx(date=date.today().replace(day=1), description="Stipendio", amount=2000, type="income"))
    db.session.commit()
    page = client.get("/transactions/").get_data(as_text=True)
    assert "section-cards" not in page and "Apri Entrate" not in page and 'name="cards"' not in page
    tabs = page[page.index('class="section-tabs'):][:1500]  # the tabs of Transazioni, not entries of the side menu
    for href in ('href="/reports/income"', 'href="/reports/spending"', 'href="/subscriptions/"'):
        assert href in tabs
    assert "Entrate e uscite ricorrenti" in tabs and 'class="nav-item nav-sub' not in page


def test_the_pages_sit_under_transazioni(client, db):
    for url, title in (("/reports/income", "Entrate"), ("/reports/spending", "Uscite"), ("/subscriptions/", "Entrate e uscite ricorrenti")):
        page = client.get(url).get_data(as_text=True)
        crumbs = page[page.index('class="breadcrumb'):][:600]
        assert 'href="/transactions/"' in crumbs and title in crumbs, url
        tabs = page[page.index('class="section-tabs'):][:1500]
        assert 'class="report-tab active" aria-current="page"' in tabs and title in tabs, url
