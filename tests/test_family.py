"""F20f: whose things are — accounts, holdings and debts by holder, joint ones split, the rest to the family."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.wealth import Debt, Holding
from app.services import family, owners
from tests.conftest import make_tx


@pytest.fixture()
def household(app, db):
    with app.test_request_context():
        owners.set_holders(["Mario Rossi", "Anna Bianchi"])
    mine = Account(name="Conto Mario", kind="current", opening_balance=Decimal("1000"), owner="Mario Rossi")
    ours = Account(name="Conto comune", kind="current", opening_balance=Decimal("4000"), owner=family.JOINT)
    cash = Account(name="Contanti", kind="cash", opening_balance=Decimal("200"))
    db.session.add_all([mine, ours, cash,
                        Holding(name="ETF Anna", asset_class="ETF", quantity=10, avg_price=100, owner="Anna Bianchi"),
                        Holding(name="Casa", asset_class="Immobile", quantity=1, avg_price=300000, owner=family.JOINT),
                        Debt(name="Mutuo", type="Mutuo", principal=200000, balance=100000, owner=family.JOINT)])
    db.session.flush()
    db.session.add(make_tx(description="Esselunga di Mario", amount=Decimal("50"), account_id=mine.id))
    db.session.commit()
    return mine, ours, cash


def test_shares_and_choices(app, household):
    with app.test_request_context():
        assert family.choices() == [("Mario Rossi", "Mario Rossi"), ("Anna Bianchi", "Anna Bianchi"),
                                    ("joint", "Cointestato")]
        assert family.shares("joint") == {"Mario Rossi": 0.5, "Anna Bianchi": 0.5}
        assert family.shares("Mario Rossi") == {"Mario Rossi": 1.0}
        assert family.shares("Qualcun altro") == family.shares(None) == {"": 1.0}
        assert (family.label("joint"), family.label(None), family.label("Anna Bianchi")) == ("Cointestato", "Famiglia",
                                                                                          "Anna Bianchi")


def test_by_person(app, household):
    with app.test_request_context():
        rows = {r["person"]: r for r in family.by_person(date(2026, 10, 13))}
    assert list(rows) == ["Mario Rossi", "Anna Bianchi", ""]
    assert (rows["Mario Rossi"]["cash"], rows["Mario Rossi"]["other"], rows["Mario Rossi"]["debts"]) == (2950, 150000, 50000)
    assert rows["Mario Rossi"]["net"] == 102950  # 950 + 2.000 + half the house − half the mortgage
    assert (rows["Anna Bianchi"]["investments"], rows["Anna Bianchi"]["net"]) == (1000, 103000)
    assert rows[""]["cash"] == 200


def test_pages_and_filters(client, db, household):
    mine, ours, cash = household
    page = client.get("/accounting/balance-sheet").get_data(as_text=True)
    assert "Patrimonio per persona" in page and "Anna Bianchi" in page
    page = client.get("/portfolio/?person=Mario+Rossi").get_data(as_text=True)
    assert "Casa" in page and "ETF Anna" not in page
    page = client.get("/transactions/?person=Anna+Bianchi").get_data(as_text=True)
    assert "Esselunga di Mario" not in page
    assert "Esselunga di Mario" in client.get("/transactions/?person=Mario+Rossi").get_data(as_text=True)
    assert "Cointestato" in client.get("/accounts/").get_data(as_text=True)
    form = {"name": "Conto Mario", "kind": "current", "currency": "EUR", "opening_balance": "1000", "owner": "Anna Bianchi",
            "active": "1"}
    client.post(f"/accounts/{mine.id}/edit", data=form)
    assert db.session.get(Account, mine.id).owner == "Anna Bianchi"
    client.post(f"/accounts/{mine.id}/edit", data={**form, "owner": "Sconosciuto"})
    assert db.session.get(Account, mine.id).owner is None
    assert 'name="owner"' in client.get("/portfolio/new").get_data(as_text=True)
    assert 'name="owner"' in client.get("/debt/new").get_data(as_text=True)


def test_without_holders_nothing_shows(client, db):
    assert 'name="owner"' not in client.get("/accounts/new").get_data(as_text=True)
    assert "Patrimonio per persona" not in client.get("/accounting/balance-sheet").get_data(as_text=True)
