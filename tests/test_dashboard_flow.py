"""Dashboard: monthly net, yearly three-bar total and the Sankey of where the money goes."""
from datetime import date

from app.services import analytics
from tests.conftest import make_tx

YEAR = (date(2026, 1, 1), date(2027, 1, 1))


def _year(db, spend_more=False):
    db.session.add_all([
        make_tx(date=date(2026, 1, 27), category="Stipendio", type="income", amount=2000),
        make_tx(date=date(2026, 2, 15), category="Freelance", type="income", amount=500),
        make_tx(date=date(2026, 1, 5), category="Casa", amount=800),
        make_tx(date=date(2026, 2, 5), category="Alimentari", amount=3000 if spend_more else 300),
        make_tx(date=date(2026, 2, 6), category="Giroconto", type="transfer", amount=1000),  # not in the flow
    ])
    db.session.commit()


def test_sankey_flows_from_income_to_expenses_and_savings(app, db):
    _year(db)
    with app.test_request_context():
        flow = analytics.sankey(*YEAR)
    names = [(n["label"], n["amount"], n["kind"]) for n in flow["nodes"]]
    assert names == [("Stipendio", 2000.0, "income"), ("Freelance", 500.0, "income"), ("Entrate", 2500.0, "total"),
                     ("Casa", 800.0, "expense"), ("Alimentari", 300.0, "expense"), ("Risparmio", 1400.0, "expense")]
    assert len(flow["bands"]) == 5 and all(b["d"].startswith("M") and b["d"].endswith("Z") for b in flow["bands"])
    left = [n for n in flow["nodes"] if n["kind"] == "income"]
    right = [n for n in flow["nodes"] if n["kind"] == "expense"]
    assert abs(sum(n["h"] for n in left) - sum(n["h"] for n in right)) < 1  # both sides carry the same total
    assert right[-1]["special"] and right[-1]["color"] == "positive"


def test_sankey_when_spending_more_than_earning(app, db):
    _year(db, spend_more=True)
    with app.test_request_context():
        flow = analytics.sankey(*YEAR)
    assert ("Dai risparmi", 1300.0) in [(n["label"], n["amount"]) for n in flow["nodes"] if n["kind"] == "income"]
    assert "Risparmio" not in [n["label"] for n in flow["nodes"]]


def test_sankey_groups_the_smallest_categories(app, db):
    db.session.add(make_tx(date=date(2026, 3, 1), category="Stipendio", type="income", amount=10000))
    db.session.add_all([make_tx(date=date(2026, 3, 2), category=f"Cat {i}", amount=100 + i) for i in range(10)])
    db.session.commit()
    with app.test_request_context():
        flow = analytics.sankey(*YEAR)
    right = [n["label"] for n in flow["nodes"] if n["kind"] == "expense"]
    assert len(right) == analytics.SANKEY_SIDE + 2 and right[-2:] == ["Altre", "Risparmio"]


def test_nothing_to_draw(app, db):
    with app.test_request_context():
        assert analytics.sankey(*YEAR) is None


def test_dashboard_shows_the_new_charts_and_they_can_be_hidden(client, db):
    _year(db)
    html = client.get("/dashboard?year=2026").get_data(as_text=True)
    assert 'class="sankey"' in html and "Dove va il denaro" in html and "Risparmio" in html
    assert 'id="netChart"' in html and 'id="yearChart"' in html
    client.post("/settings/save", data={})  # every checkbox unticked
    html = client.get("/dashboard?year=2026").get_data(as_text=True)
    assert 'class="sankey"' not in html and 'id="netChart"' not in html


def test_savings_rate_month_by_month(app, db):
    _year(db)
    with app.test_request_context():
        rates = analytics.savings_rates(2026, 3)
    assert rates["current"] == [60.0, 40.0, None]  # January 2000 − 800, February 500 − 300, March no income
    assert rates["year_rate"] == 56.0 and rates["previous"] is None and rates["previous_rate"] is None
    db.session.add_all([make_tx(date=date(2025, 1, 10), category="Stipendio", type="income", amount=1000),
                        make_tx(date=date(2025, 1, 12), category="Casa", amount=900)])
    db.session.commit()
    with app.test_request_context():
        rates = analytics.savings_rates(2026, 3)
    assert rates["previous"] == [10.0, None, None] and rates["previous_rate"] == 10.0


def test_savings_rate_card_and_its_switch(client, db):
    _year(db)
    html = client.get("/dashboard?year=2026").get_data(as_text=True)
    assert 'id="savingsChart"' in html and "2026: 56%" in html
    client.post("/settings/save", data={"dashboard_net": "on"})
    html = client.get("/dashboard?year=2026").get_data(as_text=True)
    assert 'id="savingsChart"' not in html and 'id="netChart"' in html
