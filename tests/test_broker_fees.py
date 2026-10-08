"""F17: trades entered in units, with the broker's commission computed from its rules and confirmed by the user."""
from decimal import Decimal

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.wealth import Holding, HoldingPrice
from app.services import accounts, broker, wealth


def _setup(db, **rule):
    directa = Account(name="Directa", kind="other", opening_balance=Decimal(5000), **rule)
    etf = Holding(name="ETF World", ticker="VWCE", asset_class="ETF", quantity=Decimal(10), avg_price=Decimal(100))
    db.session.add_all([directa, etf])
    db.session.commit()
    return directa, etf


def test_commission_rule():
    rule = Account(name="x", fee_fixed=Decimal("1.50"), fee_percent=Decimal("0.19"), fee_min=Decimal("2.95"),
                   fee_max=Decimal("19"))
    assert broker.commission(rule, Decimal(500)) == Decimal("2.95")      # 1,50 + 0,95 → the minimum
    assert broker.commission(rule, Decimal(2000)) == Decimal("5.30")     # 1,50 + 3,80
    assert broker.commission(rule, Decimal(20000)) == Decimal("19.00")   # capped
    assert broker.commission(Account(name="y"), Decimal(1000)) is None   # no rule
    assert broker.commission(None, Decimal(1000)) is None
    assert broker.commission(Account(name="z", fee_fixed=Decimal(5)), Decimal(-100)) == Decimal("5.00")
    assert broker.rules([rule, Account(id=9, name="w")]) == {rule.id: {"fixed": 1.5, "percent": 0.19, "min": 2.95, "max": 19.0}}


def _trade(client, account, holding, **changes):
    data = {"date": "2026-09-12", "description": "Acquisto VWCE", "amount": "", "currency": "EUR",
            "account_id": str(account.id), "holding_id": str(holding.id), "trade_side": "buy", "units": "10",
            "unit_price": "120", "fee_amount": "5,30", "record_fee": "on", "update_holding": "on"}
    data.update(changes)
    return client.post("/transactions/new", data={k: v for k, v in data.items() if v is not None})


def test_a_purchase_in_units_with_its_commission(client, db):
    directa, etf = _setup(db, fee_fixed=Decimal("1.50"), fee_percent=Decimal("0.19"))
    response = _trade(client, directa, etf)
    assert response.status_code == 302
    trade = Transaction.query.filter_by(description="Acquisto VWCE").one()
    assert (trade.type, trade.amount, trade.units, trade.unit_price) == ("transfer", Decimal("1200.00"), Decimal(10), Decimal(120))
    assert trade.category == "Investimenti" and trade.account_id == directa.id and trade.counter_account_id is None
    fee = Transaction.query.filter_by(fee_for_id=trade.id).one()
    assert (fee.type, fee.amount, fee.category, fee.account_id) == ("expense", Decimal("5.30"), "Commissioni", directa.id)
    assert fee.description == "Commissione Directa: Acquisto VWCE" and "commissione" in fee.tags
    db.session.refresh(etf)
    assert etf.quantity == 20 and etf.avg_price == Decimal("110.265000")  # (1000 + 1200 + 5,30) / 20
    assert HoldingPrice.query.one().price == 120
    with client.application.test_request_context():
        assert accounts.balance(directa) == 5000 - 1200 - 5.30
        assert wealth.cash_balance() == 5000 - 1200 - 5.30  # the purchase left the cash, the commission is an expense
    db.session.delete(trade)
    db.session.commit()
    assert Transaction.query.filter_by(fee_for_id=trade.id).count() == 0  # the commission goes with its trade


def test_a_sale_arrives_on_the_broker_account(client, db):
    directa, etf = _setup(db)
    _trade(client, directa, etf, description="Vendita VWCE", trade_side="sell", units="4", unit_price="130",
           fee_amount="2,00")
    sale = Transaction.query.filter_by(description="Vendita VWCE").one()
    assert sale.units == -4 and sale.account_id is None and sale.counter_account_id == directa.id
    db.session.refresh(etf)
    assert etf.quantity == 6 and etf.avg_price == 100  # a sale leaves the average price alone
    with client.application.test_request_context():
        assert accounts.balance(directa) == 5000 + 520 - 2


def test_everything_stays_optional(client, db):
    directa, etf = _setup(db)
    _trade(client, directa, etf, record_fee=None, update_holding=None, fee_amount="")
    assert Transaction.query.count() == 1
    db.session.refresh(etf)
    assert etf.quantity == 10
    # a plain transaction linked to the holding, with no units: as before (a dividend, a manual purchase)
    client.post("/transactions/new", data={"date": "2026-09-20", "description": "Dividendo", "amount": "12",
                                           "currency": "EUR", "holding_id": str(etf.id)})
    dividend = Transaction.query.filter_by(description="Dividendo").one()
    assert dividend.type == "income" and dividend.units is None


def test_invalid_units_are_refused_and_editing_does_not_repeat_the_effects(client, db):
    directa, etf = _setup(db)
    html = _trade(client, directa, etf, units="0").get_data(as_text=True)
    assert "quote e prezzo" in html and Transaction.query.count() == 0
    _trade(client, directa, etf)
    trade = Transaction.query.filter_by(description="Acquisto VWCE").one()
    page = client.get(f"/transactions/{trade.id}/edit").get_data(as_text=True)
    assert 'value="10"' in page and "si aggiornano solo quando la registri" in page
    client.post(f"/transactions/{trade.id}/edit", data={"date": "2026-09-12", "description": "Acquisto VWCE (PAC)", "amount": "",
                                                        "currency": "EUR", "account_id": str(directa.id), "holding_id": str(etf.id),
                                                        "trade_side": "buy", "units": "10", "unit_price": "121"})
    db.session.refresh(etf)
    assert etf.quantity == 20 and Transaction.query.filter_by(type="expense").count() == 1  # no second commission
    assert db.session.get(Transaction, trade.id).amount == Decimal("1210.00")


def test_account_form_saves_the_rules(client, db):
    client.post("/accounts/new", data={"name": "Fineco Trading", "kind": "other", "currency": "EUR", "active": "on",
                                       "fee_fixed": "2,95", "fee_percent": "0,19", "fee_min": "2,95", "fee_max": "19"})
    account = Account.query.one()
    assert account.has_fee_rule and account.fee_percent == Decimal("0.1900")
    html = client.post(f"/accounts/{account.id}/edit", data={"name": "Fineco Trading", "kind": "other", "currency": "EUR",
                                                             "fee_min": "20", "fee_max": "19"}).get_data(as_text=True)
    assert "il minimo non può superare il massimo" in html
    assert "Commissioni del broker" in client.get("/accounts/new").get_data(as_text=True)
    form = client.get("/transactions/new").get_data(as_text=True)
    assert f'"{account.id}": {{"fixed": 2.95' in form or f'"{account.id}":{{"fixed":2.95' in form
