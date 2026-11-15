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


def test_the_filters_panel_opens_with_a_filter_on_and_the_pill_counts_them(client, db):
    _add(db, 1, category="Alimentari")
    html = client.get("/transactions/?category=Alimentari&type=expense&q=spesa").get_data(as_text=True)
    # two filters on (the search text apart): the panel open, «Filtri · 2» lit, «Azzera» there
    assert 'class="tx-panel is-open" id="search-box" data-remember="mfp-search-open" data-forced="1"' in html
    assert "Filtri · 2" in html and 'id="filters-toggle" aria-controls="search-box"' in html and "Togli ricerca e filtri" in html
    plain = client.get("/transactions/").get_data(as_text=True)
    assert 'class="tx-panel" id="search-box"' in plain and "Filtri ·" not in plain and "Togli ricerca e filtri" not in plain
    # the search alone: no filter counted, but «Azzera» shows
    only_text = client.get("/transactions/?q=spesa").get_data(as_text=True)
    assert "Filtri ·" not in only_text and "Togli ricerca e filtri" in only_text


def test_search_filters_and_bulk_edit_live_inside_the_table_card(client, db):
    _add(db, 2, category="Alimentari", tags=[AI_TAG])
    db.session.add_all([Account(name="Fineco", kind="current", currency="EUR"),
                        SpendingEvent(name="Viaggio", start=date(2026, 5, 1), end=date(2026, 6, 30))])
    db.session.commit()
    html = client.get("/transactions/").get_data(as_text=True)
    card = html[html.index('<div class="card tx-card">'):html.index('id="tx-table"')]
    # the toolbar, the filters (the amount written: two text fields) and the Modifica massiva, all in the table's card
    for piece in ('id="filter-form"', 'id="register-q"', 'id="search-history"', 'id="search-box"', 'id="bulk-box"',
                  'id="bulk-edit-form"', 'id="bulk-scope"', 'id="bulk-summary"', 'id="bulk-toggle" aria-controls="bulk-box"',
                  'id="bulk-delete"', 'id="bulk-count"', 'id="assign-form"', 'id="bulk-assign"', 'id="event-form"',
                  'id="bulk-event"', 'id="confirm-form"', 'id="bulk-confirm"', 'id="bulk-delete-icon"',
                  'type="text" inputmode="decimal" name="min"', 'type="text" inputmode="decimal" name="max"',
                  "Azioni sulla selezione", "Cambia i campi"):
        assert piece in card, piece
    form = card[card.index('id="filter-form"'):card.index('</form>', card.index('name="recurring"'))]
    assert 'name="q"' in form and 'name="min"' in form and 'name="category"' in form  # one form: search and filters
    above = html.split('<div class="card tx-card">')[0].split('class="section-tabs')[-1]
    assert '<div class="card' not in above  # no separate card between the tabs and the table


def test_the_table_is_sorted_by_a_click_on_its_titles(client, db):
    for description, amount, day in (("bar", 5, 3), ("Affitto", 800, 1), ("cinema", 20, 2)):
        db.session.add(make_tx(description=description, amount=amount, date=date(2026, 6, day), category="Casa"))
    db.session.commit()
    order = lambda html: [d for d in ("bar", "Affitto", "cinema") if f'data-description="{d}"' in html]  # noqa: E731

    def rows(query):
        html = client.get(f"/transactions/?{query}").get_data(as_text=True)
        return sorted(order(html), key=lambda d: html.index(f'data-description="{d}"'))
    assert rows("") == ["bar", "cinema", "Affitto"]  # the newest first
    assert rows("sort=description") == ["Affitto", "bar", "cinema"]  # A to Z, whatever the case
    assert rows("sort=amount") == ["Affitto", "cinema", "bar"]  # the biggest first
    assert rows("sort=amount&dir=asc") == ["bar", "cinema", "Affitto"]
    html = client.get("/transactions/?sort=amount&category=Casa").get_data(as_text=True)
    # the arrow on the column in use; its title turns the order round, the others start from their own
    assert 'class="sort-link is-sorted"' in html and "sort=amount&amp;dir=asc" in html and "sort=date&amp;dir=desc" in html
    assert rows("sort=nope&dir=up") == ["bar", "cinema", "Affitto"]


def test_the_amount_filter_from_to(client, db):
    for description, amount in (("small", 5), ("mid", 50), ("big", 500)):
        db.session.add(make_tx(description=description, amount=amount, type="income" if amount == 50 else "expense"))
    db.session.commit()
    html = client.get("/transactions/?min=10&max=100").get_data(as_text=True)
    assert 'data-description="mid"' in html and 'data-description="small"' not in html and 'data-description="big"' not in html
    assert "col-filter-btn is-on" in html and "Togli" in html
    html = client.get("/transactions/?min=x&max=-100").get_data(as_text=True)  # not a number: no limit; the sign: none
    assert 'data-description="big"' not in html and 'data-description="mid"' in html
    # the whole search follows the filter too
    client.post("/transactions/delete-selected", data={"scope": "search", "min": "100"})
    assert [t.description for t in Transaction.query.order_by(Transaction.id)] == ["small", "mid"]
