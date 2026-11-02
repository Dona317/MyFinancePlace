"""F22: categories left out of the analyses but not of the balances."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.category import Category
from app.models.transaction import TransactionSplit
from app.services import accounts, analytics, categories, spending_rhythm
from app.services.totals import excluded_total, value_total
from tests.conftest import make_tx


@pytest.fixture()
def book(db):
    categories.ensure_defaults()
    work = Category(name="Rimborsi lavoro", kind="both", excluded=True)
    db.session.add(work)
    db.session.flush()
    db.session.add(Category(name="Trasferte", kind="expense", parent_id=work.id))
    bank = Account(name="Banca")
    db.session.add(bank)
    db.session.flush()
    split = make_tx(date=date(2026, 6, 20), description="Cena", amount=100, category="Ristoranti", account_id=bank.id)
    split.splits = [TransactionSplit(category="Ristoranti", amount=Decimal(60)),
                    TransactionSplit(category="Trasferte", amount=Decimal(40))]
    db.session.add_all([
        make_tx(date=date(2026, 6, 1), description="Stipendio", amount=3000, type="income", category="Stipendio",
                account_id=bank.id),
        make_tx(date=date(2026, 6, 5), description="Treno Milano", amount=200, category="Trasferte", account_id=bank.id),
        make_tx(date=date(2026, 6, 25), description="Rimborso trasferta", amount=200, type="income",
                category="Rimborsi lavoro", account_id=bank.id),
        make_tx(date=date(2026, 6, 10), description="Spesa", amount=300, category="Spesa", account_id=bank.id),
        split,
    ])
    db.session.commit()
    return bank


def test_names_with_subcategories(book):
    assert categories.excluded_names() == ["Rimborsi lavoro", "Trasferte"]


def test_analyses_leave_them_out(book):
    june = (date(2026, 6, 1), date(2026, 7, 1))
    spent = {item["category"]: item["amount"] for item in analytics.category_breakdown(*june)}
    assert spent == {"Spesa": 300, "Ristoranti": 60}  # the split's work part is out too
    assert value_total(analytics.Transaction.type == "income") == 3000
    assert spending_rhythm.by_category(date(2026, 6, 1), date(2026, 6, 30)) == {"Spesa": 300, "Ristoranti": 60}
    flows = analytics.last_12_months(date(2026, 6, 30))
    assert flows["income"][-1] == 3000 and flows["expenses"][-1] == 400
    assert excluded_total(analytics.Transaction.type == "expense") == 240
    assert accounts.balance(book) == 3000 - 200 + 200 - 300 - 100  # balances count everything


def test_reports_page_and_settings(client, book, db):
    page = client.get("/reports/?period=custom&start=2026-06-01&end=2026-06-30").get_data(as_text=True)
    assert "Escluse dalle analisi" in page and "Treno Milano" not in page
    page = client.get("/reports/?period=custom&start=2026-06-01&end=2026-06-30&category=Trasferte").get_data(as_text=True)
    assert "Treno Milano" in page  # asked for by name: shown
    settings = client.get("/settings/categories").get_data(as_text=True)
    assert 'name="excluded"' in settings
    client.post("/settings/categories/save", data={"old_name": "Rimborsi lavoro", "name": "Rimborsi lavoro", "kind": "both"})
    assert categories.excluded_names() == []
    client.post("/settings/categories/save", data={"name": "Per altri", "kind": "expense", "excluded": "on"})
    assert Category.query.filter_by(name="Per altri").one().excluded and categories.excluded_names() == ["Per altri"]
    assert "Escluse dalle analisi" not in client.get("/reports/?period=custom&start=2026-06-01&end=2026-06-30").get_data(as_text=True)
