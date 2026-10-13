"""F22: the cash wallet — ATM withdrawals as giroconti, counting the wallet, a wallet below zero."""
import io
import re
from datetime import date
from decimal import Decimal

from app.models.account import Account
from app.models.transaction import Transaction
from app.services import accounts, cash, data_health
from tests.conftest import make_tx
from tests.form_helper import form_data

HEADER = "Data Registrazione;Data valuta;Descrizione;Causale;Importo (EUR)\n"
STATEMENT = ("﻿" + HEADER + "\n".join([
    "05.10.2026;05.10.2026;PRELIEVO BANCOMAT ATM 1234 ROMA;Prelievo;-100,00",
    "06.10.2026;06.10.2026;PAGAMENTO POS ATM MILANO;Pagamento POS;-2,20",   # the Milan transit company
    "07.10.2026;07.10.2026;Cash withdrawal at BANCOMAT ROMA;;-50,00",
]) + "\n").encode()


def test_withdrawals():
    assert cash.is_withdrawal("PRELIEVO BANCOMAT ATM 1234")
    assert cash.is_withdrawal("Cash withdrawal at BANCOMAT ROMA")
    assert cash.is_withdrawal("Pagamento", "prelevamento contanti sportello")
    assert not cash.is_withdrawal("PAGAMENTO POS ATM MILANO")


def test_wallet_made_once(db):
    assert cash.wallet() is None
    db.session.add(Account(name="Contanti", kind="current"))  # the name taken by another kind of account
    db.session.commit()
    made = cash.wallet(create=True)
    assert made.kind == "cash" and made.name == "Contanti 2" and cash.wallet(create=True).id == made.id


def test_import_moves_withdrawals_to_the_wallet(client, db):
    bank = Account(name="Banca", kind="current", opening_balance=Decimal(1000))
    db.session.add(bank)
    db.session.commit()
    html = client.post("/export/bank", data={"file": (io.BytesIO(STATEMENT), "estratto.csv"), "bank": "auto"},
                       content_type="multipart/form-data").get_data(as_text=True)
    rows = sorted(set(re.findall(r'name="include" value="(\d+)"', html)), key=int)
    client.post("/export/bank/confirm", data=form_data(html, "preview-form", include=rows, account_id=str(bank.id)))
    wallet = cash.wallet()
    assert wallet is not None
    moved = Transaction.query.filter_by(counter_account_id=wallet.id).all()
    assert sorted(float(t.amount) for t in moved) == [50.0, 100.0] and all(t.type == "transfer" for t in moved)
    assert accounts.balance(wallet) == 150 and accounts.balance(bank) == 1000 - 152.2
    assert Transaction.query.filter_by(description="PAGAMENTO POS ATM MILANO").one().type == "expense"


def test_count(db):
    wallet = cash.wallet(create=True)
    db.session.add(make_tx(date=date(2026, 10, 1), description="Prelievo", amount=200, type="transfer",
                           counter_account_id=wallet.id, category="Giroconto"))
    db.session.add(make_tx(date=date(2026, 10, 2), description="Mercato", amount=30, account_id=wallet.id))
    db.session.commit()
    spent = cash.count(wallet, Decimal(85), date(2026, 10, 10))
    db.session.commit()
    assert spent.type == "expense" and spent.amount == 85 and spent.category == cash.UNRECORDED
    assert accounts.balance(wallet) == 85 and wallet.reconciled_on == date(2026, 10, 10)
    found = cash.count(wallet, Decimal(100), date(2026, 10, 11))
    assert found.type == "income" and found.amount == 15 and found.category == cash.FOUND
    assert cash.count(wallet, Decimal(100), date(2026, 10, 12)) is None  # it adds up
    bank = Account(name="Banca", kind="current")
    db.session.add(bank)
    for bad in ((bank, Decimal(1)), (wallet, Decimal(-1)), (wallet, None)):
        try:
            cash.count(*bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_page_and_negative_wallet(client, db):
    wallet = cash.wallet(create=True)
    db.session.add(make_tx(date=date(2026, 10, 2), description="Mercato", amount=30, account_id=wallet.id))
    db.session.commit()
    assert cash.negative() == [(wallet, -30.0)]
    with client.application.test_request_context():
        check = next(c for c in data_health.run() if c.key == "cash")
    assert check.count == 1
    page = client.get(f"/accounts/{wallet.id}").get_data(as_text=True)
    assert "Conta i contanti" in page
    assert "non può essere negativo" in client.post(f"/accounts/{wallet.id}/count", data={"counted": "-5"},
                                          follow_redirects=True).get_data(as_text=True)
    page = client.post(f"/accounts/{wallet.id}/count", data={"counted": "20"}, follow_redirects=True).get_data(as_text=True)
    assert "Contanti trovati" in page and accounts.balance(wallet) == 20
    page = client.post(f"/accounts/{wallet.id}/count", data={"counted": "20"}, follow_redirects=True).get_data(as_text=True)
    assert "Tutto torna" in page and "Ultima conta" in page and cash.negative() == []
