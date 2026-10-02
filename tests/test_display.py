"""Settings → Visualizzazione applied everywhere: base currency, number format, date format."""
from datetime import date
from decimal import Decimal

from app.models.transaction import Transaction
from app.routes.settings import DEFAULT_SETTINGS
from app.services import currency
from tests.conftest import make_tx


def save_display(client, **choices):
    form = {k: "on" for k, v in DEFAULT_SETTINGS.items() if v is True}
    form.update({"currency": "EUR", "locale": "it-IT", "date_format": "DD/MM/YYYY"} | choices)
    return client.post("/settings/save", data=form, follow_redirects=True)


def test_number_and_date_formats(client, db):
    db.session.add(make_tx(date=date(2026, 6, 3), description="Affitto", amount=1234.5))
    db.session.commit()
    html = client.get("/transactions/").get_data(as_text=True)
    assert "-€ 1.234,50" in html and "03/06/2026" in html
    save_display(client, locale="en-GB", date_format="YYYY-MM-DD")
    html = client.get("/transactions/").get_data(as_text=True)
    assert "-€ 1,234.50" in html and "2026-06-03" in html
    assert 'data-locale="en-GB"' in html


def test_changing_the_base_currency_converts_totals(client, db):
    currency.save_rate("USD", date(2026, 1, 1), Decimal("0.8"))  # 1 USD = 0.80 EUR
    db.session.add(make_tx(date=date(2026, 6, 3), amount=80, currency="EUR"))
    db.session.commit()
    response = save_display(client, currency="USD")
    assert "Totali ora in USD" in response.get_data(as_text=True)
    assert Transaction.query.one().amount_base == 100  # 80 EUR = 100 USD
    assert "$ 100.00" not in client.get("/transactions/").get_data(as_text=True)  # still Italian numbers
    assert "≈ -$ 100,00" in client.get("/transactions/").get_data(as_text=True)
    save_display(client, currency="EUR")
    assert Transaction.query.one().amount_base == 80


def test_preview_on_settings_page(client, db):
    save_display(client, locale="de-CH", date_format="MM/DD/YYYY")
    html = client.get("/settings/").get_data(as_text=True)
    assert "€ 1&#39;234.56" in html and "05/25/2026" in html
