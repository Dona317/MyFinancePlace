"""F22: money between people — balances, sharing an expense, money given back, reminders, balance sheet."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.personal_loan import PersonalLoan
from app.services import analytics, categories, notifications, personal_loans, wealth
from tests.conftest import make_tx


def test_balances_and_due(app, db):
    personal_loans.add("Luca", "lent", Decimal(100), date(2026, 9, 1), "cena", due=date.today() + timedelta(days=3))
    personal_loans.add("luca ", "repaid_me", Decimal(40), date(2026, 9, 10))
    personal_loans.add("Luca", "repaid_me", Decimal(10), date(2026, 9, 11))
    personal_loans.add("Sara", "borrowed", Decimal(200), date(2026, 9, 5))
    personal_loans.add("Sara", "repaid_them", Decimal(50), date(2026, 9, 20))
    personal_loans.add("Anna", "lent", Decimal(30), date(2026, 9, 1))
    personal_loans.add("Anna", "repaid_me", Decimal(30), date(2026, 9, 2))
    db.session.commit()
    people = personal_loans.people()
    assert [(p.name, p.balance) for p in people] == [("Sara", -150), ("Luca", 50), ("Anna", 0)]  # «luca» is Luca
    assert personal_loans.totals() == {"owed_to_me": 50, "i_owe": 150}
    assert [p.name for p in personal_loans.due_soon()] == ["Luca"]
    with app.test_request_context():
        assert any(n.key.startswith("loan-Luca-") for n in notifications.collect())
    sheet = wealth.balance_sheet()
    assert sheet["other_assets"]["Crediti verso persone"] == 50
    assert sheet["current_liabilities"]["Debiti verso persone"] == 150
    for bad, message in ((("", "lent", Decimal(1)), "nome"), (("X", "boh", Decimal(1)), "cosa"),
                         (("X", "lent", Decimal(0)), "positivo")):
        with pytest.raises(ValueError, match=message):
            personal_loans.add(*bad, None)


def test_share_an_expense(db):
    categories.ensure_defaults()
    dinner = make_tx(date=date.today(), description="Cena al lago", amount=90, category="Ristoranti")
    db.session.add(dinner)
    db.session.commit()
    assert personal_loans.recent("expense") == [dinner]
    shares = personal_loans.equal_shares(Decimal(90), ["Luca", " Sara ", ""])
    assert shares == {"Luca": 30, "Sara": 30}
    made = personal_loans.share_expense(dinner, shares)
    db.session.commit()
    assert [(e.person, e.amount) for e in made] == [("Luca", 30), ("Sara", 30)]
    assert sorted((s.category, s.amount) for s in dinner.splits) == [("Anticipi per altri", 60), ("Ristoranti", 30)]
    assert "Anticipi per altri" in categories.excluded_names()
    spent = {i["category"]: i["amount"] for i in analytics.category_breakdown(date.today().replace(day=1),
                                                                               date.today() + timedelta(days=1))}
    assert spent == {"Ristoranti": 30}  # only my part is my spending
    assert personal_loans.recent("expense") == []  # already split
    with pytest.raises(ValueError, match="già suddivisa"):
        personal_loans.share_expense(dinner, {"Luca": Decimal(1)})
    other = make_tx(description="Benzina", amount=50)
    db.session.add(other)
    with pytest.raises(ValueError, match="meno del totale"):
        personal_loans.share_expense(other, {"Luca": Decimal(50)})
    with pytest.raises(ValueError, match="almeno una persona"):
        personal_loans.share_expense(other, {})
    with pytest.raises(ValueError, match="almeno una persona"):
        personal_loans.equal_shares(Decimal(10), [" "])
    with pytest.raises(ValueError, match="solo una spesa"):
        personal_loans.share_expense(make_tx(type="income"), {"Luca": Decimal(1)})


def test_money_given_back(db):
    categories.ensure_defaults()
    back = make_tx(date=date.today(), description="Bonifico da Luca", amount=30, type="income", category="Altro")
    db.session.add(back)
    db.session.commit()
    assert personal_loans.recent("income") == [back]
    entry = personal_loans.repayment(back, "Luca")
    db.session.commit()
    assert entry.amount == -30 and back.category == "Anticipi per altri" and personal_loans.recent("income") == []
    assert analytics.last_12_months()["income"][-1] == 0  # not my income
    with pytest.raises(ValueError, match="entrata"):
        personal_loans.repayment(make_tx(type="expense"), "Luca")


def test_pages(client, db):
    assert "Nessun prestito" in client.get("/loans/").get_data(as_text=True)
    client.post("/loans/new", data={"person": "Luca", "kind": "lent", "amount": "50", "date": "2026-10-01",
                                    "due": "2026-10-31", "description": "biglietti"})
    assert PersonalLoan.query.one().amount == 50
    assert "positivo" in client.post("/loans/new", data={"person": "Luca", "kind": "lent", "amount": "0"},
                                     follow_redirects=True).get_data(as_text=True)
    dinner = make_tx(date=date.today(), description="Pizza", amount=60, category="Ristoranti")
    back = make_tx(date=date.today(), description="Rimborso", amount=20, type="income")
    db.session.add_all([dinner, back])
    db.session.commit()
    page = client.get("/loans/").get_data(as_text=True)
    assert "ti deve" in page and "Pizza" in page and "Rimborso" in page
    client.post("/loans/share", data={"transaction_id": dinner.id, "people": "Luca, Sara"})
    assert PersonalLoan.query.filter_by(person="Sara").one().amount == 20
    client.post("/loans/share", data={"transaction_id": dinner.id, "people": "Luca"})  # already split: refused
    assert PersonalLoan.query.count() == 3
    pizza = make_tx(date=date.today(), description="Pizza 2", amount=60, category="Ristoranti")
    db.session.add(pizza)
    db.session.commit()
    client.post("/loans/share", data={"transaction_id": pizza.id, "people": "Luca", "each": "25"})
    assert PersonalLoan.query.filter_by(person="Luca", amount=25).count() == 1
    client.post("/loans/repaid", data={"transaction_id": back.id, "person": "Luca"})
    assert PersonalLoan.query.filter_by(amount=-20).count() == 1
    entry = PersonalLoan.query.filter_by(person="Sara").one()
    client.post(f"/loans/{entry.id}/delete")
    assert PersonalLoan.query.filter_by(person="Sara").count() == 0
