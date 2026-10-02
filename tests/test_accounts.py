"""Accounts and cards: balance per account, transfers between them, reconciliation, import on an account."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.transaction import Transaction
from app.services import accounts, wealth
from tests.conftest import make_tx
from tests.form_helper import assert_divs_balanced


@pytest.fixture()
def two_accounts(db):
    fineco = Account(name="Fineco", kind="current", opening_balance=Decimal("1000"))
    card = Account(name="Carta", kind="prepaid", opening_balance=Decimal("0"))
    db.session.add_all([fineco, card])
    db.session.commit()
    db.session.add_all([
        make_tx(date=date(2026, 6, 1), description="Stipendio", amount=2000, type="income", account_id=fineco.id),
        make_tx(date=date(2026, 6, 3), description="Affitto", amount=700, account_id=fineco.id),
        make_tx(date=date(2026, 6, 5), description="Ricarica carta", amount=100, type="transfer",
                account_id=fineco.id, counter_account_id=card.id),
        make_tx(date=date(2026, 6, 8), description="Amazon", amount=30, account_id=card.id),
        make_tx(date=date(2026, 6, 9), description="Contanti", amount=20),  # no account
    ])
    db.session.commit()
    return fineco, card


def test_balances_follow_transfers(two_accounts):
    fineco, card = two_accounts
    assert accounts.balance(fineco) == 1000 + 2000 - 700 - 100
    assert accounts.balance(card) == 100 - 30
    assert accounts.balance(fineco, date(2026, 6, 2)) == 3000
    assert accounts.unassigned_count() == 1


def test_account_opening_balances_count_as_cash(two_accounts):
    # 1000 opening + 2000 − 700 − 30 − 20 (the transfer moves money between own accounts)
    assert wealth.cash_balance() == 2250


def test_reconciliation(client, db, two_accounts):
    fineco, _ = two_accounts
    html = client.post(f"/accounts/{fineco.id}/reconcile", data={"on": "2026-06-04", "statement_balance": "2.300,00"}).get_data(as_text=True)
    assert "Tutto torna" in html
    assert db.session.get(Account, fineco.id).reconciled_on == date(2026, 6, 4)
    html = client.post(f"/accounts/{fineco.id}/reconcile", data={"on": "2026-06-30", "statement_balance": "2250"}).get_data(as_text=True)
    assert "differenza" in html and "€ 50,00" in html


def test_pages(client, two_accounts):
    fineco, _ = two_accounts
    for url in ("/accounts/", "/accounts/new", f"/accounts/{fineco.id}", f"/accounts/{fineco.id}/edit"):
        response = client.get(url)
        assert response.status_code == 200, url
        assert_divs_balanced(response.get_data(as_text=True))
    html = client.get("/accounts/").get_data(as_text=True)
    assert "€ 2.200,00" in html and "€ 70,00" in html


def test_crud_and_validation(client, db):
    client.post("/accounts/new", data={"name": "Revolut", "kind": "current", "opening_balance": "50", "active": "on"})
    account = Account.query.one()
    assert account.opening_balance == 50 and account.active
    response = client.post("/accounts/new", data={"name": "Revolut", "kind": "current"})
    assert "Esiste già un conto" in response.get_data(as_text=True)
    db.session.add(make_tx(account_id=account.id))
    db.session.commit()
    client.post(f"/accounts/{account.id}/delete")
    assert Account.query.count() == 0 and Transaction.query.one().account_id is None


def test_filter_and_bulk_assign(client, two_accounts):
    fineco, card = two_accounts
    html = client.get(f"/transactions/?account={card.id}").get_data(as_text=True)
    assert "Amazon" in html and "Ricarica carta" in html and "Affitto" not in html
    html = client.get("/transactions/?account=none").get_data(as_text=True)
    assert "Contanti" in html and "Amazon" not in html
    loose = Transaction.query.filter_by(description="Contanti").one()
    client.post("/transactions/assign-account", data={"ids": [str(loose.id)], "account_id": str(card.id)})
    assert Transaction.query.filter_by(description="Contanti").one().account_id == card.id


def test_transaction_form_accounts(client, db, two_accounts):
    fineco, card = two_accounts
    base = {"type": "transfer", "date": "2026-06-10", "amount": "50", "description": "Giroconto"}
    response = client.post("/transactions/new", data=base | {"account_id": str(fineco.id), "counter_account_id": str(fineco.id)})
    assert "deve essere diverso" in response.get_data(as_text=True)
    client.post("/transactions/new", data=base | {"account_id": str(fineco.id), "counter_account_id": str(card.id)})
    tx = Transaction.query.filter_by(description="Giroconto").one()
    assert (tx.account_id, tx.counter_account_id) == (fineco.id, card.id)
    # an expense never keeps a destination account
    client.post(f"/transactions/{tx.id}/edit", data=base | {"type": "expense", "account_id": str(fineco.id),
                                                          "counter_account_id": str(card.id)})
    assert db.session.get(Transaction, tx.id).counter_account_id is None


def test_bank_import_on_an_account(client, db):
    import io
    import re

    from tests.form_helper import form_data
    from tests.statements import fineco_xlsx

    fineco = Account(name="Fineco", kind="current")
    db.session.add(fineco)
    db.session.commit()
    html = client.post("/export/bank", data={"file": (io.BytesIO(fineco_xlsx()), "movimenti.xlsx"), "bank": "auto"},
                       content_type="multipart/form-data").get_data(as_text=True)
    assert re.search(rf'<option value="{fineco.id}" selected', html)  # suggested from the bank's name
    rows = sorted(set(re.findall(r'name="include" value="(\d+)"', html)), key=int)
    client.post("/export/bank/confirm", data=form_data(html, "preview-form", include=rows))
    imported = Transaction.query.all()
    assert imported and all(t.account_id == fineco.id or t.counter_account_id == fineco.id for t in imported)
    giroconto = Transaction.query.filter(Transaction.description.ilike("%giroconto%")).first()
    # money leaving towards the savings account: it leaves Fineco
    assert giroconto.type == "transfer" and giroconto.account_id == fineco.id and giroconto.counter_account_id is None
