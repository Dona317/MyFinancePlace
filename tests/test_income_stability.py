"""F10b: how reliable each source of income is, over the last 12 complete months."""
from datetime import date

from app.services import analytics
from tests.conftest import make_tx

TODAY = date(2026, 10, 8)  # the window: October 2025 – September 2026


def _income(db, category, amounts, day=27):
    """`amounts` from October 2025 on, one per month (None: nothing that month)."""
    for k, amount in enumerate(amounts):
        year, month = divmod(2025 * 12 + 9 + k, 12)
        if amount:
            db.session.add(make_tx(date=date(year, month + 1, day), amount=amount, type="income", category=category))
    db.session.commit()


def test_sources_are_stable_variable_or_occasional(app, db):
    _income(db, "Stipendio", [2000] * 11 + [2100])
    _income(db, "Freelance", [300, None, 900, None, 200, 1200, None, 400, None, 700, None, 100])
    _income(db, "Vendite", [None] * 5 + [150])
    db.session.add(make_tx(date=date(2026, 10, 2), amount=5000, type="income", category="Vendite"))  # this month: out
    db.session.commit()
    with app.test_request_context():
        data = analytics.income_stability(TODAY)
    sources = {s["name"]: s for s in data["sources"]}
    assert [s["name"] for s in data["sources"]] == ["Stipendio", "Freelance", "Vendite"]
    assert sources["Stipendio"]["kind"] == "stable" and sources["Stipendio"]["months"] == 12
    assert sources["Stipendio"]["variation"] < 5
    assert sources["Freelance"]["kind"] == "variable" and sources["Freelance"]["months"] == 7
    assert sources["Vendite"]["kind"] == "occasional" and sources["Vendite"]["total"] == 150
    assert data["total"] == 24100 + 3800 + 150
    assert data["stable_share"] == round(24100 / data["total"] * 100, 1)


def test_a_steady_source_that_jumps_is_variable(app, db):
    _income(db, "Stipendio", [2000] * 6 + [3000] * 6)
    with app.test_request_context():
        [source] = analytics.income_stability(TODAY)["sources"]
    assert source["kind"] == "variable" and source["variation"] == 20.0


def test_no_income_and_income_without_category(app, db):
    with app.test_request_context():
        empty = analytics.income_stability(TODAY)
    assert empty["sources"] == [] and empty["stable_share"] is None
    _income(db, None, [100] * 12)
    with app.test_request_context():
        [source] = analytics.income_stability(TODAY)["sources"]
    assert source["name"] == "Senza categoria"


def test_forecast_page_shows_the_panel(client, db):
    _income(db, "Stipendio", [2000] * 12)
    html = client.get("/forecast/").get_data(as_text=True)
    assert "Stabilità delle entrate" in html and "Stipendio" in html  # the window follows today: no fixed counts here
