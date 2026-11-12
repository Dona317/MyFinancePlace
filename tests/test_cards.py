"""
F41: payment cards charged on an account — what is kept (never the full number, CVV or PIN), the card of a
movement from the form or from the bank text of an imported one, its spending of the month, its expiry in the
deadlines and the reminders, the pages.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.card import Card
from app.models.transaction import Transaction
from app.services import cards, deadlines, notifications
from app.services.cards import CardError, CardInput
from tests.conftest import make_tx


def _input(**values) -> CardInput:
    base = dict(name="Visa Fineco", kind="credit", network="visa", number="4821", expiry="08/28", holder="Mario Rossi",
                account_id=None, credit_limit=Decimal(1500), statement_day=15, contactless=True, notes=None)
    return CardInput(**(base | values))


@pytest.fixture()
def bank(db):
    account = Account(name="Fineco", kind="current")
    other = Account(name="Intesa", kind="current")
    db.session.add_all([account, other])
    db.session.commit()
    return account, other


def test_what_is_kept(app, db, bank):
    account, _other = bank
    with app.test_request_context():
        card, cut = cards.save(None, _input(account_id=account.id, number="4111 1111 1111 4821"))
        db.session.commit()
    assert cut and card.last4 == "4821"  # the full number is never stored
    assert (card.expiry_month, card.expiry_year, card.statement_day, card.credit_limit) == (8, 2028, 15, Decimal(1500))
    assert cards.expiry_date(card) == date(2028, 8, 31) and cards.masked(card) == "•••• 4821"
    assert [c.name for c in account.cards] == ["Visa Fineco"]
    with app.test_request_context():
        debit, cut = cards.save(None, _input(name="Bancomat", kind="debit", network="bancomat", number="", expiry="2027-03",
                                             credit_limit=Decimal(500), statement_day=10, account_id=account.id))
    assert not cut and debit.last4 is None and (debit.credit_limit, debit.statement_day) == (None, None)
    assert (debit.expiry_month, debit.expiry_year) == (3, 2027)
    for wrong, message in ((dict(name=" "), "nome"), (dict(kind="gold"), "Tipo"), (dict(network="diners"), "Circuito"),
                           (dict(number="12"), "ultime 4"), (dict(expiry="13/28"), "Scadenza"),
                           (dict(expiry="domani"), "Scadenza"), (dict(statement_day=40), "giorno"),
                           (dict(credit_limit=Decimal(-1)), "plafond")):
        with app.test_request_context(), pytest.raises(CardError, match=message):
            cards.save(None, _input(**wrong))


def test_the_card_of_an_imported_movement(app, db, bank):
    account, other = bank
    with app.test_request_context():
        visa, _cut = cards.save(None, _input(account_id=account.id))
        twin, _cut = cards.save(None, _input(name="Carta Intesa", account_id=other.id))  # same last four, other bank
        db.session.commit()
        rows = [make_tx(description="Esselunga", bank_description="PAGAMENTO POS CARTA *4821 ESSELUNGA MILANO",
                        account_id=account.id),
                make_tx(description="Amazon", bank_description="Op. carta n. ****4821 AMAZON EU", account_id=other.id),
                make_tx(description="Bar", bank_description="POS XXXX4821 BAR", account_id=None),
                make_tx(description="Affitto", bank_description="BONIFICO 482100 AFFITTO", account_id=account.id)]
        assert cards.assign(rows) == 2
    assert [r.card_id for r in rows] == [visa.id, twin.id, None, None]  # two cards end in 4821: no account, no guess
    assert cards.digits_in("CARD 1234 and ***5678") == {"1234", "5678"}


def test_spending_of_the_month_and_the_movements_list(client, app, db, bank):
    account, _other = bank
    with app.test_request_context():
        card, _cut = cards.save(None, _input(account_id=account.id))
        db.session.commit()
    today = date.today()
    db.session.add_all([make_tx(date=today.replace(day=1), amount=40, card_id=card.id, account_id=account.id,
                                description="Spesa con la carta"),
                        make_tx(date=today.replace(day=1), amount=500, type="income", card_id=card.id),
                        make_tx(date=date(2020, 1, 1), amount=99, card_id=card.id),
                        make_tx(date=today.replace(day=1), amount=7, description="Pagato in contanti")])
    db.session.commit()
    with app.test_request_context():
        assert cards.month_spending(card) == Decimal(40) and cards.movements_count(card) == 3
    page = client.get(f"/transactions/?card={card.id}").get_data(as_text=True)
    assert "Spesa con la carta" in page and "Pagato in contanti" not in page
    page = client.get(f"/accounts/{account.id}").get_data(as_text=True)
    assert 'id="cards"' in page and "Visa Fineco" in page and "3 movimenti" in page and "addebito il 15" in page


def test_expiry_in_deadlines_and_reminders(app, db, bank):
    account, _other = bank
    soon = date.today().replace(day=1)
    with app.test_request_context():
        card, _cut = cards.save(None, _input(account_id=account.id, expiry=f"{soon.month:02d}/{soon.year}"))
        old, _cut = cards.save(None, _input(name="Vecchia", account_id=account.id, expiry="01/20", active=False))
        db.session.commit()
        found = [d for d in deadlines.between(soon, soon.replace(day=28) + (date(2000, 1, 5) - date(2000, 1, 1)) * 2)
                 if d.kind == "card"]
        assert [d.title for d in found] == ["Scade la carta Visa Fineco"] and found[0].detail == "•••• 4821"
        alerts = [n for n in notifications.collect() if n.key.startswith("card-")]
    assert len(alerts) == 1 and "Carta in scadenza: Visa Fineco" in alerts[0].title and cards.expires_soon(card)
    assert not cards.expires_soon(old)


def test_pages(client, db, bank):
    account, _other = bank
    page = client.get(f"/accounts/{account.id}/edit").get_data(as_text=True)
    assert "Aggiungi una carta" in page and "mockup-tbd" not in page
    assert "Salva il conto, poi aggiungi" in client.get("/accounts/new").get_data(as_text=True)
    page = client.get(f"/accounts/cards/new?account={account.id}").get_data(as_text=True)
    assert "il CVV e il PIN non vanno mai scritti" in page and f'value="{account.id}" selected' in page
    form = {"name": "Visa Fineco", "kind": "credit", "network": "visa", "number": "4111111111114821",
            "expiry": "08/28", "holder": "Mario Rossi", "account_id": str(account.id), "credit_limit": "1500",
            "statement_day": "15", "contactless": "1", "active": ["", "1"], "notes": ""}
    page = client.post("/accounts/cards/new", data=form, follow_redirects=True).get_data(as_text=True)
    assert "Carta «Visa Fineco» salvata." in page and "teniamo solo le ultime 4 cifre" in page
    card = Card.query.one()
    assert card.last4 == "4821" and card.active and "4111111111114821" not in page
    assert "Visa Fineco 4821" in client.get("/accounts/").get_data(as_text=True)
    page = client.post(f"/accounts/cards/{card.id}/edit", data={**form, "expiry": "99/99"}, follow_redirects=True)
    assert "Scadenza non valida" in page.get_data(as_text=True)
    client.post(f"/accounts/cards/{card.id}/edit", data={**form, "number": "4821", "active": [""]})
    db.session.refresh(card)
    assert not card.active
    # the card of a movement from its form
    tx = make_tx(description="Cena", amount=60, account_id=account.id)
    db.session.add(tx)
    db.session.commit()
    page = client.get(f"/transactions/{tx.id}/edit").get_data(as_text=True)
    assert 'name="card_id"' in page and f'data-account="{account.id}"' in page
    client.post(f"/transactions/{tx.id}/edit", data={"date": "2026-11-02", "description": "Cena", "amount": "60",
                                                     "type": "expense", "category": "Ristoranti",
                                                     "account_id": str(account.id), "card_id": str(card.id)})
    assert db.session.get(Transaction, tx.id).card_id == card.id
    page = client.post(f"/accounts/cards/{card.id}/delete", follow_redirects=True).get_data(as_text=True)
    assert "i suoi movimenti restano, senza carta" in page
    assert Card.query.count() == 0 and db.session.get(Transaction, tx.id).card_id is None
