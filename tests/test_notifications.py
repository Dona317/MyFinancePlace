"""Reminders: policy expiries, upcoming recurring transactions and installments, budgets, goals."""
from datetime import date, timedelta
from decimal import Decimal

from app.models.wealth import Debt, Goal, InsurancePolicy
from app.services import budgets, notifications
from tests.conftest import make_tx
from tests.form_helper import assert_divs_balanced

TODAY = date.today()



def test_collects_every_kind(app, db):
    db.session.add_all([
        InsurancePolicy(type="Auto", company="Unipol", premium=Decimal("300"), expiry_date=TODAY + timedelta(days=10)),
        InsurancePolicy(type="Casa", company="Generali", premium=Decimal("200"), expiry_date=TODAY + timedelta(days=200)),
        make_tx(date=TODAY - timedelta(days=28), description="Palestra", amount=40, is_recurring=True, recurrence="monthly"),
        Debt(name="Mutuo", type="Mutuo", principal=Decimal("10000"), annual_rate=0, term_months=100,
             start_date=TODAY - timedelta(days=27)),
        Goal(name="Viaggio", target_amount=Decimal("1000"), saved_amount=Decimal("100"), target_date=TODAY + timedelta(days=20)),
        Goal(name="Vecchio", target_amount=Decimal("1000"), saved_amount=Decimal("100"), target_date=TODAY - timedelta(days=3)),
    ])
    budgets.save("Svago", Decimal("50"), None)
    db.session.commit()
    db.session.add(make_tx(date=TODAY, category="Svago", amount=60))
    db.session.commit()

    with app.test_request_context():
        items = notifications.collect()
    titles = " | ".join(n.title for n in items)
    assert "Polizza Auto · Unipol" in titles and "Generali" not in titles  # 200 days away: not yet
    assert "Spesa ricorrente: Palestra" in titles
    assert "Rata Mutuo" in titles
    assert "Budget Svago superato" in titles
    assert "Obiettivo «Viaggio» tra 20 giorni" in titles and "Obiettivo «Vecchio» scaduto" in titles
    assert items[0].level == "danger"  # most urgent first


def test_dismiss_and_bell(client, db):
    db.session.add(InsurancePolicy(type="Auto", company="Unipol", premium=Decimal("300"),
                                   expiry_date=TODAY + timedelta(days=5)))
    db.session.commit()
    html = client.get("/dashboard").get_data(as_text=True)
    assert 'class="bell-count">1<' in html
    page = client.get("/notifications/").get_data(as_text=True)
    assert_divs_balanced(page)
    assert "Polizza Auto · Unipol" in page
    key = client.get("/notifications/api").get_json()["notifications"][0]["key"]
    client.post("/notifications/dismiss", data={"key": key})
    assert client.get("/notifications/api").get_json()["notifications"] == []
    assert "bell-count" not in client.get("/dashboard").get_data(as_text=True)
    assert "Già visti (1)" in client.get("/notifications/").get_data(as_text=True)


def test_disabled_modules_give_no_reminders(client, db):
    from app.routes.settings import DEFAULT_SETTINGS
    db.session.add(InsurancePolicy(type="Auto", company="Unipol", premium=Decimal("300"),
                                   expiry_date=TODAY + timedelta(days=5)))
    db.session.commit()
    form = {k: "on" for k, v in DEFAULT_SETTINGS.items() if v is True and k != "module_insurance"}
    client.post("/settings/save", data=form)
    assert client.get("/notifications/api").get_json()["notifications"] == []


def test_empty_page(client, db):
    assert "Nessun promemoria" in client.get("/notifications/").get_data(as_text=True)


def test_the_bell_window_dismisses_in_place(client, db):
    """The X in the bell's window hides the reminder without leaving the page: the window stays open and reloads its
    list, the bell's number follows (checked in a browser on 22 Nov 2026)."""
    for company in ("Unipol", "Allianz"):
        db.session.add(InsurancePolicy(type="Auto", company=company, premium=Decimal("300"),
                                       expiry_date=TODAY + timedelta(days=5)))
    db.session.commit()
    peek = client.get("/notifications/peek?back=/dashboard").get_data(as_text=True)
    assert 'data-total="2"' in peek
    key = client.get("/notifications/api").get_json()["notifications"][0]["key"]
    response = client.post("/notifications/dismiss", data={"key": key, "next": "/dashboard"},
                           headers={"X-Requested-With": "fetch"})
    assert response.status_code == 204
    assert 'data-total="1"' in client.get("/notifications/peek").get_data(as_text=True)
    page = client.get("/dashboard").get_data(as_text=True)
    assert "body.addEventListener('submit'" in page and "'X-Requested-With': 'fetch'" in page
