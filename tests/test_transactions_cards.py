"""F81: Entrate, Uscite and Ricorrenti are pages of Transazioni — three cards on top of the list open them, and in the
menu they sit under Transazioni; «Abbonamenti» is now «Ricorrenti»."""
from datetime import date

from app.services import periods
from tests.conftest import make_tx


def test_three_cards_open_the_pages(client, db):
    this_month = date.today().replace(day=1)
    db.session.add_all([
        make_tx(date=this_month, description="Stipendio", amount=2000, type="income", category="Stipendio"),
        make_tx(date=this_month, description="Spesa", amount=150, category="Alimentari"),
        make_tx(date=periods.add_months(this_month, -1), description="Vecchia", amount=999, category="Altro"),
        make_tx(date=this_month, description="Netflix", amount=12, category="Abbonamenti", is_recurring=True,
                recurrence="monthly"),
        make_tx(date=this_month, description="Palestra", amount=120, category="Sport", is_recurring=True,
                recurrence="yearly"),
    ])
    db.session.commit()
    page = client.get("/transactions/").get_data(as_text=True)
    cards = page[page.index('section-cards'):page.index('section-cards') + 3000]
    for href in ('href="/reports/income"', 'href="/reports/spending"', 'href="/subscriptions/"'):
        assert href in cards
    assert 'data-amount="2000.0"' in cards and 'data-amount="-282.0"' in cards  # 150 + 12 + 120 of this month
    assert 'data-amount="-22.0"' in cards and "2 serie ricorrenti" in cards  # 12 a month + 120 a year / 12
    tabs = page[page.index('class="section-tabs'):][:1500]  # the tabs of Transazioni, not entries of the side menu
    assert 'href="/subscriptions/"' in tabs and 'Ricorrenti' in tabs and 'class="nav-item nav-sub' not in page


def test_the_pages_sit_under_transazioni(client, db):
    for url, title in (("/reports/income", "Entrate"), ("/reports/spending", "Uscite"), ("/subscriptions/", "Ricorrenti")):
        page = client.get(url).get_data(as_text=True)
        crumbs = page[page.index('class="breadcrumb'):][:600]
        assert 'href="/transactions/"' in crumbs and title in crumbs, url
        tabs = page[page.index('class="section-tabs'):][:1500]
        assert 'class="report-tab active" aria-current="page"' in tabs and title in tabs, url
