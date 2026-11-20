"""«Bridge del mese» (it was «Ponte del mese») (18–21 Nov 2026): only real income and spending — giroconti, cash taken out and reconciliations
stay out — on the month of the shared period, which the card names."""
from datetime import date
from decimal import Decimal

from app.models.account import Account
from app.services import accounts, dashboard_charts
from tests.conftest import make_tx


def test_the_bridge_counts_only_real_income_and_spending(app, db):
    bank, savings = Account(name="Intesa", kind="current"), Account(name="Fineco", kind="current")
    db.session.add_all([bank, savings])
    db.session.commit()
    db.session.add_all([
        make_tx(date=date(2026, 10, 27), amount=1584, type="income", category="Stipendio", account_id=bank.id),
        make_tx(date=date(2026, 10, 1), amount=200, category="Spese mediche", account_id=bank.id),
        make_tx(date=date(2026, 10, 27), amount=1000, type="transfer", category="Giroconto", account_id=bank.id,
                counter_account_id=savings.id),  # moved to savings: still the user's money
        make_tx(date=date(2026, 11, 15), amount=1369, type="income", account_id=bank.id,
                category=accounts.RECONCILIATION, tags=[accounts.RECONCILIATION_TAG]),
        make_tx(date=date(2026, 11, 15), amount=777, account_id=savings.id,
                category=accounts.RECONCILIATION, tags=[accounts.RECONCILIATION_TAG]),
        make_tx(date=date(2026, 11, 4), amount=Decimal("59.04"), category="Spese mediche", account_id=bank.id),
    ])
    db.session.commit()
    with app.test_request_context():
        accounts.reconciliation_category()  # the category exists and is left out of the analyses
        october = dashboard_charts.month_bridge(date(2026, 11, 21), date(2026, 10, 1))
        november = dashboard_charts.month_bridge(date(2026, 11, 21))
    assert october["income"] == 1584 and october["left"] == 1384  # the giroconto is not spending
    assert october["steps"][-1] == {"label": "Risparmi", "low": 0.0, "high": 1384.0, "kind": "left"}
    assert not october["current"] and "26" in october["month"]
    assert november["income"] == 0 and november["left"] == -59.04 and november["current"]  # no reconciliation
    # spent more than came in: the rest taken from the savings, on top of the income; the bridge ends at zero
    assert [s["kind"] for s in november["steps"]] == ["income", "drawn", "expense"]
    assert november["steps"][1] == {"label": "Presi dai risparmi", "low": 0.0, "high": 59.04, "kind": "drawn"}
    assert november["steps"][-1]["low"] == 0.0 and all(s["low"] >= 0 for s in november["steps"])


def test_the_dashboard_shows_the_month_of_the_shared_period(client, db):
    db.session.add(make_tx(date=date(2025, 3, 10), amount=40, category="Spese mediche"))
    db.session.commit()
    client.post("/dashboard/layout?view=month", json={"widgets": [{"id": "bridge", "span": 1}]})
    page = client.get("/dashboard?view=month&year=2025&part=year").get_data(as_text=True)
    card = page[page.index("Bridge del mese"):][:1500]
    assert "Dic 25" in card and "l’ultimo mese del periodo in alto" in card
    page = client.get("/dashboard?view=month&year=2025&part=M03").get_data(as_text=True)
    assert "Mar 25" in page[page.index("Bridge del mese"):][:1500]
