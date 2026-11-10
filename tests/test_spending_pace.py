"""F65: the spending pace of the month in the budget page, and the expenses of a year before on the dashboard."""
from datetime import date
from decimal import Decimal

from app.routes import dashboard
from app.services import budgets
from app.services.periods import month_bounds, month_index
from tests.conftest import make_tx
from tests.form_helper import assert_divs_balanced

JUNE = date(2026, 6, 1)


def spend(db, day, category, amount):
    db.session.add(make_tx(date=day, category=category, amount=amount))
    db.session.commit()


def june_budgets(db):
    budgets.save("Alimentari", Decimal("300"), None)
    budgets.save("Svago", Decimal("150"), None)
    db.session.commit()
    spend(db, date(2026, 6, 2), "Alimentari", 60)
    spend(db, date(2026, 6, 10), "Alimentari", 90)
    spend(db, date(2026, 6, 12), "Svago", 30)
    spend(db, date(2026, 6, 20), "Svago", 100)  # after «today»: not drawn yet
    spend(db, date(2026, 6, 3), "Casa", 500)  # no budget: left out
    spend(db, date(2026, 5, 5), "Alimentari", 40)
    spend(db, date(2026, 5, 31), "Alimentari", 20)  # day 31: June has 30


def test_pace_of_the_month_under_way(db):
    june_budgets(db)
    pace = budgets.pace(JUNE, today=date(2026, 6, 15))
    assert pace["days"] == 30 and pace["elapsed"] == 15 and pace["planned"] == 450
    assert pace["labels"][0] == "1" and pace["labels"][-1] == "30"
    actual = pace["actual"]
    assert actual[0] == 0 and actual[1] == 60 and actual[8] == 60 and actual[9] == 150 and actual[11] == 180
    assert actual[14] == 180 and actual[15:] == [None] * 15
    assert pace["spent"] == 180
    assert pace["projected"] == 360  # 180 in 15 days → 360 in 30
    assert pace["ideal"][0] == 15 and pace["ideal"][14] == 225 and pace["ideal"][-1] == 450
    previous = pace["previous"]
    assert len(previous) == 30 and previous[3] == 0 and previous[4] == 40 and previous[-1] == 40


def test_pace_of_a_past_and_a_future_month(db):
    june_budgets(db)
    past = budgets.pace(JUNE, today=date(2026, 7, 3))
    assert past["elapsed"] == 30 and past["actual"][-1] == 280 and past["projected"] is None
    future = budgets.pace(JUNE, today=date(2026, 5, 20))
    assert future["elapsed"] == 0 and future["actual"] == [None] * 30 and future["spent"] == 0
    assert future["projected"] is None


def test_shorter_month_before_keeps_its_total(db):
    budgets.save("Alimentari", Decimal("310"), None)
    db.session.commit()
    spend(db, date(2026, 2, 28), "Alimentari", 10)
    pace = budgets.pace(date(2026, 3, 1), today=date(2026, 3, 31))
    assert len(pace["previous"]) == 31 and pace["previous"][26] == 0 and pace["previous"][27:] == [10] * 4
    assert pace["ideal"][0] == 10  # 310 over 31 days


def test_no_budgets_no_pace(db):
    assert budgets.pace(JUNE, today=date(2026, 6, 15)) is None


def test_budget_page_draws_the_pace(client, db):
    june_budgets(db)
    html = client.get("/lifestyle/budget?month=2026-06").get_data(as_text=True)
    assert_divs_balanced(html)
    assert 'id="paceChart"' in html and "Ritmo di spesa" in html
    today = date.today()
    budgets.save("Svago", Decimal("150"), None)
    db.session.commit()
    spend(db, today, "Svago", 10)
    html = client.get(f"/lifestyle/budget?month={today:%Y-%m}").get_data(as_text=True)
    start, end = month_bounds(today.year, today.month)
    if today.day < (end - start).days:  # the last day of the month has no projection
        assert "A questo ritmo chiudi a" in html
    empty = client.get("/lifestyle/budget?month=2020-01").get_data(as_text=True)
    assert 'id="spending-pace"' in empty  # the every-month budgets apply to any month
    budgets.save("Svago", None, None)
    budgets.save("Alimentari", None, None)
    db.session.commit()
    assert 'id="spending-pace"' not in client.get("/lifestyle/budget?month=2020-01").get_data(as_text=True)


def test_dashboard_expenses_a_year_before(app, client, db):
    spend(db, date(2025, 6, 10), "Alimentari", 80)
    spend(db, date(2025, 7, 1), "Alimentari", 25)
    spend(db, date(2026, 6, 10), "Alimentari", 70)
    with app.test_request_context():
        flow = dashboard._flow(range(month_index(JUNE), month_index(JUNE) + 2))
    assert flow["expenses"] == [70, 0] and flow["expenses_previous"] == [80, 25]
    assert dashboard._flow(range(0))["expenses_previous"] == []
    assert "Uscite anno prima" in client.get("/dashboard").get_data(as_text=True)
