"""F23: the deadlines calendar — every source, the hand-written ones, the .ics file, the page."""
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.personal_loan import PersonalLoan
from app.models.portfolio_model import InvestmentPlan
from app.models.reminder import Reminder
from app.models.wealth import Debt, Goal, Holding, InsurancePolicy
from app.services import contribution_limits, deadlines, notifications
from tests.conftest import make_tx


def _reminder(db, **values):
    base = dict(title="Bollo auto", due=date(2026, 11, 30), repeat="yearly", amount=Decimal("210.50"), notes=None)
    reminder = deadlines.save(None, **(base | values))
    db.session.commit()
    return reminder


@pytest.fixture()
def household(db):
    bank = Account(name="Banca")
    fund = Holding(name="Fondo Cometa", asset_class="Fondo Pensione", quantity=1, avg_price=1000)
    db.session.add_all([bank, fund])
    db.session.flush()
    db.session.add_all([
        make_tx(date=date(2026, 10, 5), description="Affitto", amount=700, is_recurring=True, recurrence="monthly"),
        make_tx(date=date(2026, 10, 27), description="Stipendio", amount=2000, type="income", is_recurring=True,
                recurrence="monthly"),
        Debt(name="Mutuo", type="Mutuo", principal=Decimal(12000), annual_rate=0, term_months=12,
             start_date=date(2026, 6, 10)),
        InsurancePolicy(type="Auto", company="Allianz", premium=Decimal(400), frequency="annual",
                        expiry_date=date(2026, 12, 3)),
        Goal(name="Vacanza", target_amount=Decimal(3000), saved_amount=Decimal(500), target_date=date(2026, 12, 20)),
        Goal(name="Fondo emergenza", target_amount=Decimal(100), saved_amount=Decimal(100), target_date=date(2026, 12, 21)),
        InvestmentPlan(name="PAC ETF", amount=Decimal(300), frequency="monthly", day=15, start=date(2026, 1, 1),
                       account_id=bank.id),
        InvestmentPlan(name="PAC finito", amount=Decimal(50), frequency="monthly", day=15, start=date(2025, 1, 1),
                       end=date(2025, 12, 31)),
        PersonalLoan(person="Luca", date=date(2026, 10, 1), amount=Decimal(80), due=date(2026, 12, 10)),
        PersonalLoan(person="Sara", date=date(2026, 10, 1), amount=Decimal(-40), due=date(2026, 12, 11)),
    ])
    db.session.commit()
    contribution_limits.save(None, name="Cometa", kind="pension", yearly=Decimal("5164.57"), total=None, since_year=None,
                             account_ids=[], holding_ids=[fund.id], category=None, notes=None)
    db.session.commit()


def test_every_source_in_december(app, db, household):
    _reminder(db, title="Revisione", due=date(2026, 12, 2), repeat="none", amount=None, notes="Officina Rossi")
    with app.test_request_context():
        items = deadlines.between(date(2026, 12, 1), date(2026, 12, 31))
    kinds = {d.kind for d in items}
    assert kinds == {"recurring", "installment", "policy", "plan", "goal", "loan", "limit", "fiscal", "reminder"}
    titles = [d.title for d in items]
    assert "Affitto" in titles and "Stipendio" in titles and "Rata Mutuo" in titles and "PAC «PAC ETF»" in titles
    assert "PAC «PAC finito»" not in titles  # ended last year
    assert "Luca ti restituisce" in titles and "Restituisci a Sara" in titles
    assert "IMU: saldo" in titles and "Cometa: ultimo giorno" in titles and "Revisione" in titles
    goal = next(d for d in items if d.title == "Obiettivo «Vacanza»")
    assert goal.amount == 2500 and not goal.outgoing
    assert next(d for d in items if d.title == "Obiettivo «Fondo emergenza»").amount is None
    assert next(d for d in items if d.kind == "limit").amount == Decimal("5164.57")
    assert next(d for d in items if d.title == "Rata Mutuo").amount == 1000
    assert items == sorted(items, key=lambda d: (d.day, d.kind, d.title))
    assert next(d for d in items if d.kind == "fiscal").icon == "percent"


def test_month_grid_and_total(app, db, household):
    with app.test_request_context():
        grid = deadlines.month_grid(date(2026, 12, 15))
    assert grid["month"] == date(2026, 12, 1) and grid["previous"] == date(2026, 11, 1) and grid["next"] == date(2027, 1, 1)
    assert all(len(week) == 7 for week in grid["weeks"]) and grid["weeks"][0][0] == (None, [])  # 1/12/2026 is a Tuesday
    days = [day for week in grid["weeks"] for day, _ in week if day]
    assert days[0] == date(2026, 12, 1) and days[-1] == date(2026, 12, 31)
    # rent 700 + installment 1000 + policy 400 + PAC 300 + 40 to Sara; the deductible room is a choice, not a bill
    assert grid["to_pay"] == 2440


def test_fiscal_dates_switch_off(app, db):
    with app.test_request_context():
        assert [d.title for d in deadlines.between(date(2027, 6, 1), date(2027, 6, 30))] == [
            "IMU: acconto", "Saldo IRPEF e primo acconto"]
        deadlines.set_fiscal(False)
        db.session.commit()
        assert not deadlines.fiscal_on() and deadlines.between(date(2027, 6, 1), date(2027, 6, 30)) == []


def test_reminders_repeat_and_done(app, db):
    yearly = _reminder(db)
    monthly = _reminder(db, title="Abbonamento ATM", due=date(2026, 1, 31), repeat="monthly", amount=Decimal(39))
    once = _reminder(db, title="Rinnovo carta d'identità", due=date(2026, 12, 1), repeat="none", amount=None)
    assert deadlines.occurrences(yearly, date(2026, 1, 1), date(2028, 12, 31)) == [
        date(2026, 11, 30), date(2027, 11, 30), date(2028, 11, 30)]
    assert deadlines.occurrences(monthly, date(2026, 2, 1), date(2026, 4, 30)) == [
        date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]
    assert deadlines.occurrences(once, date(2026, 1, 1), date(2026, 11, 30)) == []
    once.done = True
    assert deadlines.occurrences(once, date(2026, 1, 1), date(2026, 12, 31)) == []
    assert [d for _, d in deadlines.due_reminders(date(2026, 11, 25))] == [date(2026, 11, 30), date(2026, 11, 30)]
    with pytest.raises(ValueError, match="cosa scade"):
        _reminder(db, title="  ")
    with pytest.raises(ValueError, match="data"):
        _reminder(db, due=None)
    with pytest.raises(ValueError, match="negativo"):
        _reminder(db, amount=Decimal(-1))
    assert _reminder(db, repeat="weekly").repeat == "none"


def test_reminders_in_notifications(app, db):
    today = date.today()
    _reminder(db, title="Tagliando", due=today + timedelta(days=3), repeat="none")
    _reminder(db, title="Lontano", due=today + timedelta(days=30), repeat="none")
    with app.test_request_context():
        found = [n for n in notifications.collect() if n.key.startswith("reminder-")]
    assert [n.title for n in found] == ["Tagliando"] and "210,50" in found[0].detail


def test_ics_file(app, db):
    _reminder(db, title="Bollo; auto, \\ con una nota molto lunga che supera la riga di settantacinque ottetti — sì",
              due=date(2026, 11, 30), repeat="none", notes="riga uno\nriga due")
    with app.test_request_context():
        text = deadlines.ics(date(2026, 11, 1), date(2026, 11, 30), now=datetime(2026, 10, 19, 9, 0))
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    lines = text.split("\r\n")[:-1]
    assert all(len(line.encode()) <= 75 for line in lines) and "\n" not in text.replace("\r\n", "")
    unfolded = text.replace("\r\n ", "")
    assert "SUMMARY:Bollo\\; auto\\, \\\\ con una nota" in unfolded and "210\\,50 €" in unfolded
    assert "DESCRIPTION:riga uno\\nriga due" in unfolded and "DTSTAMP:20261019T090000" in unfolded
    assert "DTSTART;VALUE=DATE:20261130" in unfolded and "DTEND;VALUE=DATE:20261201" in unfolded
    uid = next(line for line in unfolded.split("\r\n") if line.startswith("UID:reminder"))
    with app.test_request_context():
        assert uid in deadlines.ics(date(2026, 11, 1), date(2026, 11, 30)).replace("\r\n ", "")  # stable
    assert deadlines._fold("é" * 80)[1].startswith("é") and all(len(p.encode()) <= 75 for p in deadlines._fold("é" * 80))


def test_pages(client, db):
    page = client.get("/deadlines/?month=2026-12").get_data(as_text=True)
    assert "Scadenzario" in page and "Dicembre 2026" in page and "IMU: saldo" in page
    assert client.get("/deadlines/?month=nonsense").status_code == 200
    client.post("/deadlines/new", data={"title": "Bollo auto", "due": "2026-11-30", "repeat": "yearly", "amount": "210,50"})
    reminder = Reminder.query.one()
    assert reminder.amount == Decimal("210.50") and reminder.repeat == "yearly"
    assert "cosa scade" in client.post("/deadlines/new", data={"title": "", "due": "2026-11-30"},
                                       follow_redirects=True).get_data(as_text=True)
    assert 'value="Bollo auto"' in client.get(f"/deadlines/?edit={reminder.id}").get_data(as_text=True)
    client.post(f"/deadlines/{reminder.id}/edit", data={"title": "Bollo moto", "due": "2026-11-30", "repeat": "yearly"})
    client.post(f"/deadlines/{reminder.id}/done")
    db.session.refresh(reminder)
    assert reminder.title == "Bollo moto" and reminder.due == date(2027, 11, 30) and reminder.amount is None
    client.post("/deadlines/new", data={"title": "Passaporto", "due": "2026-12-05", "repeat": "none"})
    once = Reminder.query.filter_by(title="Passaporto").one()
    client.post(f"/deadlines/{once.id}/done")
    db.session.refresh(once)
    assert once.done
    client.post("/deadlines/fiscal", data={"on": "0"})
    assert "IMU: saldo" not in client.get("/deadlines/?month=2026-12").get_data(as_text=True)
    soon = (date.today() + timedelta(days=10)).isoformat()
    client.post("/deadlines/new", data={"title": "Tagliando", "due": soon, "repeat": "none"})
    ics = client.get("/deadlines/scadenze.ics")
    assert ics.mimetype == "text/calendar" and "attachment" in ics.headers["Content-Disposition"]
    assert "Tagliando" in ics.get_data(as_text=True) and "Passaporto" not in ics.get_data(as_text=True)
    client.post(f"/deadlines/{once.id}/delete")
    assert Reminder.query.count() == 2
