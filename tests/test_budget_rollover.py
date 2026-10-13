"""F7: budget rollover to the next month, and the set-aside for the not-monthly expenses."""
from datetime import date
from decimal import Decimal

from app.models.budget import Budget
from app.services import budgets, categories
from tests.conftest import make_tx


def _food(db, *amounts):
    """Groceries of 100 every-month budget: `amounts` spent in May, June, July 2026."""
    for month, amount in zip((5, 6, 7), amounts):
        db.session.add(make_tx(date=date(2026, month, 10), amount=amount, category="Alimentari"))
    db.session.commit()


def test_what_is_left_or_overspent_moves_to_the_next_month(app, db):
    budgets.save("Alimentari", Decimal(100), None, rollover=True, since=date(2026, 5, 1))
    db.session.commit()
    _food(db, 70, 150, 40)
    with app.test_request_context():
        assert budgets.carried("Alimentari", date(2026, 5, 1)) == 0  # the first month carries nothing in
        assert budgets.carried("Alimentari", date(2026, 6, 1)) == 30  # May left 30
        assert budgets.carried("Alimentari", date(2026, 7, 1)) == -20  # June overspent by 50
        [line] = budgets.status(date(2026, 7, 1), date(2026, 7, 20))
    assert (line["planned"], line["carried"], line["available"], line["left"]) == (100, -20, 80, 40)
    assert line["rollover"] and line["share"] == 50.0


def test_a_one_month_budget_counts_in_the_carry(app, db):
    budgets.save("Alimentari", Decimal(100), None, rollover=True, since=date(2026, 5, 1))
    budgets.save("Alimentari", Decimal(300), date(2026, 6, 1))  # a bigger June
    db.session.commit()
    _food(db, 100, 150)
    with app.test_request_context():
        assert budgets.carried("Alimentari", date(2026, 7, 1)) == 150


def test_switching_off_forgets_the_carry_and_no_rollover_carries_nothing(app, db):
    budgets.save("Alimentari", Decimal(100), None, rollover=True, since=date(2026, 5, 1))
    db.session.commit()
    _food(db, 10)
    budgets.save("Alimentari", Decimal(100), None, rollover=False)
    db.session.commit()
    assert Budget.query.one().rollover_since is None
    with app.test_request_context():
        assert budgets.carried("Alimentari", date(2026, 6, 1)) == 0
    budgets.save("Svago", Decimal(50), None)  # rollover None: left as it is (off)
    db.session.commit()
    with app.test_request_context():
        assert budgets.carried("Svago", date(2026, 6, 1)) == 0


def test_set_aside_for_the_not_monthly_categories(client, db):
    categories.ensure_defaults()
    db.session.add_all([make_tx(date=date(2026, 2, 10), amount=540, category="Assicurazioni"),
                        make_tx(date=date(2026, 5, 16), amount=150, category="Tasse e imposte"),
                        make_tx(date=date(2026, 6, 1), amount=500, category="Alimentari")])  # variable: not here
    db.session.commit()
    with client.application.test_request_context():
        items = {i["category"]: i for i in budgets.set_asides(date(2026, 7, 15))}
    assert set(items) == {"Assicurazioni", "Tasse e imposte"} and items["Assicurazioni"]["monthly"] == 45.0
    assert items["Assicurazioni"]["budget"] is None
    response = client.post("/lifestyle/budget/set-aside?month=2026-07", data={"category": "Assicurazioni"})
    assert response.status_code == 302
    budget = Budget.query.filter_by(category="Assicurazioni").one()
    assert budget.amount == Decimal("45.00") and budget.rollover_since == date(2026, 7, 1)
    assert "non è una categoria" in client.post("/lifestyle/budget/set-aside?month=2026-07", data={"category": "Alimentari"},
                                                follow_redirects=True).get_data(as_text=True)


def test_budget_page_saves_the_rollover_and_shows_the_carry(client, db):
    categories.ensure_defaults()
    client.post("/lifestyle/budget?month=2026-05", data={"category": ["Alimentari"], "every-Alimentari": "100",
                                                         "rollover-Alimentari": "on"})
    assert Budget.query.one().rollover_since == date(2026, 5, 1)
    _food(db, 70)
    html = client.get("/lifestyle/budget?month=2026-06").get_data(as_text=True)
    assert 'name="rollover-Alimentari" checked' in html and "di cui riportati" in html and "riportati" in html
    client.post("/lifestyle/budget?month=2026-06", data={"category": ["Alimentari"], "every-Alimentari": "100"})
    assert Budget.query.one().rollover_since is None
