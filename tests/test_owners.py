"""
Titolari e IBAN (services/owners.py): a bonifico naming a holder or the IBAN of one of the accounts is a giroconto,
even when only one of the two statements is imported; with the IBAN the import also knows the other account.
"""
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.transaction import Transaction
from app.services import accounts, owners
from tests.test_bank_transfers_pairing import _csv, _import, _preview, pair, two  # noqa: F401 - pair is a fixture

UNICREDIT_IBAN, FINECO_IBAN = "IT27X0200801600000102345678", "IT06S0301503200000012345678"


def test_iban_check_digits():
    assert owners.clean_iban("it27 x020 0801 6000 0010 2345 678") == UNICREDIT_IBAN
    assert owners.clean_iban("  ") is None
    for wrong in ("IT28X0200801600000102345678", "IBAN123", "IT27X02008016000001023456789012345678"):
        with pytest.raises(ValueError):
            owners.clean_iban(wrong)


def test_holders_need_first_and_last_name(db):
    assert owners.set_holders(["Mario  Rossi", "", "mario rossi", "Laura Bianchi"]) == ["Mario Rossi", "Laura Bianchi"]
    assert owners.holders() == ["Mario Rossi", "Laura Bianchi"]
    with pytest.raises(ValueError, match="nome e cognome"):
        owners.set_holders(["Mario"])
    with pytest.raises(ValueError):
        owners.set_holders([f"Nome Cognome{i}" for i in range(owners.MAX_HOLDERS + 1)])


def test_the_settings_page(client, pair):  # noqa: F811
    unicredit, fineco = pair
    assert "Titolari e IBAN" in client.get("/settings/").get_data(as_text=True)
    page = client.post("/settings/owners", data={"holders": "Mario Rossi\nLaura Bianchi",
                                                 f"iban-{unicredit.id}": "IT27 X020 0801 6000 0010 2345 678",
                                                 f"iban-{fineco.id}": FINECO_IBAN}, follow_redirects=True)
    assert "Titolari e IBAN salvati" in page.get_data(as_text=True)
    assert (unicredit.iban, unicredit.iban_tail, fineco.iban) == (UNICREDIT_IBAN, "5678", FINECO_IBAN)
    assert "Laura Bianchi" in client.get("/settings/owners").get_data(as_text=True)

    wrong = client.post("/settings/owners", data={"holders": "Mario Rossi", f"iban-{unicredit.id}": "IT00 1234",
                                                  f"iban-{fineco.id}": FINECO_IBAN})
    assert wrong.status_code == 400 and "non è un IBAN valido" in wrong.get_data(as_text=True)
    assert "IT00 1234" in wrong.get_data(as_text=True)  # what was typed stays in the form
    same = client.post("/settings/owners", data={f"iban-{unicredit.id}": FINECO_IBAN, f"iban-{fineco.id}": FINECO_IBAN})
    assert same.status_code == 400 and "già di un altro conto" in same.get_data(as_text=True)
    assert Account.query.get(unicredit.id).iban == UNICREDIT_IBAN  # nothing saved


def test_the_account_form_takes_the_iban(client, db):
    client.post("/accounts/new", data={"name": "Conto BPER", "kind": "current", "currency": "EUR",
                                       "iban": "IT60 X054 2811 1010 0000 0123 456"})
    assert Account.query.filter_by(name="Conto BPER").one().iban == "IT60X0542811101000000123456"


def _profile(unicredit, fineco, ibans=True):
    owners.set_holders(["Mario Rossi"])
    if ibans:
        owners.set_iban(unicredit, UNICREDIT_IBAN)
        owners.set_iban(fineco, FINECO_IBAN)
    from app.extensions import db
    db.session.commit()


SENT = _csv(f"06.03.2026;06.03.2026;Bonifico SEPA a MARIO ROSSI IBAN {FINECO_IBAN};Bonifico SEPA;-300,00",
            "07.03.2026;07.03.2026;Bonifico SEPA a ROSSI MARIO;Bonifico SEPA;-80,00",
            "08.03.2026;08.03.2026;Bonifico SEPA a IDRAULICO BIANCHI;Bonifico SEPA;-150,00",
            "09.03.2026;09.03.2026;PAGAMENTO POS ROSSI MARIO FERRAMENTA;Pagamento POS;-20,00")


def test_one_statement_is_enough_with_the_iban(client, pair, app):  # noqa: F811
    unicredit, fineco = pair
    _profile(unicredit, fineco)
    html = _preview(client, "unicredit_marzo.csv", SENT)
    assert "Giroconto con «Fineco conto risparmio»" in html
    _import(client, "unicredit_marzo.csv", SENT, unicredit)
    by_amount = {t.amount: t for t in Transaction.query}
    to_fineco, to_self, plumber, shop = (by_amount[Decimal(v)] for v in ("300.00", "80.00", "150.00", "20.00"))
    assert (to_fineco.type, to_fineco.account_id, to_fineco.counter_account_id) == ("transfer", unicredit.id, fineco.id)
    assert (to_self.type, to_self.category, to_self.counter_account_id) == ("transfer", "Giroconto", None)  # the name
    assert plumber.type == "expense" and shop.type == "expense"  # not a holder; a card payment is never a giroconto
    with app.test_request_context():
        assert accounts.balance(fineco) == 300.0

    # the other statement afterwards: joined to the transfer already complete, nothing added twice
    arriving = _csv(f"09.03.2026;09.03.2026;Bonifico da MARIO ROSSI IBAN {UNICREDIT_IBAN};Bonifico;300,00",
                    "10.03.2026;10.03.2026;Bonifico da ROSSI MARIO;Bonifico;80,00")
    assert _preview(client, "unicredit_fineco_marzo.csv", arriving).count('name="pair-') == 2
    _import(client, "unicredit_fineco_marzo.csv", arriving, fineco)
    assert Transaction.query.count() == 4
    assert {(t.account_id, t.counter_account_id) for t in Transaction.query.filter_by(type="transfer")} == {
        (unicredit.id, fineco.id)}
    with app.test_request_context():
        assert accounts.balance(fineco) == 380.0 and accounts.balance(unicredit) == 450.0


@pytest.mark.parametrize("first", ["unicredit", "fineco"])
def test_the_two_bank_sample_files_with_the_profile(client, pair, app, first):  # noqa: F811
    unicredit, fineco = pair
    unicredit.opening_balance, fineco.opening_balance = two.OPENING["unicredit"], two.OPENING["fineco"]
    _profile(unicredit, fineco)
    files = {"unicredit": (two.UNICREDIT_FILE, unicredit), "fineco": (two.FINECO_FILE, fineco)}
    name, account = files[first]
    _import(client, name, (two.OUT / name).read_bytes(), account)
    moves = two.build()
    # one statement alone: every movement between the two accounts is already a giroconto with both accounts
    transfers = Transaction.query.filter_by(type="transfer")
    assert transfers.count() == sum(m.transfer for m in moves) // 2
    assert transfers.filter(Transaction.counter_account_id.is_(None) | Transaction.account_id.is_(None)).count() == (
        sum(m.transfer and m.short == "Giroconto" for m in moves) // 2)  # «giroconto» rows name no IBAN

    other = "fineco" if first == "unicredit" else "unicredit"
    name, account = files[other]
    _import(client, name, (two.OUT / name).read_bytes(), account)
    assert transfers.count() == sum(m.transfer for m in moves) // 2
    assert transfers.filter(Transaction.counter_account_id.is_(None) | Transaction.account_id.is_(None)).count() == 0
    with app.test_request_context():
        summary = two.summary(moves)
        assert accounts.balance(unicredit) == float(summary["unicredit"]["closing"])
        assert accounts.balance(fineco) == float(summary["fineco"]["closing"])
    before = Transaction.query.count()
    _import(client, name, (two.OUT / name).read_bytes(), account)  # again: nothing new
    assert Transaction.query.count() == before
