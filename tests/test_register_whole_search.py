"""F35: with the box on the header of the table, every action on the selection works on the whole search (every
page), not only on the ticked rows of the page shown."""
from datetime import date

from app.models.account import Account
from app.models.event import SpendingEvent
from app.models.transaction import Transaction
from app.routes.transactions import AI_TAG
from tests.conftest import make_tx


def _add(db, n, **values):
    rows = [make_tx(description=f"Spesa {i}", **values) for i in range(n)]
    db.session.add_all(rows)
    db.session.commit()
    return rows


def _whole(category, **extra):
    return {"scope": "search", "category": category, "q": "", "type": "", **extra}


def test_delete_removes_the_whole_search_and_nothing_else(client, db):
    _add(db, 3, category="Alimentari")
    other = _add(db, 2, category="Casa")
    client.post("/transactions/delete-selected", data=_whole("Alimentari"))
    assert Transaction.query.count() == 2
    assert {tx.id for tx in Transaction.query} == {tx.id for tx in other}


def test_assign_confirm_and_event_work_on_the_whole_search(client, db):
    food = _add(db, 3, category="Alimentari", tags=[AI_TAG])
    home = _add(db, 1, category="Casa", tags=[AI_TAG])
    account = Account(name="Fineco", kind="current", currency="EUR")
    event = SpendingEvent(name="Viaggio", start=date(2026, 5, 1), end=date(2026, 6, 30))
    db.session.add_all([account, event])
    db.session.commit()
    client.post("/transactions/assign-account", data={**_whole("Alimentari"), "account_id": account.id})
    client.post("/transactions/confirm-ai", data=_whole("Alimentari"))
    client.post("/events/assign", data={**_whole("Alimentari"), "event_id": event.id})
    for tx in food:
        db.session.refresh(tx)
        assert tx.account_id == account.id and AI_TAG not in tx.tags and tx.event_id == event.id
    db.session.refresh(home[0])
    assert home[0].account_id is None and AI_TAG in home[0].tags and home[0].event_id is None


def test_without_the_whole_search_only_the_ticked_rows_change(client, db):
    first, second = _add(db, 2, category="Alimentari")
    client.post("/transactions/delete-selected", data={"ids": [str(first.id)], "category": "Alimentari"})
    assert [tx.id for tx in Transaction.query] == [second.id]


def test_the_search_card_closes_and_says_how_many_filters_are_on(client, db):
    _add(db, 1, category="Alimentari")
    html = client.get("/transactions/?category=Alimentari&type=expense").get_data(as_text=True)
    assert 'id="search-box" open data-remember="mfp-search-open"' in html and "2 filtri attivi" in html
    assert "filtro attivo" not in client.get("/transactions/").get_data(as_text=True)
