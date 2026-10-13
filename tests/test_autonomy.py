"""F10a: months of autonomy — how long the liquid money pays the average spending."""
from datetime import date
from decimal import Decimal

from app.models.account import Account
from app.services import analytics, categories
from tests.conftest import make_tx

TODAY = date(2026, 7, 15)


def _spend(db, months, rent=1000, food=500):
    """`months` complete months of rent (fixed) and food (variable) before July 2026, and a big July expense."""
    for k in range(1, months + 1):
        month = 7 - k
        db.session.add_all([make_tx(date=date(2026, month, 3), amount=rent, category="Casa"),
                            make_tx(date=date(2026, month, 9), amount=food, category="Alimentari")])
    db.session.add(make_tx(date=date(2026, 7, 2), amount=9000, category="Viaggi"))  # the month under way: left out
    db.session.add(Account(name="Conto", kind="current", opening_balance=Decimal(30000)))
    db.session.commit()


def test_average_of_the_complete_months_only(app, db):
    categories.ensure_defaults()
    _spend(db, 4)
    with app.test_request_context():
        run = analytics.autonomy(TODAY)
    assert run["basis"] == 4 and run["avg_expenses"] == 1500.0 and run["avg_essential"] == 1000.0
    liquid = run["liquid"]
    assert run["months_all"] == round(liquid / 1500, 1) and run["months_essential"] == round(liquid / 1000, 1)


def test_at_most_twelve_months(app, db):
    categories.ensure_defaults()
    db.session.add(make_tx(date=date(2024, 1, 5), amount=100, category="Alimentari"))
    db.session.commit()
    with app.test_request_context():
        assert analytics.autonomy(TODAY)["basis"] == 12


def test_too_little_data_gives_no_average(app, db):
    _spend(db, 2)
    with app.test_request_context():
        run = analytics.autonomy(TODAY)
    assert run["basis"] == 2 and run["avg_expenses"] is None and run["months_all"] is None
    with app.test_request_context():
        assert analytics.autonomy(TODAY)["liquid"] == run["liquid"]


def test_no_essential_spending_gives_no_essential_months(app, db):
    categories.ensure_defaults()
    _spend(db, 3, rent=0)
    with app.test_request_context():
        run = analytics.autonomy(TODAY)
    assert run["avg_essential"] == 0 and run["months_essential"] is None and run["months_all"] is not None


def test_dashboard_card_and_target_setting(client, db):
    categories.ensure_defaults()
    _spend(db, 4)
    html = client.get("/dashboard").get_data(as_text=True)
    assert "Mesi di autonomia" in html and "/ 6 mesi" in html
    client.post("/settings/save", data={"dashboard_health": "on", "autonomy_target": "12"})
    assert "/ 12 mesi" in client.get("/dashboard").get_data(as_text=True)
    client.post("/settings/save", data={"dashboard_health": "on", "autonomy_target": "7"})  # not offered: the default
    assert "/ 6 mesi" in client.get("/dashboard").get_data(as_text=True)
    assert 'name="autonomy_target"' in client.get("/settings/").get_data(as_text=True)


def test_dashboard_without_enough_months(client, db):
    db.session.add(make_tx(date=date.today(), amount=10))
    db.session.commit()
    assert "Servono almeno 3 mesi completi" in client.get("/dashboard").get_data(as_text=True)
