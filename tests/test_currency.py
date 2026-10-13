"""Several currencies: each transaction keeps its amount and currency; totals use its value in euro."""
from datetime import date
from decimal import Decimal

from app.models.currency import ExchangeRate
from app.models.transaction import Transaction
from app.services import analytics, currency
from tests.conftest import make_tx

ECB_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube><Cube time="2026-06-02"><Cube currency="USD" rate="1.25"/><Cube currency="GBP" rate="0.8"/><Cube currency="XXX" rate="2"/></Cube></Cube>
</gesmes:Envelope>"""


def test_euro_value_is_filled_on_save(db):
    db.session.add(make_tx(amount=100, currency="EUR"))
    db.session.add(make_tx(amount=100, currency="USD", date=date(2026, 6, 10)))
    db.session.commit()
    eur, usd = Transaction.query.order_by(Transaction.id).all()
    assert eur.amount_base == 100
    assert usd.amount_base == 100  # no rate yet: 1:1


def test_rates_by_date_and_recompute(db):
    db.session.add(make_tx(amount=100, currency="USD", date=date(2026, 6, 10), type="expense"))
    db.session.commit()
    currency.save_rate("USD", date(2026, 6, 1), Decimal("0.9"))
    currency.save_rate("USD", date(2026, 6, 20), Decimal("0.8"))
    currency.recompute("USD")
    assert Transaction.query.one().amount_base == Decimal("90.00")  # the latest rate on or before its date
    assert currency.rate_on("USD", date(2026, 5, 1)) == Decimal("0.9")  # before any rate: the first one
    assert currency.to_base(10, "EUR", date(2026, 1, 1)) == 10


def test_reports_add_up_euro_values(db):
    currency.save_rate("USD", date(2026, 1, 1), Decimal("0.5"))
    db.session.add_all([make_tx(amount=100, date=date(2026, 6, 1), currency="EUR"),
                        make_tx(amount=100, date=date(2026, 6, 2), currency="USD")])
    db.session.commit()
    assert analytics.totals(date(2026, 6, 1), date(2026, 7, 1))["expenses"] == 150
    assert Transaction.query.filter_by(currency="USD").one().magnitude == 50


def test_ecb_file_is_parsed_as_value_in_euro():
    rates = currency.parse_ecb(ECB_XML)
    assert (date(2026, 6, 2), "USD", Decimal("0.80000000")) in rates
    assert (date(2026, 6, 2), "GBP", Decimal("1.25000000")) in rates
    assert all(code != "XXX" for _, code, _ in rates)


def test_currencies_page(client, db):
    db.session.add(make_tx(amount=10, currency="GBP"))
    db.session.commit()
    html = client.get("/settings/currencies").get_data(as_text=True)
    assert "GBP · 1 transazioni · senza cambio!" in html
    response = client.post("/settings/currencies/rate", data={"currency": "GBP", "on": "2026-01-01", "rate": "1,15"},
                           follow_redirects=True)
    assert "Ricalcolate 1 transazioni" in response.get_data(as_text=True)
    assert Transaction.query.one().amount_base == Decimal("11.50")
    response = client.post("/settings/currencies/rate", data={"currency": "EUR", "on": "2026-01-01", "rate": "1"},
                           follow_redirects=True)
    assert "scegline una diversa dall" in response.get_data(as_text=True)
    rate = ExchangeRate.query.one()
    client.post(f"/settings/currencies/rate/{rate.id}/delete")
    assert Transaction.query.one().amount_base == 10


def test_transaction_list_shows_original_and_euro(client, db):
    currency.save_rate("USD", date(2026, 1, 1), Decimal("0.9"))
    db.session.add(make_tx(amount=100, currency="USD", description="Hotel NYC"))
    db.session.commit()
    html = client.get("/transactions/").get_data(as_text=True)
    assert "-USD 100,00" in html and "≈ -€ 90,00" in html
