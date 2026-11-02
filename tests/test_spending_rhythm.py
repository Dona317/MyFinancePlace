"""F20e: the rhythm of spending — the calendar of the year, the weekdays and what changed last month."""
from datetime import date
from decimal import Decimal

from app.services import spending_rhythm
from tests.conftest import make_tx

TODAY = date(2026, 10, 13)


def _spend(db):
    db.session.add_all([
        make_tx(description="Spesa", amount=Decimal("100"), category="Alimentari", date=date(2026, 9, 5)),   # Saturday
        make_tx(description="Spesa", amount=Decimal("60"), category="Alimentari", date=date(2026, 9, 12)),   # Saturday
        make_tx(description="Cena", amount=Decimal("80"), category="Ristoranti", date=date(2026, 9, 7)),     # Monday
        make_tx(description="Benzina", amount=Decimal("50"), category="Carburante", date=date(2026, 8, 3)),
        make_tx(description="Spesa", amount=Decimal("40"), category="Alimentari", date=date(2026, 8, 8)),
        make_tx(description="Regalo", amount=Decimal("5"), category="Regali", date=date(2026, 9, 9)),
        make_tx(description="Stipendio", amount=Decimal("2000"), type="income", category="Stipendio", date=date(2026, 9, 27)),
        make_tx(description="Spesa vecchia", amount=Decimal("1200"), category="Alimentari", date=date(2026, 1, 15)),
    ])
    db.session.commit()


def test_calendar(app, db):
    _spend(db)
    with app.test_request_context():
        cal = spending_rhythm.calendar(2026, TODAY)
    assert cal["total"] == Decimal(1535) and cal["days_with"] == 7 and cal["days"] == 286
    cells = {c.day: c for week in cal["weeks"] for c in week if c.day}
    assert len(cells) == 286 and date(2026, 10, 14) not in cells  # nothing after today
    assert cells[date(2026, 1, 15)].level == 4 and cells[date(2026, 9, 9)].level == 1 and cells[date(2026, 9, 10)].level == 0
    assert cal["weeks"][0][0].day is None  # 1 January 2026 is a Thursday: Monday–Wednesday are outside the year
    assert cal["busiest"][0] == (date(2026, 1, 15), Decimal(1200))
    with app.test_request_context():
        assert spending_rhythm.calendar(2025, TODAY)["days_with"] == 0


def test_weekdays_and_changes(app, db):
    _spend(db)
    with app.test_request_context():
        days = spending_rhythm.weekdays(date(2026, 9, 1), date(2026, 9, 30))
        ch = spending_rhythm.changes(TODAY)
    assert days[5] == Decimal("40.00")  # 160 € over 4 Saturdays
    assert days[0] == Decimal("20.00")  # 80 € over 4 Mondays
    assert ch["month"] == date(2026, 9, 1) and (ch["total_now"], ch["total_before"]) == (Decimal(245), Decimal(90))
    assert [(r.category, r.diff) for r in ch["up"]] == [("Alimentari", Decimal(120)), ("Ristoranti", Decimal(80))]
    assert [(r.category, r.diff) for r in ch["down"]] == [("Carburante", Decimal(-50))]  # Regali moved < 10 €
    up = ch["up"][0]
    assert up.average == Decimal("103.33") and up.vs_average == Decimal("56.67")  # (1200 + 40) / 12


def test_page(client, db):
    _spend(db)
    page = client.get("/reports/rhythm?year=2026").get_data(as_text=True)
    assert "Calendario delle spese" in page and "weekdayChart" in page and "rhythm-day level-4" in page
    assert "Ritmo" in client.get("/reports/summary").get_data(as_text=True)
