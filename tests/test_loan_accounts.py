"""F34: a loan received is a debt account of its own — the money a giroconto, the installments interest + capital."""
from datetime import date

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.wealth import Debt
from app.services import accounts, wealth


def _bank(db):
    bank = Account(name="Fineco", kind="current", currency="EUR")
    db.session.add(bank)
    db.session.commit()
    return bank


def test_a_loan_received_on_an_account_is_a_giroconto_not_an_income(client, db):
    bank = _bank(db)
    client.post("/debt/new", data={"name": "Prestito auto", "type": "Prestito Auto", "principal": "6000", "annual_rate": "0",
                                   "term_months": "24", "start_date": "2026-01-10", "received_on": str(bank.id)})
    debt = Debt.query.one()
    received = Transaction.query.one()
    assert (received.type, received.account_id, received.counter_account_id, float(received.amount)) == (
        "transfer", debt.account_id, bank.id, 6000.0)
    assert debt.account.kind == "debt" and accounts.balance(bank) == 6000
    assert wealth.cash_balance() == 6000 and wealth.debt_summary(debt)["balance"] == 6000  # the cash, and as much owed
    assert wealth.balance_sheet()["net_worth"] == 0
    page = client.get(f"/debt/{debt.id}").get_data(as_text=True)
    assert "Registra la rata" in page and "dal conto del prestito" in page
    # the accounts page: the loan's account is not money
    assert "€ 6.000,00" in client.get("/accounts/").get_data(as_text=True)


def test_an_installment_splits_interest_and_capital(client, db):
    bank = _bank(db)
    debt = Debt(name="Mutuo", type="Mutuo", principal=12000, annual_rate=6, term_months=12, start_date=date(2026, 1, 1))
    db.session.add(debt)
    db.session.commit()
    client.post(f"/debt/{debt.id}/account")
    first = wealth.schedule(debt)[0]  # due 1 Feb: interest 60
    response = client.post(f"/debt/{debt.id}/payment", data={"amount": str(first.payment), "on": "2026-02-01",
                                                             "account_id": str(bank.id)}, follow_redirects=True)
    assert "Rata registrata" in response.get_data(as_text=True)
    interest = Transaction.query.filter_by(type="expense").one()
    capital = Transaction.query.filter_by(type="transfer").one()
    assert float(interest.amount) == 60.0 and interest.tags == ["Interessi"] and interest.category == "Prestito"
    assert float(capital.amount) == round(first.payment - 60, 2) and capital.counter_account_id == debt.account_id
    # the account owes nothing yet below zero (the money was not recorded as received): the debt follows the account
    assert wealth.balance_on(debt, date.today()) == 0.0


def test_payment_errors(client, db):
    bank = _bank(db)
    debt = Debt(name="Prestito", type="Prestito", principal=1000, annual_rate=0, term_months=10, start_date=date(2026, 1, 1))
    db.session.add(debt)
    db.session.commit()
    client.post(f"/debt/{debt.id}/account")
    for data in ({"amount": "0", "account_id": str(bank.id)}, {"amount": "50", "account_id": "999"}):
        page = client.post(f"/debt/{debt.id}/payment", data=data, follow_redirects=True).get_data(as_text=True)
        assert "alert" in page
    assert Transaction.query.count() == 0
    # at zero interest all of it is capital
    rows = wealth.loan_payment(debt, bank, 100, date(2026, 2, 1))
    assert [(r.type, float(r.amount)) for r in rows] == [("transfer", 100.0)]
    # the account is made once, its name unique
    db.session.add(Account(name="Altro", kind="current"))
    other = Debt(name="Prestito", type="Prestito", principal=500)
    db.session.add(other)
    db.session.flush()
    assert wealth.open_loan_account(other).name == "Prestito 2" and wealth.open_loan_account(other) is other.account
