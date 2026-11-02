"""
F19b: the operations of a holding (purchases, sales, dividends, coupons, fees, taxes), the position recomputed from
the opening one and the trades, and the returns (realized, unrealized, money-weighted XIRR).
"""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import portfolio_ops
from app.services.portfolio_ops import Operation


@pytest.fixture()
def setup(db):
    broker = Account(name="Directa", kind="other", fee_fixed=Decimal("1.5"), fee_percent=Decimal("0.19"),
                     fee_min=Decimal("1.5"), fee_max=Decimal("18"))
    etf = Holding(name="All-World", ticker="VWCE.DE", asset_class="ETF", quantity=10, avg_price=100,
                  opening_quantity=10, opening_price=100, opening_date=date(2025, 1, 2))
    db.session.add_all([broker, etf])
    db.session.commit()
    return broker, etf


def test_buy_sell_and_income_move_the_position(app, db, setup):
    broker, etf = setup
    with app.test_request_context():
        portfolio_ops.record(etf, Operation("buy", date(2025, 6, 2), broker, units=Decimal(10), price=Decimal(120),
                                            fee=Decimal("2.28")))
        assert (etf.quantity, etf.avg_price) == (Decimal(20), Decimal("110.114000"))  # (1000 + 1200 + 2,28) / 20
        portfolio_ops.record(etf, Operation("sell", date(2025, 9, 1), broker, units=Decimal(5), price=Decimal(130)))
        assert (etf.quantity, etf.avg_price) == (Decimal(15), Decimal("110.114000"))  # a sale keeps the average
        portfolio_ops.record(etf, Operation("dividend", date(2025, 12, 1), broker, amount=Decimal("12.40")))
        portfolio_ops.record(etf, Operation("tax", date(2025, 12, 31), broker, amount=Decimal("2")))
        db.session.commit()
    trades = portfolio_ops.trades(etf)
    assert [(t.type, t.units, t.account_id, t.counter_account_id) for t in trades] == [
        ("transfer", Decimal(10), broker.id, None), ("transfer", Decimal(-5), None, broker.id)]
    assert trades[0].description == "Acquisto 10 All-World" and trades[0].amount == Decimal("1200.00")
    kinds = [portfolio_ops.kind_of(t) for t in portfolio_ops.operations(etf)]
    assert kinds == ["tax", "dividend", "sell", "fee", "buy"]  # newest first; the buy's commission is listed too
    assert etf.price_date == date(2025, 9, 1)  # the trades' prices went into the history


def test_editing_or_deleting_a_trade_recomputes(client, db, setup):
    broker, etf = setup
    with client.application.test_request_context():
        portfolio_ops.record(etf, Operation("buy", date(2025, 6, 2), broker, units=Decimal(10), price=Decimal(120)))
        db.session.commit()
    trade = portfolio_ops.trades(etf)[0]
    form = {"date": "2025-06-02", "description": trade.description, "amount": "1200", "type": "transfer",
            "category": "Investimenti", "account_id": str(broker.id), "holding_id": str(etf.id), "units": "20",
            "unit_price": "110"}
    assert client.post(f"/transactions/{trade.id}/edit", data=form).status_code == 302
    db.session.refresh(etf)
    assert (etf.quantity, etf.avg_price) == (Decimal(30), Decimal("106.666667"))  # (1000 + 2200) / 30
    client.post(f"/transactions/{trade.id}/delete")
    db.session.refresh(etf)
    assert (etf.quantity, etf.avg_price) == (Decimal(10), Decimal("100.000000"))  # back to the opening position


def test_wrong_operations_are_refused(app, db, setup):
    broker, etf = setup
    with app.test_request_context():
        for op, message in ((Operation("sell", date(2025, 1, 5), broker, units=Decimal(11), price=Decimal(1)), "più quote"),
                            (Operation("buy", date(2025, 1, 5), broker, units=Decimal(0), price=Decimal(1)), "maggiori di zero"),
                            (Operation("buy", date(2025, 1, 5), broker, units=Decimal(1), price=Decimal(1), fee=Decimal(-1)), "negativa"),
                            (Operation("coupon", date(2025, 1, 5), broker), "importo"),
                            (Operation("swap", date(2025, 1, 5), broker), "sconosciuto")):
            with pytest.raises(ValueError, match=message):
                portfolio_ops.record(etf, op)
            db.session.rollback()


def test_xirr():
    assert portfolio_ops.xirr([(date(2025, 1, 1), -1000), (date(2026, 1, 1), 1100)]) == 10.0
    assert portfolio_ops.xirr([(date(2025, 1, 1), -1000), (date(2025, 7, 2), -1000), (date(2026, 1, 1), 2100)]) \
        == pytest.approx(6.7, abs=0.1)
    assert portfolio_ops.xirr([(date(2025, 1, 1), -1000)]) is None
    assert portfolio_ops.xirr([(date(2025, 1, 1), 1000), (date(2026, 1, 1), 1100)]) is None  # all money out
    assert portfolio_ops.xirr([(date(2025, 1, 1), -1), (date(2025, 1, 2), 10 ** 9)]) is None  # beyond any rate


def test_performance_and_the_holding_page(client, db, setup):
    broker, etf = setup
    with client.application.test_request_context():
        portfolio_ops.record(etf, Operation("sell", date(2025, 7, 1), broker, units=Decimal(4), price=Decimal(125)))
        portfolio_ops.record(etf, Operation("coupon", date(2025, 8, 1), broker, amount=Decimal(10)))
        etf.current_price = Decimal(130)
        db.session.commit()
        perf = portfolio_ops.performance([etf], date(2026, 1, 2))
    assert perf["unrealized"] == 180.0 and perf["realized"] == 100.0 and perf["income"] == 10.0
    assert perf["xirr"] > 25  # 1000 in, 500 + 10 out, 780 left after a year
    page = client.get(f"/portfolio/{etf.id}").get_data(as_text=True)
    assert "Rendimento annuo" in page and "Posizione iniziale: 10" in page and "Cedola" in page and "Vendita" in page
    assert f"/portfolio/{etf.id}" in client.get("/portfolio/").get_data(as_text=True)  # linked from the list


def test_the_operation_page(client, db, setup):
    broker, etf = setup
    page = client.get(f"/portfolio/{etf.id}/operation").get_data(as_text=True)
    assert "Directa" in page and '"fixed": 1.5' in page  # the commission rule for the live estimate
    client.post(f"/portfolio/{etf.id}/operation", data={"kind": "buy", "on": "2025-03-03", "units": "5", "price": "110",
                                                        "account_id": str(broker.id), "fee": "1,5"})
    db.session.refresh(etf)
    assert etf.quantity == Decimal(15) and Transaction.query.filter_by(category="Commissioni").count() == 1
    wrong = client.post(f"/portfolio/{etf.id}/operation", data={"kind": "sell", "on": "2025-03-04", "units": "99",
                                                                "price": "1"})
    assert wrong.status_code == 400 and "più quote" in wrong.get_data(as_text=True)
    client.post(f"/portfolio/{etf.id}/operation", data={"kind": "dividend", "on": "2025-03-05", "amount": "3,2"})
    assert Transaction.query.filter_by(category="Dividendi e cedole").one().account_id is None


def test_a_new_position_already_owned(client, db):
    client.post("/portfolio/new", data={"name": "Enel", "ticker": "ENEL.MI", "asset_class": "Azione", "quantity": "100",
                                        "avg_price": "5,8", "purchase_date": "2024-02-01"})
    enel = Holding.query.one()
    assert (enel.opening_quantity, enel.opening_price, enel.opening_date) == (Decimal(100), Decimal("5.8"), date(2024, 2, 1))
    # the form edits the opening position; the operations recorded move the holding from there
    with client.application.test_request_context():
        portfolio_ops.record(enel, Operation("buy", date(2025, 1, 2), None, units=Decimal(50), price=Decimal(7)))
        db.session.commit()
    assert 'value="100"' in client.get(f"/portfolio/{enel.id}/edit").get_data(as_text=True)
    client.post(f"/portfolio/{enel.id}/edit", data={"name": "Enel", "ticker": "ENEL.MI", "asset_class": "Azione",
                                                    "quantity": "200", "avg_price": "6"})
    db.session.refresh(enel)
    assert (enel.opening_quantity, enel.quantity, enel.avg_price) == (Decimal(200), Decimal(250), Decimal("6.200000"))


def test_opening_from_now(db, setup):
    _broker, etf = setup
    db.session.add(Transaction(date=date(2025, 2, 1), description="buy", amount=500, type="transfer",
                               holding_id=etf.id, units=4, unit_price=125))
    db.session.commit()
    portfolio_ops.opening_from_now(etf)
    assert etf.opening_quantity == Decimal(6)
