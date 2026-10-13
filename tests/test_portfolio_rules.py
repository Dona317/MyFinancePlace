"""
F19e: rules on the investments that turn into reminders (drift from the model, drawdown, price thresholds,
concentration) and the PAC — due on its day, split as the model says, confirmed into purchases.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.portfolio_model import InvestmentPlan, PortfolioRule
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import investment_plans, notifications, portfolio_models, portfolio_rules
from app.services.investment_plans import Order, PlanError
from app.services.portfolio_rules import RuleError

TODAY = date(2026, 10, 15)


@pytest.fixture()
def book(db):
    world = Holding(name="All-World", isin="IE00BK5BQT80", ticker="VWCE.MI", asset_class="ETF", quantity=70,
                    avg_price=100, current_price=100, price_date=date(2026, 10, 14))
    bonds = Holding(name="Global Agg", ticker="AGGH.MI", asset_class="ETF", quantity=400, avg_price=6, current_price=5,
                    price_date=date(2026, 10, 14))
    db.session.add_all([world, bonds])
    db.session.commit()
    return world, bonds  # 7.000 € + 2.000 € (bonds down 16,7 %)


def _rule(db, kind, threshold=None, holding=None):
    rule = PortfolioRule(kind=kind, threshold=threshold, holding_id=holding.id if holding else None)
    db.session.add(rule)
    db.session.commit()
    return rule


def test_rules_trip(app, db, book):
    world, bonds = book
    with app.test_request_context():
        portfolio_models.copy_ready("60-40")
        db.session.commit()
        drift = _rule(db, "drift")
        down = _rule(db, "drawdown", 15)
        above = _rule(db, "price_above", 99, world)
        below = _rule(db, "price_below", 4, bonds)
        heavy = _rule(db, "concentration", 70)
        alerts = portfolio_rules.evaluate(TODAY)
    keys = [a.key for a in alerts]
    assert keys == [f"rule-{drift.id}-0-2026-10", f"rule-{drift.id}-1-2026-10",  # 77,8 % vs 60, 22,2 % vs 40
                    f"rule-{down.id}-{bonds.id}-2026-10-14", f"rule-{above.id}-{world.id}-2026-10-14",
                    f"rule-{heavy.id}-{world.id}-2026-10-14"]
    assert "Global Agg ha perso il 16,7 % dal prezzo medio" in [a.title for a in alerts]
    assert below.id not in {int(k.split("-")[1]) for k in keys}  # 5 € is not under 4 €

    with app.test_request_context():
        texts = [n.title for n in notifications.collect(TODAY)]
    assert "All-World pesa il 77,8 % degli investimenti" in texts

    drift.threshold, down.active = Decimal(20), False
    db.session.commit()
    with app.test_request_context():
        keys = [a.key for a in portfolio_rules.evaluate(TODAY)]
    assert not any(k.startswith(f"rule-{drift.id}-") or k.startswith(f"rule-{down.id}-") for k in keys)


def test_no_rules_or_model(app, db, book):
    with app.test_request_context():
        assert portfolio_rules.evaluate(TODAY) == []
        _rule(db, "drift")
        assert portfolio_rules.evaluate(TODAY) == []  # no active model
        _rule(db, "concentration", 50)
        Holding.query.delete()
        db.session.commit()
        assert portfolio_rules.evaluate(TODAY) == []


@pytest.mark.parametrize("kind, holding, threshold, message", [
    ("nope", None, Decimal(1), "sconosciuto"),
    ("price_above", None, Decimal(1), "sceglilo"),
    ("drawdown", None, None, "maggiore di zero"),
    ("concentration", None, Decimal(120), "da 0 a 100"),
])
def test_rule_validation(app, kind, holding, threshold, message):
    with app.test_request_context(), pytest.raises(RuleError, match=message):
        portfolio_rules.validate(kind, holding, threshold)


def test_plan_due_dates(app, db):
    monthly = InvestmentPlan(name="Mensile", amount=300, frequency="monthly", day=31, start=date(2026, 1, 1))
    quarterly = InvestmentPlan(name="Trimestrale", amount=900, frequency="quarterly", day=5, start=date(2026, 1, 10))
    db.session.add_all([monthly, quarterly])
    db.session.commit()
    assert investment_plans.due_date(monthly, date(2026, 2, 3)) == date(2026, 2, 28)  # the month's last day
    assert not investment_plans.is_due(monthly, date(2026, 2, 27))
    assert investment_plans.is_due(monthly, date(2026, 2, 28))
    assert investment_plans.due_date(quarterly, date(2026, 2, 6)) is None
    assert not investment_plans.is_due(quarterly, date(2026, 1, 20))  # January's day 5 came before the start
    assert investment_plans.is_due(quarterly, date(2026, 4, 5))
    monthly.last_done = "2026-02"
    assert not investment_plans.is_due(monthly, date(2026, 2, 28))
    monthly.end = date(2026, 3, 1)
    assert not investment_plans.is_due(monthly, date(2026, 3, 31))
    assert not investment_plans.is_due(monthly, date(2025, 12, 31))
    assert [p.name for p in investment_plans.due(date(2026, 4, 5))] == ["Trimestrale"]


@pytest.mark.parametrize("args, message", [
    (("", 1, "monthly", 1, date(2026, 1, 1), None), "nome"),
    (("x", 0, "monthly", 1, date(2026, 1, 1), None), "importo"),
    (("x", 1, "weekly", 1, date(2026, 1, 1), None), "Frequenza"),
    (("x", 1, "monthly", 32, date(2026, 1, 1), None), "giorno"),
    (("x", 1, "monthly", 1, None, None), "inizio"),
    (("x", 1, "monthly", 1, date(2026, 1, 1), date(2025, 1, 1)), "fine"),
])
def test_plan_validation(app, args, message):
    with app.test_request_context(), pytest.raises(PlanError, match=message):
        investment_plans.validate(*[Decimal(a) if isinstance(a, int) and i == 1 else a for i, a in enumerate(args)])


def test_plan_proposal_and_confirm(app, db, book):
    world, bonds = book
    broker = Account(name="Directa", kind="other", fee_fixed=Decimal("1.5"))
    db.session.add(broker)
    with app.test_request_context():
        template = portfolio_models.copy_ready("permanent")  # 4 × 25 %: only the stocks are held
        plan = InvestmentPlan(name="PAC", amount=1000, frequency="monthly", day=1, start=date(2026, 1, 1),
                              account=broker, fractional=False, template=template)
        db.session.add(plan)
        db.session.commit()
        purchases = investment_plans.proposal(plan)
    assert [p.label for p in purchases] == ["Obbligazioni a lungo termine", "Oro", "Liquidità"]
    assert all(p.holding is None and p.units is None for p in purchases)  # nothing held there: price to enter
    assert sum(p.amount for p in purchases) == Decimal(1000)

    orders = [Order(None, "Oro", "IE00B579F325", "SGLD.MI", Decimal(2), Decimal("190.5")),
              Order(world.id, "x", None, None, Decimal(0), Decimal(1))]  # no units: skipped
    with app.test_request_context():
        assert investment_plans.confirm(plan, orders, date(2026, 10, 2)) == 1
        db.session.commit()
    gold = Holding.query.filter_by(isin="IE00B579F325").one()
    assert (gold.name, gold.quantity) == ("Oro (SGLD.MI)", Decimal(2))
    fee = Transaction.query.filter(Transaction.fee_for_id.isnot(None)).one()
    assert fee.amount == Decimal("1.50") and plan.last_done == "2026-10"
    with app.test_request_context(), pytest.raises(PlanError, match="Nessun acquisto"):
        investment_plans.confirm(plan, [], date(2026, 10, 2))


def test_plan_proposal_fractional_and_whole(app, db, book):
    world, bonds = book
    with app.test_request_context():
        portfolio_models.copy_ready("80-20")
        db.session.commit()
        plan = InvestmentPlan(name="PAC", amount=1000, frequency="monthly", day=1, start=date(2026, 1, 1))
        db.session.add(plan)
        # after 1.000 € the total is 10.000: stocks lack 1.000, bonds are at 2.000 = target
        (stocks,) = investment_plans.proposal(plan)
        assert (stocks.holding, stocks.units, stocks.price) == (world, Decimal(10), Decimal(100))
        plan.amount = Decimal(1050)
        plan.fractional = False
        purchases = investment_plans.proposal(plan)
    # total after 10.050: stocks lack 1.040 (→ 10 whole units at 100 €), bonds 10 € (→ 2 at 5 €)
    assert [(p.amount, p.units) for p in purchases] == [(Decimal(1040), Decimal(10)), (Decimal(10), Decimal(2))]


def test_plan_without_model(app, db):
    plan = InvestmentPlan(name="PAC", amount=100, frequency="monthly", day=1, start=date(2026, 1, 1))
    with app.test_request_context(), pytest.raises(PlanError, match="portafoglio modello"):
        investment_plans.proposal(plan)


def test_rule_pages(client, db, book):
    world, bonds = book
    page = client.post("/portfolio/rules/new", data={"kind": "drawdown", "threshold": "10"}, follow_redirects=True)
    assert "Regola aggiunta" in page.get_data(as_text=True)
    page = client.post("/portfolio/rules/new", data={"kind": "price_below", "threshold": "4"}, follow_redirects=True)
    assert "sceglilo" in page.get_data(as_text=True)
    page = client.get("/portfolio/rules").get_data(as_text=True)
    assert "Avvisi di oggi" in page and "Global Agg ha perso il 16,7 %" in page and "Nessun PAC." in page
    rule = PortfolioRule.query.one()
    client.post(f"/portfolio/rules/{rule.id}/toggle")
    db.session.refresh(rule)
    assert not rule.active and "Sospesa" in client.get("/portfolio/rules").get_data(as_text=True)
    client.post(f"/portfolio/rules/{rule.id}/delete")
    assert PortfolioRule.query.count() == 0


def test_plan_pages(client, db, book):
    world, bonds = book
    broker = Account(name="Directa", kind="other")
    db.session.add(broker)
    db.session.commit()
    assert "Nuovo piano d&#39;accumulo" in client.get("/portfolio/plans/new").get_data(as_text=True)
    form = {"name": "PAC", "amount": "1000", "frequency": "monthly", "day": "1", "start": "2026-01-01", "end": "",
            "account_id": str(broker.id), "template_id": "", "fractional": "1"}
    page = client.post("/portfolio/plans/new", data={**form, "amount": "0"}).get_data(as_text=True)
    assert "Indica un importo maggiore di zero." in page and 'value="PAC"' in page
    page = client.post("/portfolio/plans/new", data=form, follow_redirects=True).get_data(as_text=True)
    assert "Piano d&#39;accumulo salvato." in page and "Da confermare" in page
    plan = InvestmentPlan.query.one()
    assert (plan.account_id, plan.template_id, plan.fractional) == (broker.id, None, True)
    assert 'value="PAC"' in client.get(f"/portfolio/plans/{plan.id}").get_data(as_text=True)
    client.post(f"/portfolio/plans/{plan.id}", data={**form, "name": "PAC mensile", "template_id": "999"})
    db.session.refresh(plan)
    assert plan.name == "PAC mensile" and plan.template_id is None

    page = client.get(f"/portfolio/plans/{plan.id}/run", follow_redirects=True).get_data(as_text=True)
    assert "ha bisogno di un portafoglio modello" in page
    client.post("/portfolio/models/ready/80-20")
    page = client.get(f"/portfolio/plans/{plan.id}/run").get_data(as_text=True)
    assert "Conferma acquisti" in page and 'name="units-0" value="10"' in page

    run = {"rows": "1", "buy-0": "1", "holding-0": str(world.id), "label-0": "Azioni", "units-0": "10",
           "price-0": "101", "on": "2026-10-15"}
    page = client.post(f"/portfolio/plans/{plan.id}/run", data={**run, "units-0": "0"}, follow_redirects=True)
    assert "Nessun acquisto da confermare" in page.get_data(as_text=True)
    page = client.post(f"/portfolio/plans/{plan.id}/run", data=run, follow_redirects=True).get_data(as_text=True)
    assert "1 acquisti del PAC registrati." in page
    db.session.refresh(world)
    db.session.refresh(plan)
    assert world.quantity == Decimal(80) and plan.last_done == "2026-10"
    client.post(f"/portfolio/plans/{plan.id}/delete")
    assert InvestmentPlan.query.count() == 0


def test_plan_reminder(app, db, book):
    with app.test_request_context():
        portfolio_models.copy_ready("60-40")
        db.session.add(InvestmentPlan(name="PAC", amount=300, frequency="monthly", day=10, start=date(2026, 1, 1)))
        db.session.commit()
        items = [n for n in notifications.collect(TODAY) if n.key.startswith("plan-")]
    assert [(n.title, n.url.endswith("/run")) for n in items] == [("PAC «PAC»: € 300,00 da investire", True)]
