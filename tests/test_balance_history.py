"""F64: the balance of each account over time (the chart on the account page) and the running balance of its list."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.services import accounts
from tests.conftest import make_tx
from tests.form_helper import assert_divs_balanced

TODAY = date(2026, 6, 30)


@pytest.fixture()
def bank(db):
    fineco = Account(name="Fineco", kind="current", opening_balance=Decimal("1000"))
    card = Account(name="Carta", kind="prepaid", opening_balance=Decimal("0"))
    db.session.add_all([fineco, card])
    db.session.commit()
    db.session.add_all([
        make_tx(date=date(2025, 3, 1), description="Vecchia spesa", amount=50, account_id=fineco.id),  # before the window
        make_tx(date=date(2026, 6, 1), description="Stipendio", amount=2000, type="income", account_id=fineco.id),
        make_tx(date=date(2026, 6, 3), description="Affitto", amount=700, account_id=fineco.id),
        make_tx(date=date(2026, 6, 5), description="Ricarica carta", amount=100, type="transfer",
                account_id=fineco.id, counter_account_id=card.id),
        make_tx(date=date(2026, 6, 6), description="Giro su sé stesso", amount=999, type="transfer",
                account_id=fineco.id, counter_account_id=fineco.id),  # moves nothing
        make_tx(date=date(2026, 6, 8), description="Amazon", amount=30, account_id=card.id),
        # in dollars: counts with what the bank charged in euro
        make_tx(date=date(2026, 6, 10), description="Hotel NY", amount=50, currency="USD", account_id=fineco.id,
                account_amount=Decimal("46")),
        make_tx(date=date(2026, 6, 12), description="Senza conto", amount=20),
    ])
    db.session.commit()
    return fineco, card


def test_daily_history_by_hand(bank):
    fineco, card = bank
    history = accounts.balance_history(fineco, today=TODAY)
    assert history["daily"] is True
    assert history["days"][0] == "2025-07-01" and history["days"][-1] == "2026-06-30"
    assert len(history["values"]) == 365
    by_day = dict(zip(history["days"], history["values"], strict=True))
    assert by_day["2025-07-01"] == 950  # 1000 opening − 50 spent in March 2025
    assert by_day["2026-05-31"] == 950
    assert by_day["2026-06-01"] == 2950
    assert by_day["2026-06-03"] == 2250
    assert by_day["2026-06-05"] == 2150  # the transfer to the card leaves
    assert by_day["2026-06-06"] == 2150  # a transfer to itself moves nothing
    assert by_day["2026-06-10"] == 2104  # 46 € charged for the 50 $
    assert history["labels"][-1] == "30/06/26"
    card_history = accounts.balance_history(card, today=TODAY)
    card_values = dict(zip(card_history["days"], card_history["values"], strict=True))
    assert card_values["2026-06-05"] == 100 and card_values["2026-06-30"] == 70  # the transfer arrives


def test_last_point_is_the_balance(bank):
    for account in bank:
        assert accounts.balance_history(account)["values"][-1] == accounts.balance(account)
        assert accounts.balance_history(account, today=TODAY)["values"][-1] == accounts.balance(account, TODAY)


def test_monthly_points_for_a_long_range(bank):
    fineco, _ = bank
    history = accounts.balance_history(fineco, months=24, today=TODAY)
    assert history["daily"] is False
    assert history["days"][:2] == ["2024-07-31", "2024-08-31"] and history["days"][-1] == "2026-06-30"
    assert len(history["days"]) == 24
    by_month = dict(zip(history["days"], history["values"], strict=True))
    assert by_month["2025-02-28"] == 1000 and by_month["2025-03-31"] == 950
    assert by_month["2026-06-30"] == 2104


def test_running_balances_take_each_row_back(bank):
    fineco, _ = bank
    rows = [make_tx(date=date(2026, 6, 10), amount=46, account_id=fineco.id),
            make_tx(date=date(2026, 6, 9), amount=999, type="transfer", account_id=99, counter_account_id=fineco.id),
            make_tx(date=date(2026, 6, 1), amount=2000, type="income", account_id=fineco.id),
            make_tx(date=date(2026, 5, 1), amount=5, account_id=None, counter_account_id=fineco.id)]  # not a transfer
    assert accounts.running_balances(fineco, rows, 2104) == [2104, 2150, 1151, -849]


def test_account_page_has_chart_and_running_balance(client, bank):
    fineco, _ = bank
    html = client.get(f"/accounts/{fineco.id}").get_data(as_text=True)
    assert_divs_balanced(html)
    assert 'id="balanceChart"' in html and "Saldo negli ultimi 12 mesi" in html
    # newest first: after the hotel 2.104, after the transfer to itself still 2.150, after the rent 2.250
    rows = html.split("<tbody>", 1)[1]
    assert rows.index("€ 2.104,00") < rows.index("€ 2.150,00") < rows.index("€ 2.250,00") < rows.index("€ 950,00")
    # a reconciliation lists only the movements going out: no running balance there
    html = client.post(f"/accounts/{fineco.id}/reconcile", data={"on": "2026-06-04", "statement_balance": "2250"}
                       ).get_data(as_text=True)
    assert "Il saldo del conto dopo il movimento" not in html


def test_account_without_movements_has_no_chart(client, db):
    empty = Account(name="Vuoto", kind="current", opening_balance=Decimal("10"))
    db.session.add(empty)
    db.session.commit()
    html = client.get(f"/accounts/{empty.id}").get_data(as_text=True)
    assert 'id="balanceChart"' not in html
    assert accounts.balance_history(empty, months=1, today=TODAY)["values"] == [10.0] * 31  # 31 May to 30 June
