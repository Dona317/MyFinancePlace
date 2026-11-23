"""Transazioni → Investimenti: the trades of securities in a tab of their own, and movements moved there."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import investment_moves, wealth
from tests.conftest import make_tx


def _fineco(db):
    account = Account(name="Fineco", kind="current", opening_balance=Decimal("10000"))
    db.session.add(account)
    db.session.commit()
    return account


def test_a_purchase_moved_keeps_the_cash_and_records_units_price_and_fee(app, db):
    fineco = _fineco(db)
    tx = make_tx(description="Bonifico a Fineco titoli", amount=Decimal("5000"), account_id=fineco.id)
    db.session.add(tx)
    db.session.commit()
    before = wealth.cash_balance()
    vwce = investment_moves.holding_named("Vanguard FTSE All-World")
    investment_moves.move(tx, vwce, Decimal("40"), None, Decimal("2.95"))
    db.session.commit()
    assert tx.type == "transfer" and tx.units == 40 and tx.amount == Decimal("4997.05")
    assert tx.unit_price == pytest.approx(Decimal("4997.05") / 40)
    fee = Transaction.query.filter_by(fee_for_id=tx.id).one()
    assert fee.amount == Decimal("2.95") and fee.account_id == fineco.id
    assert wealth.cash_balance() == pytest.approx(before)  # 5.000 € left the account: 4.997,05 + 2,95
    assert float(db.session.get(Holding, vwce.id).quantity) == 40
    # an investment, not a spending: the commission is not in the month's expenses
    from app.services import analytics
    assert analytics.totals(date(2026, 6, 1), date(2026, 7, 1))["expenses"] == 0


def test_a_sale_and_the_checks(app, db):
    fineco = _fineco(db)
    sale = make_tx(description="Vendita titoli", amount=Decimal("1000"), type="income", account_id=fineco.id)
    db.session.add(sale)
    db.session.commit()
    etf = investment_moves.holding_named("IE00BK5BQT80")
    assert etf.isin == "IE00BK5BQT80" and investment_moves.holding_named("ie00bk5bqt80").id == etf.id
    investment_moves.move(sale, etf, None, Decimal("100"), Decimal("5"))
    assert sale.units == Decimal("-10.05") and sale.amount == Decimal("1005")  # sold for 1.005, 5 of commission
    with pytest.raises(ValueError):
        investment_moves.move(sale, etf, Decimal("1"), Decimal("1"))  # already an operation
    other = make_tx(amount=Decimal("10"), account_id=fineco.id)
    db.session.add(other)
    with pytest.raises(ValueError):
        investment_moves.move(other, etf, None, None)
    with pytest.raises(ValueError):
        investment_moves.move(other, etf, Decimal("1"), None, Decimal("20"))  # a commission bigger than the movement
    with pytest.raises(ValueError):
        investment_moves.holding_named("  ")


def test_the_tab_and_the_move_from_the_register(client, db):
    fineco = _fineco(db)
    tx = make_tx(description="Acquisto VWCE", amount=Decimal("5000"), account_id=fineco.id, date=date(2026, 11, 3))
    keep = make_tx(description="Spesa", amount=Decimal("40"), account_id=fineco.id)
    db.session.add_all([tx, keep])
    db.session.commit()
    page = client.post("/transactions/investments/move", data={"ids": [str(tx.id)]}).get_data(as_text=True)
    assert "Acquisto VWCE" in page and f'name="units-{tx.id}"' in page
    done = client.post("/transactions/investments/move", data={
        "ids": [str(tx.id)], "save": "1", f"holding-{tx.id}": "VWCE", f"units-{tx.id}": "40", f"price-{tx.id}": "",
        f"fee-{tx.id}": "2,95"})
    assert done.status_code == 302 and done.headers["Location"].endswith("/transactions/investments")
    tab = client.get("/transactions/investments").get_data(as_text=True)
    assert "VWCE" in tab and "Investimenti" in tab
    register = client.get("/transactions/").get_data(as_text=True)
    assert "Acquisto VWCE" in register and "Spesa" in register  # it stays in the list, marked
    assert register.count('class="tx-invest-mark"') == 2  # the trade and its commission, marked
    # a row without units nor price is shown again with the error, nothing saved
    other = make_tx(description="Bonifico broker", amount=Decimal("100"), account_id=fineco.id)
    db.session.add(other)
    db.session.commit()
    again = client.post("/transactions/investments/move", data={
        "ids": [str(other.id)], "save": "1", f"holding-{other.id}": "VWCE", f"units-{other.id}": "", f"price-{other.id}": ""})
    assert again.status_code == 200 and "quote o il prezzo" in again.get_data(as_text=True)
    assert db.session.get(Transaction, other.id).units is None
