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


DEPOSITS = ("﻿" + HEADER + "\n".join([
    "08.10.2026;08.10.2026;VERSAMENTO CONTANTI ATM 1234;Versamento;300,00",
    "09.10.2026;09.10.2026;Bonifico da Mario;Bonifico;80,00",
]) + "\n").encode()


def test_deposits():
    assert cash.is_deposit("VERSAMENTO CONTANTI ATM 1234")
    assert cash.is_deposit("Vers. contanti", None) and cash.is_deposit("Accredito", "cash deposit at ATM")
    assert not cash.is_deposit("Versamento affitto") and not cash.is_deposit("PRELIEVO BANCOMAT")


def test_import_takes_cash_paid_in_from_the_wallet(client, db):
    bank = Account(name="Banca", kind="current", opening_balance=Decimal(1000))
    db.session.add(bank)
    db.session.commit()
    html = client.post("/export/bank", data={"file": (io.BytesIO(DEPOSITS), "estratto.csv"), "bank": "auto"},
                       content_type="multipart/form-data").get_data(as_text=True)
    rows = sorted(set(re.findall(r'name="include" value="(\d+)"', html)), key=int)
    client.post("/export/bank/confirm", data=form_data(html, "preview-form", include=rows, account_id=str(bank.id)))
    wallet = cash.wallet()
    paid_in = Transaction.query.filter_by(account_id=wallet.id).one()
    assert (paid_in.type, paid_in.counter_account_id, float(paid_in.amount)) == ("transfer", bank.id, 300.0)
    assert accounts.balance(bank) == 1380 and accounts.balance(wallet) == -300
    assert Transaction.query.filter_by(description="Bonifico da Mario").one().type == "income"


def test_realign_turns_the_register_into_giroconti(db):
    bank = Account(name="Banca", kind="current")
    db.session.add(bank)
    db.session.commit()
    out = make_tx(account_id=bank.id, description="PRELIEVO BANCOMAT ATM", amount=100, type="expense", category="Altro")
    paid_in = make_tx(account_id=bank.id, description="Versamento contanti sportello", amount=40, type="income",
                      category="Altre entrate")
    salary = make_tx(account_id=bank.id, description="Stipendio", amount=1500, type="income")
    db.session.add_all([out, paid_in, salary])
    db.session.commit()
    assert cash.realign() == 2
    wallet = cash.wallet()
    assert (out.type, out.account_id, out.counter_account_id, out.category) == ("transfer", bank.id, wallet.id, "Giroconto")
    assert (paid_in.type, paid_in.account_id, paid_in.counter_account_id) == ("transfer", wallet.id, bank.id)
    assert salary.type == "income" and cash.realign() == 0
    assert accounts.balance(wallet) == 60


def test_realign_without_bank_accounts(db):
    assert cash.realign() == 0


def test_the_register_review_suggests_the_giroconto_for_cash_paid_in(db):
    from app.services import review
    bank = Account(name="Banca", kind="current")
    db.session.add(bank)
    db.session.commit()
    tx = make_tx(account_id=bank.id, description="VERSAMENTO CONTANTI", amount=40, type="income")
    db.session.add(tx)
    db.session.commit()
    findings, _note = review.review([tx], [])
    assert [(f.kind, f.title) for f in findings] == [("cash", "Versamento di contanti: è un giroconto da Contanti")]
    assert review.apply(tx, "cash", "") is True
    assert (tx.type, tx.account_id, tx.counter_account_id) == ("transfer", cash.wallet().id, bank.id)


def test_the_cash_page_shows_how_much_was_written_down(client, db):
    wallet = cash.wallet(create=True)
    year = date.today().year
    db.session.add_all([make_tx(account_id=wallet.id, amount=30, date=date(year, 1, 5), category="Alimentari"),
                        make_tx(account_id=wallet.id, amount=10, date=date(year, 1, 6), category=cash.UNRECORDED),
                        make_tx(account_id=wallet.id, amount=99, date=date(year - 1, 5, 1), category=cash.UNRECORDED)])
    db.session.commit()
    assert cash.tracking(wallet, year) == {"year": year, "recorded": 30.0, "unrecorded": 10.0, "share": 75.0}
    assert cash.tracking(wallet, year + 1)["share"] is None
    html = client.get(f"/accounts/{wallet.id}").get_data(as_text=True)
    assert "Spese in contanti tracciate" in html and "<strong>75%</strong>" in html and "Come funzionano i contanti" in html
    assert "mfp-cash-intro" in html


def test_unrecorded_cash_is_a_line_of_its_own(client, db):
    from app.services import analytics
    for category, amount in (("Alimentari", 60), ("Casa", 40), (cash.UNRECORDED, 25)):
        db.session.add(make_tx(category=category, amount=amount, date=date(2026, 3, 1)))
    db.session.commit()
    lines = analytics.category_breakdown(date(2026, 1, 1), date(2027, 1, 1))
    assert [(line["category"], line["share"], line.get("apart", False)) for line in lines] == [
        ("Alimentari", 60.0, False), ("Casa", 40.0, False), (cash.UNRECORDED, 20.0, True)]  # its share of all 125
    html = client.get("/dashboard?year=2026").get_data(as_text=True)
    assert "A parte: «Spese non annotate»" in html
    assert "a parte</span>" in client.get("/accounting/income-statement?year=2026").get_data(as_text=True)
