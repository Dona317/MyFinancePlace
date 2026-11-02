"""The statements of a year closed on 1 January; a later change to that year is noticed and saved again."""
from datetime import date

import pytest

from app.models.year_close import YearClose
from app.services import notifications, year_close
from app.web import hooks
from tests.conftest import make_tx


def _add(db, **values):
    tx = make_tx(**values)
    db.session.add(tx)
    db.session.commit()
    return tx


def test_the_past_years_are_closed_once_from_the_first_with_data(app, db):
    _add(db, date=date(2024, 3, 1), amount=100, type="income")
    _add(db, date=date(2025, 6, 1), amount=40)
    _add(db, date=date(2026, 1, 10), amount=5)
    made = year_close.ensure(date(2026, 1, 1))
    assert [(row.year, row.version, row.automatic) for row in made] == [(2024, 1, True), (2025, 1, True)]
    assert year_close.ensure(date(2026, 5, 1)) == []  # not again
    row = year_close.latest(2025)
    assert row.data["income_statement"]["summary"]["expenses"] == 40
    assert row.data["balance_sheet"]["date"] == "2025-12-31" and row.data["cash_flow"]["year"] == 2025
    assert year_close.ensure(date(2027, 1, 1))[0].year == 2026
    assert year_close.changed() == []


def test_nothing_to_close_without_transactions(app, db):
    assert year_close.ensure(date(2026, 1, 1)) == []


def test_a_change_to_a_closed_year_is_noticed_and_saved_again(client, db):
    old = _add(db, date=date(2025, 6, 1), amount=40)
    year_close.ensure(date(2026, 1, 1))
    _add(db, date=date(2026, 2, 1), amount=7)  # the new year: the closed one is the same
    assert year_close.changed() == []
    old.amount = 45
    db.session.commit()
    assert [row.year for row in year_close.changed()] == [2025]
    with client.application.test_request_context():
        bell = notifications.collect(date(2026, 11, 2))
    assert any(n.key == "year-close-2025-1" and "Bilanci 2025 da aggiornare" in n.title for n in bell)
    page = client.get("/accounting/closes").get_data(as_text=True)
    assert "Aggiorna i bilanci 2025" in page and "dati cambiati" in page
    client.post("/accounting/closes/2025")
    assert year_close.latest(2025).version == 2 and year_close.changed() == []
    assert year_close.latest(2025).data["income_statement"]["summary"]["expenses"] == 45
    page = client.get("/accounting/closes").get_data(as_text=True)
    assert "sostituita" in page and "aggiornata" in page
    saved = client.get(f"/accounting/closes/{year_close.latest(2025).id}.json")
    assert saved.headers["Content-Disposition"].endswith('bilanci-2025-v2.json"') and saved.get_json()["version"] == 2


def test_only_past_years_are_closed_by_hand(client, db):
    client.post(f"/accounting/closes/{date.today().year}")
    assert YearClose.query.count() == 0
    assert "Nessun anno chiuso" in client.get("/accounting/closes").get_data(as_text=True)


@pytest.fixture()
def year_close_on(app):
    app.config["YEAR_CLOSE"] = True
    hooks._CLOSED_TODAY.clear()
    yield
    app.config.pop("YEAR_CLOSE", None)
    hooks._CLOSED_TODAY.clear()


def test_the_first_visit_of_the_day_closes_the_past_years(client, db, year_close_on):
    _add(db, date=date(date.today().year - 1, 6, 1), amount=10)
    client.get("/accounting/closes")
    assert year_close.latest(date.today().year - 1) is not None
    YearClose.query.delete()
    db.session.commit()
    client.get("/accounting/closes")
    assert YearClose.query.count() == 0  # looked at once a day
