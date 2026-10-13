"""Monthly budgets per category, with warnings at 80% and when exceeded."""
from datetime import date
from decimal import Decimal

from app.models.budget import Budget
from app.services import budgets, categories
from tests.conftest import make_tx
from tests.form_helper import assert_divs_balanced

JUNE = date(2026, 6, 1)


def spend(db, category, amount, day=10):
    db.session.add(make_tx(date=date(2026, 6, day), category=category, amount=amount))
    db.session.commit()


def test_status_and_month_override(db):
    budgets.save("Alimentari", Decimal("400"), None)
    budgets.save("Svago", Decimal("100"), None)
    budgets.save("Svago", Decimal("300"), JUNE)  # a birthday month
    db.session.commit()
    spend(db, "Alimentari", 330)
    spend(db, "Svago", 120)
    lines = {line["category"]: line for line in budgets.status(JUNE, today=date(2026, 6, 15))}
    assert lines["Alimentari"]["state"] == "warning" and lines["Alimentari"]["left"] == 70
    assert lines["Svago"]["planned"] == 300 and lines["Svago"]["state"] == "ok"
    assert lines["Alimentari"]["pace"] == 50.0  # 15 of 30 days
    july = {line["category"]: line for line in budgets.status(date(2026, 7, 1))}
    assert july["Svago"]["planned"] == 100  # the override was for June only


def test_over_budget_alert_on_dashboard(client, db):
    today = date.today()
    budgets.save("Casa", Decimal("100"), None)
    db.session.commit()
    db.session.add(make_tx(date=today, category="Casa", amount=150))
    db.session.commit()
    assert budgets.alerts(today)[0]["state"] == "over"
    html = client.get("/dashboard").get_data(as_text=True)
    assert "Budget del mese" in html and "Casa" in html and "(superato)" in html


def test_budget_page_saves_and_removes(client, db):
    html = client.get("/lifestyle/budget?month=2026-06").get_data(as_text=True)
    assert_divs_balanced(html)
    assert "Alimentari" in html
    client.post("/lifestyle/budget?month=2026-06", data={"category": ["Alimentari", "Svago"],
                                                         "every-Alimentari": "450", "month-Svago": "1.200"})
    assert {(b.category, b.month, b.amount) for b in Budget.query} == {
        ("Alimentari", None, 450), ("Svago", JUNE, 1200)}
    client.post("/lifestyle/budget?month=2026-06", data={"category": ["Alimentari"], "every-Alimentari": ""})
    assert Budget.query.filter_by(category="Alimentari").count() == 0
    response = client.post("/lifestyle/budget?month=2026-06", data={"category": ["Svago"], "every-Svago": "tanto"},
                           follow_redirects=True)
    assert "non è un numero valido" in response.get_data(as_text=True)


def test_renamed_category_keeps_its_budget(db):
    budgets.save("Svago", Decimal("100"), None)
    db.session.commit()
    categories.rename("Svago", "Tempo libero")
    assert Budget.query.one().category == "Tempo libero"
    categories.delete("Tempo libero", None)
    assert Budget.query.count() == 0


def test_dashboard_category_legend_shows_amount_and_share(client, db):
    today = date.today()
    db.session.add_all([make_tx(date=today, category="Casa", amount=300), make_tx(date=today, category="Svago", amount=100)])
    db.session.commit()
    html = client.get("/dashboard").get_data(as_text=True)
    legend = html.split('<ul class="category-legend">')[1].split("</ul>")[0]
    # biggest first, each with the slice colour, the amount and its share of the month
    assert legend.index("Casa") < legend.index("Svago")
    assert "var(--chart-1)" in legend and "var(--chart-2)" in legend
    assert "(75%)" in legend and "(25%)" in legend
