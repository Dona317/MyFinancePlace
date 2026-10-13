"""F20b: spending events — movements of any category gathered under a trip or a wedding, with cost and budget."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.event import SpendingEvent
from app.models.transaction import Transaction
from app.services import backup, spending_events
from app.services.spending_events import EventError
from tests.conftest import make_tx


@pytest.fixture()
def trip(db):
    event = SpendingEvent(name="Giappone", start=date(2026, 4, 1), end=date(2026, 4, 10), budget=Decimal("3000"))
    db.session.add(event)
    db.session.flush()
    db.session.add_all([
        make_tx(description="Volo", amount=Decimal("1200"), category="Viaggi", date=date(2026, 3, 1), event_id=event.id),
        make_tx(description="Hotel", amount=Decimal("900"), category="Viaggi", date=date(2026, 4, 2), event_id=event.id),
        make_tx(description="Sushi", amount=Decimal("80"), category="Ristoranti", date=date(2026, 4, 3), event_id=event.id),
        make_tx(description="Rimborso hotel", amount=Decimal("100"), type="income", category="Rimborsi",
                date=date(2026, 4, 5), event_id=event.id),
        make_tx(description="Treno", amount=Decimal("50"), category="Trasporti", date=date(2026, 4, 4)),
        make_tx(description="Giroconto", amount=Decimal("500"), type="transfer", category="Giroconto", date=date(2026, 4, 4)),
        make_tx(description="Spesa a casa", amount=Decimal("60"), category="Alimentari", date=date(2026, 4, 20)),
    ])
    db.session.commit()
    return event


def test_summary(app, trip):
    with app.test_request_context():
        s = spending_events.summary(trip)
    assert (s.spent, s.refunds, s.net, s.count, s.days) == (Decimal(2180), Decimal(100), Decimal(2080), 4, 10)
    assert s.by_category == [("Viaggi", Decimal(2100)), ("Ristoranti", Decimal(80))]
    assert (s.per_day, s.left, round(s.used_pct, 1)) == (Decimal("208.00"), Decimal(920), 69.3)
    assert [tx.description for tx in spending_events.suggestions(trip)] == ["Treno"]  # in its dates, no transfers
    with app.test_request_context():
        assert spending_events.spent_outside_events(date(2026, 4, 1), date(2026, 4, 30)) == Decimal(110)
        assert spending_events.spent_in_events(date(2026, 1, 1), date(2026, 12, 31)) == Decimal(2180)
    one_day = SpendingEvent(name="Cena", start=date(2026, 5, 1))
    assert spending_events.summary(one_day, []).days == 1 and spending_events.summary(one_day, []).used_pct is None


@pytest.mark.parametrize("args, message", [
    (("", date(2026, 1, 1), None, None), "nome"),
    (("x", None, None, None), "inizio"),
    (("x", date(2026, 1, 2), date(2026, 1, 1), None), "fine"),
    (("x", date(2026, 1, 1), None, Decimal(-1)), "negativo"),
])
def test_validation(app, args, message):
    with app.test_request_context(), pytest.raises(EventError, match=message):
        spending_events.validate(*args)


def test_pages(client, db, trip):
    page = client.get("/events/").get_data(as_text=True)
    assert "Giappone" in page and "€ 2.080,00" in page
    page = client.get(f"/events/{trip.id}").get_data(as_text=True)
    assert "restano € 920,00" in page and "Treno" in page and "€ 208,00" in page

    treno = Transaction.query.filter_by(description="Treno").one()
    client.post("/events/assign", data={"event_id": str(trip.id), "ids": [str(treno.id)]})
    assert db.session.get(Transaction, treno.id).event_id == trip.id
    page = client.post("/events/assign", data={"event_id": "", "ids": [str(treno.id)]}, follow_redirects=True)
    assert "1 movimenti tolti dagli eventi." in page.get_data(as_text=True)

    page = client.post("/events/", data={"name": "Matrimonio", "start": "2026-06-20", "budget": "15000"},
                       follow_redirects=True).get_data(as_text=True)
    assert "Evento creato" in page and "Nessun movimento" in page
    wedding = SpendingEvent.query.filter_by(name="Matrimonio").one()
    assert wedding.budget == Decimal(15000)
    page = client.post("/events/", data={"name": "", "start": "2026-06-20"}, follow_redirects=True).get_data(as_text=True)
    assert "Dai un nome all" in page
    client.post(f"/events/{wedding.id}", data={"name": "Matrimonio Anna", "start": "2026-06-20", "end": "2026-06-21",
                                               "budget": "", "notes": "Villa"})
    db.session.refresh(wedding)
    assert (wedding.name, wedding.end, wedding.budget, wedding.notes) == ("Matrimonio Anna", date(2026, 6, 21), None, "Villa")
    page = client.post(f"/events/{wedding.id}", data={"name": "x", "start": "2026-06-20", "end": "2026-06-01"},
                       follow_redirects=True).get_data(as_text=True)
    assert "La fine viene prima" in page
    client.post(f"/events/{trip.id}/delete")
    assert Transaction.query.filter(Transaction.event_id.isnot(None)).count() == 0 and Transaction.query.count() == 7


def test_transaction_pages_show_events(client, db, trip):
    page = client.get("/transactions/").get_data(as_text=True)
    assert 'id="event-form"' in page and "Giappone" in page
    volo = Transaction.query.filter_by(description="Volo").one()
    page = client.get(f"/transactions/{volo.id}/edit").get_data(as_text=True)
    assert f'<option value="{trip.id}" selected>Giappone</option>' in page


def test_backup_keeps_events(app, db, trip):
    with app.test_request_context():
        data = backup.export_data()
        backup.restore(data, {})
    assert SpendingEvent.query.one().name == "Giappone"
    assert Transaction.query.filter(Transaction.event_id.isnot(None)).count() == 4
