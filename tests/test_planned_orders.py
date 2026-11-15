"""
Theoretical orders: a rebalancing (or a PAC instalment) saved before going to the broker moves nothing; the units,
average price and liquidity it would give are estimates, the liquidity gross of commissions; at the confirmation the
commissions are given order by order, as a total, or found from the liquidity actually left.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.planned_order import PlannedOrder
from app.models.portfolio_model import InvestmentPlan
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import planned_orders, securities
from app.services.planned_orders import Draft, Execution, PlannedError

ON = date(2026, 11, 2)


@pytest.fixture()
def book(db):
    """20.000 € on the broker's liquidity, three ETFs: the user's example — buy them as the model says."""
    cash = Account(name="Liquidità Fineco", kind="other", opening_balance=Decimal(20000))
    world = Holding(name="All-World", isin="IE00BK5BQT80", asset_class="ETF", quantity=10, avg_price=100,
                    current_price=110, opening_quantity=10, opening_price=100)
    bonds = Holding(name="Agg Bond", asset_class="ETF", quantity=0, avg_price=0, current_price=5,
                    opening_quantity=0, opening_price=0)
    gold = Holding(name="Gold", asset_class="ETF", quantity=0, avg_price=0, current_price=200,
                   opening_quantity=0, opening_price=0)
    db.session.add_all([cash, world, bonds, gold])
    db.session.commit()
    return cash, world, bonds, gold


def _save(app, db, book):
    cash, world, bonds, gold = book
    with app.test_request_context():
        dossier = securities.save_account(None, {"name": "Dossier Fineco", "settlement_account_id": cash.id})
        batch = planned_orders.save([Draft(world, "buy", Decimal(100), Decimal(110), "Azioni"),
                                     Draft(bonds, "buy", Decimal(1000), Decimal(5), "Obbligazioni"),
                                     Draft(gold, "buy", Decimal(5), Decimal(200), "Oro")],
                                    dossier=dossier, notes="Ribilanciamento")
        db.session.commit()
    return batch, dossier


def test_saved_orders_move_nothing_and_show_a_theoretical_position(app, db, book):
    cash, world, _bonds, _gold = book
    batch, dossier = _save(app, db, book)
    assert Transaction.query.count() == 0 and world.quantity == 10  # nothing recorded
    orders = PlannedOrder.query.filter_by(batch=batch).all()
    assert {(o.account_id, o.securities_account_id) for o in orders} == {(cash.id, dossier.id)}
    with app.test_request_context():
        rows = {p.holding.name: p for p in planned_orders.positions(orders)}
        flows = planned_orders.cash(orders)
    assert rows["All-World"].units == 110 and rows["All-World"].abp == Decimal("109.090909")  # (10×100+100×110)/110
    assert rows["Gold"].units == 5 and rows["Gold"].abp == 200
    assert len(flows) == 1 and flows[0].now == Decimal(20000)
    assert flows[0].bought == Decimal(17000) and flows[0].expected == Decimal(3000)  # gross of commissions
    assert [b.batch for b in planned_orders.batches()] == [batch] and planned_orders.count() == 3


def test_commissions_from_the_liquidity_left(app, db, book):
    """319 € expected, 300 € on the account: 19 € of commissions, split over the orders by their amount."""
    cash, world, bonds, gold = book
    batch, dossier = _save(app, db, book)
    orders = {o.holding.name: o for o in PlannedOrder.query.filter_by(batch=batch)}
    executed = [Execution(orders["All-World"], Decimal(100), Decimal("110.50")),   # 11.050
                Execution(orders["Agg Bond"], Decimal(1000), Decimal("5.20")),     #  5.200
                Execution(orders["Gold"], Decimal(17), Decimal("202.10"))]         #  3.435,70 → 19.685,70
    with app.test_request_context():
        flows = planned_orders.cash(list(orders.values()), executed={e.order.id: (e.units, e.price) for e in executed})
        assert flows[0].expected == Decimal("314.30")
        result = planned_orders.confirm(batch, executed, ON, "cash", actual={cash.id: Decimal("295.30")})
        db.session.commit()
    assert result.recorded == 3 and result.fees == Decimal("19.00") and result.by_account == {"Liquidità Fineco": Decimal("19.00")}
    fees = Transaction.query.filter(Transaction.fee_for_id.isnot(None)).all()
    assert sum(f.amount for f in fees) == Decimal("19.00") and len(fees) == 3
    biggest = next(f for f in fees if f.fee_for.holding_id == world.id)
    assert biggest.amount == Decimal("10.68")  # 19 × 11.050 / 19.685,70, plus the cents left over
    with app.test_request_context():
        from app.services import accounts
        assert Decimal(str(accounts.balance(cash))) == Decimal("295.30")  # the account now matches the broker
    db.session.refresh(world)
    assert world.quantity == 110 and PlannedOrder.query.count() == 0
    assert all(t.securities_account_id == dossier.id for t in Transaction.query)


def test_commissions_as_a_total_or_per_order_and_orders_left_theoretical(app, db, book):
    cash, world, bonds, gold = book
    batch, _dossier = _save(app, db, book)
    orders = {o.holding.name: o for o in PlannedOrder.query.filter_by(batch=batch)}
    with app.test_request_context():
        result = planned_orders.confirm(batch, [Execution(orders["All-World"], Decimal(100), Decimal(110)),
                                                Execution(orders["Agg Bond"], Decimal(1000), Decimal(5))],
                                        ON, "total", total=Decimal("7.95"))
        db.session.commit()
    assert result.fees == Decimal("7.95")
    assert sorted(f.amount for f in Transaction.query.filter(Transaction.fee_for_id.isnot(None))) == [
        Decimal("2.48"), Decimal("5.47")]  # 7,95 in proportion to 11.000 and 5.000, the cent left to the biggest
    assert [o.holding.name for o in PlannedOrder.query] == ["Gold"]  # not executed: still theoretical
    with app.test_request_context():
        planned_orders.confirm(batch, [Execution(PlannedOrder.query.one(), Decimal(5), Decimal(201), Decimal("2.95"))],
                               ON, "each")
        db.session.commit()
    gold_fee = Transaction.query.filter(Transaction.fee_for_id.isnot(None)).order_by(Transaction.id.desc()).first()
    assert gold_fee.amount == Decimal("2.95") and PlannedOrder.query.count() == 0


def test_wrong_confirmations_are_refused(app, db, book):
    cash, world, *_ = book
    batch, _dossier = _save(app, db, book)
    order = PlannedOrder.query.filter_by(holding_id=world.id).one()
    with app.test_request_context():
        with pytest.raises(PlannedError, match="in più di quanto atteso"):
            planned_orders.confirm(batch, [Execution(order, Decimal(100), Decimal(110))], ON, "cash",
                                   actual={cash.id: Decimal(9500)})  # 9.000 expected: more money than possible
        with pytest.raises(PlannedError, match="liquidità che hai ora"):
            planned_orders.confirm(batch, [Execution(order, Decimal(100), Decimal(110))], ON, "cash", actual={})
        with pytest.raises(PlannedError, match="totali"):
            planned_orders.confirm(batch, [Execution(order, Decimal(100), Decimal(110))], ON, "total")
        with pytest.raises(PlannedError, match="negativa"):
            planned_orders.confirm(batch, [Execution(order, Decimal(100), Decimal(110), Decimal(-1))], ON, "each")
        with pytest.raises(PlannedError, match="come indicare"):
            planned_orders.confirm(batch, [Execution(order, Decimal(100), Decimal(110))], ON, "nonsense")
        with pytest.raises(PlannedError, match="Nessun ordine"):
            planned_orders.confirm(batch, [Execution(order, Decimal(0), Decimal(110))], ON)
        with pytest.raises(PlannedError, match="futuro"):
            planned_orders.confirm(batch, [Execution(order, Decimal(1), Decimal(110))], date(2999, 1, 1))
        with pytest.raises(PlannedError, match="Nessun ordine da salvare"):
            planned_orders.save([Draft(world, "buy", Decimal(0), Decimal(1))])
    assert planned_orders.split(Decimal(10), []) == [] and planned_orders.split(Decimal(3), [Decimal(0), Decimal(0)]) == [
        Decimal(3), Decimal(0)]


def test_a_sale_is_placed_where_the_units_are(app, db, book):
    cash, _world, _bonds, world = book  # the gold: all its units in the dossier
    with app.test_request_context():
        dossier = securities.save_account(None, {"name": "Dossier Fineco", "settlement_account_id": cash.id})
        from app.services import portfolio_ops
        portfolio_ops.record(world, portfolio_ops.Operation("buy", date(2026, 1, 5), cash, units=Decimal(5),
                                                            price=Decimal(100), securities_account=dossier))
        batch = planned_orders.save([Draft(world, "sell", Decimal(3), Decimal(120))])
        order = PlannedOrder.query.filter_by(batch=batch).one()
        assert (order.securities_account_id, order.account_id) == (dossier.id, cash.id)
        assert order.portfolio_id == securities.default_portfolio().id
        rows = planned_orders.positions([order])
        assert rows[0].units == world.quantity - 3 and rows[0].abp == world.avg_price  # a sale keeps the average
        assert planned_orders.cash([order])[0].sold == Decimal(360)
        assert planned_orders.discard(batch) == 1


def test_pages(client, db, book):
    cash, world, bonds, gold = book
    assert "Nessun ordine teorico" in client.get("/portfolio/planned").get_data(as_text=True)
    client.post("/portfolio/models/ready/all-equity")
    db.session.add(Account(name="Altro conto", kind="current"))
    db.session.commit()
    page = client.get("/portfolio/rebalance/orders?mode=new&amount=5000").get_data(as_text=True)
    assert "Salva come ordini teorici" in page
    form = {"rows": "1", "do-0": "1", "holding-0": str(world.id), "side-0": "buy", "label-0": "Azioni",
            "units-0": "40", "price-0": "110", "on": "2026-11-02", "mode": "new", "amount": "5000",
            "account_id": str(cash.id), "action": "plan"}
    page = client.post("/portfolio/rebalance/orders", data=form, follow_redirects=True).get_data(as_text=True)
    assert "Ordini salvati come teorici" in page and "lorda di commissioni" in page and "Prezzo medio teorico" in page
    assert Transaction.query.count() == 0
    assert "ordini teorici non ancora confermati" in client.get("/portfolio/").get_data(as_text=True)
    order = PlannedOrder.query.one()
    page = client.post("/portfolio/rebalance/orders", data={**form, "units-0": "0"}, follow_redirects=True)
    assert "Nessun ordine da salvare" in page.get_data(as_text=True)
    # confirmed from the liquidity: 20.000 − 4.400 = 15.600 expected, 15.595 left → 5 € of commissions
    confirm = {"on": "2026-11-02", "fee_mode": "cash", f"do-{order.id}": "1", f"units-{order.id}": "40",
               f"price-{order.id}": "110", f"cash-{cash.id}": "15595"}
    page = client.post(f"/portfolio/planned/{order.batch}/confirm", data={**confirm, f"cash-{cash.id}": "16000"},
                       follow_redirects=True).get_data(as_text=True)
    assert "in più di quanto atteso" in page and PlannedOrder.query.count() == 1
    page = client.post(f"/portfolio/planned/{order.batch}/confirm", data=confirm, follow_redirects=True).get_data(as_text=True)
    assert "1 ordini eseguiti registrati, commissioni 5,00 €." in page and "5,00 € ricavati dalla liquidità" in page
    assert Transaction.query.filter(Transaction.fee_for_id.isnot(None)).one().amount == Decimal(5)
    # a second batch, partly confirmed, then the rest thrown away
    client.post("/portfolio/rebalance/orders", data={**form, "rows": "2", "do-1": "1", "holding-1": str(gold.id),
                                                     "side-1": "buy", "units-1": "2", "price-1": "200"})
    batch = PlannedOrder.query.first().batch
    first = PlannedOrder.query.filter_by(batch=batch, holding_id=world.id).one()
    page = client.post(f"/portfolio/planned/{batch}/confirm", data={
        "on": "2026-11-02", "fee_mode": "total", "fee_total": "3", f"do-{first.id}": "1", f"units-{first.id}": "40",
        f"price-{first.id}": "110"}, follow_redirects=True).get_data(as_text=True)
    assert "1 ordini non spuntati restano teorici." in page
    page = client.post(f"/portfolio/planned/{batch}/discard", follow_redirects=True).get_data(as_text=True)
    assert "1 ordini teorici eliminati." in page


def test_a_pac_instalment_saved_as_theoretical_orders(client, db, book):
    cash, world, *_ = book
    plan = InvestmentPlan(name="PAC mensile", amount=Decimal(1000), frequency="monthly", day=1,
                          start=date(2026, 1, 1), account_id=cash.id)
    db.session.add(plan)
    db.session.commit()
    client.post("/portfolio/models/ready/all-equity")
    run = {"rows": "2", "buy-0": "1", "holding-0": str(world.id), "label-0": "Azioni", "units-0": "9",
           "price-0": "110", "buy-1": "1", "label-1": "Nuovo", "units-1": "0", "price-1": "1", "on": "2026-11-02",
           "action": "plan"}
    page = client.post(f"/portfolio/plans/{plan.id}/run", data=run, follow_redirects=True).get_data(as_text=True)
    assert "Rata salvata come ordini teorici" in page and "Rata del PAC" in page
    assert Holding.query.count() == 3  # the empty row created nothing
    order = PlannedOrder.query.one()
    assert (order.plan_id, order.source, order.account_id) == (plan.id, "pac", cash.id)
    page = client.post(f"/portfolio/plans/{plan.id}/run", data={**run, "units-0": "0"}, follow_redirects=True)
    assert "Nessun ordine da salvare" in page.get_data(as_text=True)
    client.post(f"/portfolio/planned/{order.batch}/confirm", data={
        "on": "2026-11-02", "fee_mode": "each", f"do-{order.id}": "1", f"units-{order.id}": "9",
        f"price-{order.id}": "110", f"fee-{order.id}": "1,50"})
    db.session.refresh(plan)
    assert plan.last_done == "2026-11" and "PAC «PAC mensile»" in Transaction.query.filter(
        Transaction.units.isnot(None)).one().notes
