"""F30: Contanti (in several currencies) and Debiti are in every archive, listed once used, never deleted."""
from datetime import date

import pytest

from app.models.account import Account
from app.services import accounts, wealth
from tests.conftest import make_tx


@pytest.fixture()
def fixed_on(app):
    app.config["FIXED_ACCOUNTS"] = True
    yield
    app.config.pop("FIXED_ACCOUNTS", None)


def _add(db, **values):
    tx = make_tx(**values)
    db.session.add(tx)
    db.session.commit()
    return tx


def test_the_two_accounts_are_made_once_and_wait_until_used(client, db, fixed_on):
    html = client.get("/accounts/").get_data(as_text=True)
    cash, debt = accounts.fixed("cash"), accounts.fixed("debt")
    assert (cash.name, cash.kind, debt.name, debt.kind) == ("Contanti", "cash", "Debiti", "debt")
    assert "Pronti, compaiono qui appena li usi" in html and 'class="cell-title"' not in html
    client.get("/accounts/")
    assert Account.query.count() == 2  # not made again
    _add(db, account_id=cash.id, amount=12)
    html = client.get("/accounts/").get_data(as_text=True)
    assert 'class="cell-title"' in html and "Debiti</a>" in html  # Contanti listed, Debiti still waiting


def test_an_earlier_cash_account_becomes_the_fixed_one(db):
    wallet = Account(name="Portafoglio", kind="cash", currency="EUR")
    db.session.add(wallet)
    db.session.commit()
    assert accounts.ensure_fixed() is True
    assert accounts.fixed("cash").id == wallet.id and accounts.fixed("cash").name == "Portafoglio"
    assert accounts.ensure_fixed() is False


def test_fixed_accounts_keep_name_and_kind_and_are_not_deleted(client, db):
    accounts.ensure_fixed()
    cash = accounts.fixed("cash")
    form = client.get(f"/accounts/{cash.id}/edit").get_data(as_text=True)
    assert "Conto fisso" in form and 'name="name"' not in form and form.count('name="foreign_code"') == 3
    client.post(f"/accounts/{cash.id}/edit", data={"name": "Altro", "kind": "current", "currency": "EUR",
                                                    "foreign_code": ["CHF", "USD", "CHF"], "foreign_amount": ["50", "", "7"]})
    refused = client.post(f"/accounts/{cash.id}/delete", follow_redirects=True).get_data(as_text=True)
    assert "non si elimina" in refused
    db.session.refresh(cash)
    assert (cash.name, cash.kind, cash.active) == ("Contanti", "cash", True)
    assert cash.opening_foreign == {"CHF": "7"}  # a currency once (the last), an empty amount left out
    bad = client.post(f"/accounts/{cash.id}/edit", data={"currency": "EUR", "foreign_code": ["CHF"], "foreign_amount": ["x"]})
    assert "Importo non valido per CHF" in bad.get_data(as_text=True)


def test_cash_in_several_currencies(client, db, monkeypatch):
    accounts.ensure_fixed()
    cash = accounts.fixed("cash")
    cash.opening_balance, cash.opening_foreign = 100, {"CHF": "50", "XXX": "3", "USD": "0"}
    db.session.commit()
    _add(db, account_id=cash.id, amount=20, currency="CHF", date=date(2026, 6, 2))
    _add(db, account_id=cash.id, amount=30, date=date(2026, 6, 3))
    assert accounts.by_currency(cash) == {"CHF": 30.0, "EUR": 70.0}
    monkeypatch.setattr(accounts.currency, "to_base", lambda value, code, day, target=None: value * 2 if code == "CHF" else value)
    assert accounts.balance(cash) == 70 + 50 * 2 - 20 * 2
    html = client.get(f"/accounts/{cash.id}").get_data(as_text=True)
    assert "Contanti per valuta" in html and "CHF 30,00" in html


def test_what_goes_on_debiti_is_owed_not_paid_with_cash(db):
    accounts.ensure_fixed()
    debt, bank = accounts.fixed("debt"), Account(name="Fineco", kind="current", currency="EUR")
    db.session.add(bank)
    db.session.commit()
    _add(db, account_id=bank.id, amount=1000, type="income", date=date(2026, 1, 5))
    _add(db, account_id=debt.id, amount=300, date=date(2026, 2, 1))  # bought now, paid later
    assert wealth.cash_balance() == 1000 and accounts.owed() == 300
    sheet = wealth.balance_sheet()
    assert sheet["current_liabilities"]["Debiti vari"] == 300
    # 100 paid back from the bank: less cash, less owed
    _add(db, account_id=bank.id, counter_account_id=debt.id, amount=100, type="transfer", date=date(2026, 3, 1))
    assert wealth.cash_balance() == 900 and accounts.owed() == 200
    # a loan received on the bank through Debiti: more cash, more owed
    _add(db, account_id=debt.id, counter_account_id=bank.id, amount=500, type="transfer", date=date(2026, 3, 2))
    assert wealth.cash_balance() == 1400 and accounts.owed() == 700
