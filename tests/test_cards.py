"""F41: the debit, credit and prepaid cards of an account — several per account, set in the account's form."""
from app.models.account import Account
from app.models.card import Card


def _form(**extra):
    return {"name": "Fineco", "kind": "current", "currency": "EUR", "active": "on", **extra}


def test_cards_are_added_changed_and_removed_in_the_accounts_form(client, db):
    client.post("/accounts/new", data=_form(card_id=["", ""], card_name=["Bancomat", "Visa"], card_kind=["debit", "credit"],
                                            card_last4=["12 34", "9876543"]))
    account = Account.query.one()
    assert [(c.name, c.kind, c.last4) for c in account.cards] == [("Bancomat", "debit", "1234"), ("Visa", "credit", "6543")]
    first, second = account.cards
    client.post(f"/accounts/{account.id}/edit", data=_form(
        card_id=[str(first.id), str(second.id), ""], card_name=["Bancomat Fineco", "Visa", "Revolut"],
        card_kind=["debit", "credit", "nope"], card_last4=["1234", "6543", ""], card_remove=[str(second.id)]))
    db.session.expire_all()
    assert [(c.name, c.kind) for c in Account.query.one().cards] == [("Bancomat Fineco", "debit"), ("Revolut", "debit")]
    page = client.get("/accounts/").get_data(as_text=True)
    assert "Le mie carte" in page and "Bancomat Fineco" in page and "•••• 1234" in page and "2 carte" in page
    assert "Carte del conto" in client.get(f"/accounts/{account.id}").get_data(as_text=True)
    # an account deleted takes its cards with it
    client.post(f"/accounts/{account.id}/delete")
    assert Card.query.count() == 0


def test_the_accounts_form_opens_in_a_popup_and_reloads_the_page_under_it(client, db):
    page = client.get("/accounts/").get_data(as_text=True)
    assert 'data-popup-size="wide"' in page and "Nessuna carta" in page
    form = client.get("/accounts/new?embed=1&next=/transactions/embed-done?reload%3D1").get_data(as_text=True)
    assert 'class="embedded"' in form and "data-close-embed" in form and 'name="embed" value="1"' in form
    done = client.post("/accounts/new", data=_form(embed="1", next="/transactions/embed-done?reload=1"))
    assert done.headers["Location"].endswith("/transactions/embed-done?reload=1")
    assert "reload: true" in client.get("/transactions/embed-done?reload=1").get_data(as_text=True)
