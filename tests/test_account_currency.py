"""Account balances in the account's own currency: the bank's amount when entered, else the day's exchange rate."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.transaction import Transaction
from app.services import accounts, backup, currency, wealth
from tests.conftest import make_tx

DAY = date(2026, 6, 1)


@pytest.fixture()
def setup(db):
    currency.save_rate("USD", DAY, Decimal("0.8"))  # 1 USD = 0.80 €
    eur = Account(name="Conto", currency="EUR", opening_balance=Decimal("1000"))
    usd = Account(name="Conto USD", currency="USD", opening_balance=Decimal("500"))
    db.session.add_all([eur, usd])
    db.session.commit()
    return eur, usd


def test_foreign_expense_uses_the_rate_until_the_bank_amount_is_entered(db, setup):
    eur, _usd = setup
    tx = make_tx(date=DAY, amount=100, currency="USD", account_id=eur.id)
    db.session.add(tx)
    db.session.commit()
    assert accounts.balance(eur) == 920.0 and accounts.estimated(eur) == 1  # 100 USD × 0.80
    tx.account_amount = Decimal("82.50")  # what the card statement shows
    db.session.commit()
    assert accounts.balance(eur) == 917.5 and accounts.estimated(eur) == 0
    assert accounts.balance(eur, on=date(2026, 5, 31)) == 1000.0


def test_transfer_between_currencies(db, setup):
    eur, usd = setup
    tx = make_tx(date=DAY, amount=400, currency="EUR", type="transfer", account_id=eur.id, counter_account_id=usd.id)
    db.session.add_all([tx, make_tx(date=DAY, amount=20, currency="USD", account_id=usd.id)])
    db.session.commit()
    assert accounts.balance(eur) == 600.0
    assert accounts.balance(usd) == 980.0  # 500 + 400 € = 500 $ − 20 $
    assert accounts.estimated(usd) == 1
    tx.counter_amount = Decimal("495")
    db.session.commit()
    assert accounts.balance(usd) == 975.0 and accounts.estimated(usd) == 0
    assert accounts.amount_in(tx, eur) == Decimal("400")


def test_totals_in_base_currency(client, db, setup):
    eur, usd = setup
    db.session.add(make_tx(date=DAY, amount=10, currency="USD", account_id=usd.id))
    db.session.commit()
    assert accounts.opening_total() == 1400.0  # 1000 € + 500 $ × 0.80
    assert wealth.cash_balance() == 1400.0 - 8.0
    rows = {r["account"].name: r for r in accounts.summary()}
    assert rows["Conto USD"]["balance"] == 490.0 and rows["Conto USD"]["balance_base"] == 392.0
    html = client.get("/accounts/").get_data(as_text=True)
    assert "$ 490,00" in html and "€ 1.392,00" in html


def test_detail_page_in_the_account_currency(client, db, setup):
    eur, _usd = setup
    db.session.add(make_tx(date=DAY, description="Hotel NY", amount=100, currency="USD", account_id=eur.id))
    db.session.commit()
    html = client.get(f"/accounts/{eur.id}").get_data(as_text=True)
    assert "€ 920,00" in html and "USD 100,00" in html and "al cambio" in html
    assert "contato al cambio del giorno" in html


def test_form_asks_for_the_bank_amount(client, db, setup):
    eur, usd = setup
    page = client.get("/transactions/new").get_data(as_text=True)
    assert f'value="{usd.id}" data-currency="USD"' in page and 'name="account_amount"' in page
    client.post("/transactions/new", data={"date": "2026-06-01", "amount": "-100", "currency": "USD", "description": "Hotel",
                                           "account_id": str(eur.id), "account_amount": "82,50"})
    tx = Transaction.query.one()
    assert tx.account_amount == Decimal("82.50") and tx.counter_amount is None
    assert 'value="82,50"' in client.get(f"/transactions/{tx.id}/edit").get_data(as_text=True)
    # same currency as the account: nothing to convert, the field is ignored
    client.post(f"/transactions/{tx.id}/edit", data={"date": "2026-06-01", "amount": "-100", "currency": "EUR",
                                                     "description": "Hotel", "account_id": str(eur.id), "account_amount": "5"})
    assert db.session.get(Transaction, tx.id).account_amount is None
    # a transfer to the USD account: the credited dollars
    client.post("/transactions/new", data={"date": "2026-06-01", "amount": "300", "transfer": "1", "currency": "EUR",
                                           "description": "Giro", "account_id": str(eur.id), "counter_account_id": str(usd.id),
                                           "counter_amount": "370"})
    assert Transaction.query.filter_by(description="Giro").one().counter_amount == Decimal("370.00")
    bad = client.post("/transactions/new", data={"date": "2026-06-01", "amount": "-1", "currency": "USD", "description": "x",
                                                 "account_id": str(eur.id), "account_amount": "tanti"})
    assert "Importo sul conto" in bad.get_data(as_text=True)


def test_api_fields(client, db, setup):
    eur, _usd = setup
    body = {"date": "2026-06-01", "description": "Hotel", "amount": 100, "currency": "USD", "type": "expense",
            "account_id": eur.id, "account_amount": 82.5}
    created = client.post("/transactions/api", json=body).get_json()
    assert created["account_id"] == eur.id and created["account_amount"] == 82.5
    update = {k: v for k, v in body.items() if k not in ("account_id", "account_amount")} | {"description": "Hotel NY"}
    updated = client.put(f"/transactions/api/{created['id']}", json=update).get_json()
    assert updated["account_id"] == eur.id and updated["account_amount"] == 82.5  # left out = kept
    assert client.post("/transactions/api", json=body | {"account_id": 999}).status_code == 422


def test_backup_without_the_new_columns(db, setup):
    eur, _usd = setup
    db.session.add(make_tx(date=DAY, amount=100, currency="USD", account_id=eur.id, account_amount=Decimal("82.5")))
    db.session.commit()
    data = backup.export_data()
    for row in data["tables"]["transactions"]:  # a backup made before these columns existed
        row.pop("account_amount"), row.pop("counter_amount")
    backup.restore(data, {})
    assert Transaction.query.one().account_amount is None
    assert accounts.balance(db.session.get(Account, eur.id)) == 920.0
