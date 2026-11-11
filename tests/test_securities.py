"""
F42: securities accounts and portfolios. Every operation of a holding sits in a securities account and belongs to a
portfolio; positions (holding × securities account × portfolio) come from the opening position and the trades, with
the average cost of each position (D9); the holding's own quantity and average price, the «Tutti» view, do not change.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.securities import Portfolio, SecuritiesAccount
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import portfolio_ops, securities
from app.services.portfolio_ops import Operation


@pytest.fixture()
def setup(db):
    directa = Account(name="Directa", kind="other", bank="Directa SIM", fee_fixed=Decimal("1.5"),
                      tax_regime="amministrato")
    degiro = Account(name="Degiro", kind="other", tax_regime="dichiarativo", abroad=True)
    etf = Holding(name="All-World", ticker="VWCE.DE", asset_class="ETF", quantity=10, avg_price=100,
                  opening_quantity=10, opening_price=100, opening_date=date(2025, 1, 2))
    db.session.add_all([directa, degiro, etf])
    db.session.commit()
    return directa, degiro, etf


def test_a_trade_gets_the_settlement_accounts_dossier_and_the_default_portfolio(app, db, setup):
    directa, _degiro, etf = setup
    with app.test_request_context():
        created = portfolio_ops.record(etf, Operation("buy", date(2025, 6, 2), directa, units=Decimal(5),
                                                      price=Decimal(120), fee=Decimal(2)))
        db.session.commit()
    dossier = SecuritiesAccount.query.one()
    assert (dossier.name, dossier.broker, dossier.settlement_account_id) == ("Titoli Directa", "Directa SIM", directa.id)
    assert (dossier.tax_regime, dossier.fee_fixed, dossier.cost_method) == ("amministrato", Decimal("1.50"), "average")
    default = Portfolio.query.one()
    assert (default.name, default.is_default) == ("Portafoglio principale", True)
    assert {(t.securities_account_id, t.portfolio_id) for t in created} == {(dossier.id, default.id)}  # fee too
    # the next trade on the same account reuses the dossier
    with app.test_request_context():
        portfolio_ops.record(etf, Operation("sell", date(2025, 7, 1), directa, units=Decimal(1), price=Decimal(130)))
    assert SecuritiesAccount.query.count() == 1


def test_one_portfolio_over_two_dossiers_and_one_dossier_with_two_portfolios(app, db, setup):
    directa, degiro, etf = setup
    pension, house = Portfolio(name="Pensione"), Portfolio(name="Casa")
    db.session.add_all([pension, house])
    db.session.commit()
    with app.test_request_context():
        on_directa = securities.for_settlement(directa)
        on_degiro = securities.for_settlement(degiro)
        for account, folio, units, price in ((on_directa, pension, 10, 100), (on_directa, house, 4, 110),
                                             (on_degiro, pension, 6, 105)):
            portfolio_ops.record(etf, Operation("buy", date(2025, 3, 1), account.settlement_account,
                                                units=Decimal(units), price=Decimal(price),
                                                securities_account=account, portfolio=folio))
        portfolio_ops.record(etf, Operation("sell", date(2025, 9, 1), directa, units=Decimal(5), price=Decimal(130),
                                            securities_account=on_directa, portfolio=pension))
        db.session.commit()
        found = {(p.securities_account_id, p.portfolio_id): p for p in securities.positions([etf])}
        default = securities.default_portfolio()
    # the opening position (no trades on its own before F42) sits in no dossier, in the default portfolio
    assert set(found) == {(None, default.id), (on_directa.id, pension.id), (on_directa.id, house.id),
                          (on_degiro.id, pension.id)}
    assert found[(on_directa.id, pension.id)].quantity == Decimal(5)          # 10 bought, 5 sold
    assert found[(on_directa.id, pension.id)].avg_price == Decimal("100.000000")  # a sale keeps the average (D9)
    assert found[(on_directa.id, house.id)].avg_price == Decimal("110.000000")
    # the positions always add up to the holding (the «Tutti» view is unchanged)
    assert sum(p.quantity for p in found.values()) == Decimal(etf.quantity) == Decimal(25)
    with app.test_request_context():
        in_pension = securities.positions([etf], portfolio_id=pension.id)
        on_directa_only = securities.positions(securities_account_id=on_directa.id)
        assert [h.name for h in securities.holdings_in(portfolio_id=house.id)] == ["All-World"]
    assert sum(p.quantity for p in in_pension) == Decimal(11)
    assert sum(p.quantity for p in on_directa_only) == Decimal(9)


def test_operations_from_before_f42_are_assigned_once(app, db, setup):
    directa, degiro, etf = setup
    buy = Transaction(date=date(2025, 2, 1), description="Acquisto", amount=1000, currency="EUR", type="transfer",
                      category="Investimenti", holding_id=etf.id, units=10, unit_price=100, account_id=directa.id,
                      tags=[])
    sell = Transaction(date=date(2025, 3, 1), description="Vendita", amount=550, currency="EUR", type="transfer",
                       category="Investimenti", holding_id=etf.id, units=-5, unit_price=110,
                       counter_account_id=degiro.id, tags=[])
    db.session.add_all([buy, sell])
    db.session.flush()
    fee = Transaction(date=buy.date, description="Commissione", amount=2, currency="EUR", type="expense",
                      category="Commissioni", account_id=directa.id, fee_for_id=buy.id, tags=[])
    other = Transaction(date=date(2025, 3, 2), description="Spesa", amount=30, currency="EUR", type="expense",
                        category="Alimentari", account_id=directa.id, tags=[])
    db.session.add_all([fee, other])
    db.session.commit()
    with app.test_request_context():
        assert securities.ensure_assigned() > 0
        db.session.commit()
        assert securities.ensure_assigned() == 0  # nothing left to do: it never changes what is set
    names = {s.settlement_account_id: s.id for s in SecuritiesAccount.query}
    default = Portfolio.query.filter_by(is_default=True).one()
    assert (buy.securities_account_id, sell.securities_account_id) == (names[directa.id], names[degiro.id])
    assert (fee.securities_account_id, fee.portfolio_id) == (names[directa.id], default.id)
    assert (other.securities_account_id, other.portfolio_id) == (None, None)  # not an investment: untouched
    assert (etf.opening_account_id, etf.opening_portfolio_id) == (names[directa.id], default.id)


def test_a_restored_backup_from_before_f42_gets_its_dossiers(app, db, setup):
    from app.services import backup

    directa, _degiro, etf = setup
    db.session.add(Transaction(date=date(2025, 2, 1), description="Acquisto", amount=1000, currency="EUR",
                               type="transfer", category="Investimenti", holding_id=etf.id, units=10,
                               unit_price=100, account_id=directa.id, tags=[]))
    db.session.commit()
    with app.test_request_context():
        data = backup.export_data()
        for name in ("securities_accounts", "portfolios"):
            data["tables"].pop(name, None)
        for row in data["tables"]["transactions"]:
            row.pop("securities_account_id", None)
            row.pop("portfolio_id", None)
        backup.restore(data, {})
    trade = Transaction.query.one()
    assert trade.securities_account_id == SecuritiesAccount.query.one().id
    assert trade.portfolio_id == Portfolio.query.filter_by(is_default=True).one().id


def test_lists_and_position_values(app, db, setup):
    directa, _degiro, etf = setup
    etf.current_price, etf.multiplier = Decimal(120), Decimal(1)
    closed = Portfolio(name="Vecchio", active=False, position=9)
    db.session.add(closed)
    db.session.commit()
    with app.test_request_context():
        dossier = securities.for_settlement(directa)
        securities.default_portfolio()
        db.session.commit()
        assert [p.name for p in securities.portfolios()] == ["Portafoglio principale"]
        assert [p.name for p in securities.portfolios(active_only=False)] == ["Portafoglio principale", "Vecchio"]
        dossier.active = False
        assert securities.accounts() == [] and securities.accounts(active_only=False) == [dossier]
        (position,) = securities.positions([etf])
    assert dossier.has_fee_rule and not SecuritiesAccount(name="Nuovo").has_fee_rule
    assert (position.units, position.value, position.gain) == (10.0, 1200.0, 200.0)


def test_an_order_sells_where_the_units_are_and_buys_where_the_holding_sits(app, db, setup):
    directa, degiro, etf = setup
    pension = Portfolio(name="Pensione")
    db.session.add(pension)
    db.session.commit()
    with app.test_request_context():
        on_degiro = securities.for_settlement(degiro)
        portfolio_ops.record(etf, Operation("buy", date(2025, 3, 1), degiro, units=Decimal(30), price=Decimal(100),
                                            portfolio=pension))
        etf.opening_account_id = securities.for_settlement(directa).id
        db.session.commit()
        # 10 in Directa (default portfolio), 30 in Degiro (pension): selling 35 takes 30 + 5, fee on the first part
        assert portfolio_ops.record_order(etf, "sell", date(2025, 6, 1), Decimal(35), Decimal(110), Decimal(3)) == 2
        db.session.commit()
        sales = Transaction.query.filter(Transaction.units < 0).order_by(Transaction.id).all()
        assert [(s.units, s.securities_account_id, s.portfolio_id, s.counter_account_id) for s in sales] == [
            (Decimal(-30), on_degiro.id, pension.id, degiro.id),
            (Decimal(-5), etf.opening_account_id, securities.default_portfolio().id, directa.id)]
        assert Transaction.query.filter(Transaction.fee_for_id.isnot(None)).one().fee_for_id == sales[0].id
        with pytest.raises(ValueError, match="più quote"):
            portfolio_ops.record_order(etf, "sell", date(2025, 6, 2), Decimal(6), Decimal(110))
        # a purchase with nothing chosen goes where most of it sits (Directa now), paid from its settlement account
        portfolio_ops.record_order(etf, "buy", date(2025, 6, 3), Decimal(2), Decimal(111))
        buy = Transaction.query.filter(Transaction.units == 2).one()
        assert (buy.securities_account_id, buy.account_id) == (etf.opening_account_id, directa.id)
        assert securities.main_place(Holding(name="Nuovo", asset_class="ETF", quantity=0, avg_price=0)) is None


def test_capital_gains_use_the_average_cost_of_each_securities_account(app, db, setup):
    from app.services import capital_gains

    directa, degiro, etf = setup  # 10 units at 100 opening
    with app.test_request_context():
        portfolio_ops.record(etf, Operation("buy", date(2025, 2, 1), directa, units=Decimal(10), price=Decimal(120)))
        portfolio_ops.record(etf, Operation("buy", date(2025, 2, 2), degiro, units=Decimal(10), price=Decimal(200)))
        # sold on Directa: its dossier holds the opening 10 at 100 and 10 at 120 → average 110 (not 140 over all)
        portfolio_ops.record(etf, Operation("sell", date(2025, 6, 2), directa, units=Decimal(5), price=Decimal(150)))
        db.session.commit()
        (sale,) = capital_gains.realized()[0]
    assert (sale.cost, sale.proceeds) == (Decimal("550.00"), Decimal(750)) and sale.result == Decimal(200)


def test_starring_the_portfolio_that_already_has_the_star_keeps_it(app, db):
    """The first portfolio saved gets the star; starring it again (or once more after another one is created) must
    leave exactly that one starred, not none — or the next operation would go to a new «Portafoglio principale»."""
    with app.test_request_context():
        growth = securities.save_portfolio(None, "Crescita")
        securities.save_portfolio(None, "Reddito")
        securities.set_default(growth)
        db.session.commit()
        db.session.expire_all()
        assert [p.name for p in Portfolio.query.filter_by(is_default=True)] == ["Crescita"]
        assert securities.default_portfolio().name == "Crescita"
        income = Portfolio.query.filter_by(name="Reddito").one()
        securities.set_default(income)
        db.session.commit()
        db.session.expire_all()
        assert [p.name for p in Portfolio.query.filter_by(is_default=True)] == ["Reddito"]
    assert Portfolio.query.count() == 2
