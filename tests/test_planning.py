"""F20i: goals projected with a monthly saving and a return; the retirement / FIRE Monte Carlo."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.wealth import Goal
from app.services import planning
from app.services.planning import Retirement
from tests.conftest import make_tx

TODAY = date(2026, 10, 13)


def test_money_maths():
    assert planning.future_value(1000, 100, 0, 12) == 2200
    assert round(planning.future_value(1000, 0, 12.6825, 12), 2) == 1126.83
    assert planning.months_to(1000, 1000, 0, 0) == 0
    assert planning.months_to(2200, 1000, 100, 0) == 12
    assert planning.months_to(10**9, 0, 0, 0) is None
    assert planning.required_monthly(2200, 1000, 0, 12) == 100
    assert planning.required_monthly(500, 1000, 3, 12) == 0.0
    assert planning.required_monthly(1500, 1000, 0, 0) == 500
    need = planning.required_monthly(10000, 0, 5, 60)
    assert round(planning.future_value(0, need, 5, 60), 2) == 10000


def test_goal_plan_and_sync(app, db):
    saving = Account(name="Deposito", kind="savings", opening_balance=Decimal("3000"))
    db.session.add(saving)
    db.session.flush()
    goal = Goal(name="Auto", target_amount=Decimal("6000"), saved_amount=0, target_date=date(2027, 10, 1),
                account_id=saving.id, monthly_contribution=Decimal("250"), expected_return=Decimal("0"))
    db.session.add_all([goal, make_tx(description="Prelievo", amount=Decimal("500"), account_id=saving.id)])
    db.session.commit()
    with app.test_request_context():
        planning.sync([goal])
        plan = planning.goal_plan(goal, TODAY)
    assert goal.saved_amount == Decimal("2500.00")
    assert plan.months_left == 12 and plan.needed == round(3500 / 12, 2)
    assert plan.reached_on == date(2027, 12, 13)  # 14 months of 250 €
    assert [r for r, _d in plan.scenarios] == [-2.0, 0.0, 2.0]
    assert plan.scenarios[2][1] <= plan.scenarios[1][1] <= plan.scenarios[0][1]
    open_ended = Goal(name="Casa", target_amount=Decimal("50000"), saved_amount=Decimal("1000"))
    assert planning.goal_plan(open_ended, TODAY).needed is None
    assert planning.goal_plan(open_ended, TODAY).reached_on is None  # nothing put aside: never


def test_retirement_simulation():
    plan = Retirement(age=40, retire_at=60, horizon=90, wealth=200000, yearly_saving=20000, expenses=30000,
                      pension=12000, expected_return=6, volatility=12, inflation=2, withdrawal_rate=4)
    result = planning.simulate(plan, runs=300)
    assert result["ages"][0] == 40 and result["ages"][-1] == 90 and len(result["p50"]) == 51
    assert 0 <= result["success"] <= 100 and result["p10"][20] <= result["p50"][20] <= result["p90"][20]
    assert result["gap"] == 18000 and result["needed"] == 450000
    assert result["sustainable"] == round(result["median_at_retirement"] * 0.04, 0)
    assert result["fire_age"] is not None and result["fire_age"] <= 60
    assert planning.simulate(plan, runs=300) == result  # same seed, same answer
    broke = Retirement(age=60, retire_at=61, horizon=95, wealth=50000, expenses=40000, volatility=0)
    poor = planning.simulate(broke, runs=50)
    assert poor["success"] == 0 and poor["first_broke"] is not None and poor["fire_age"] is None
    with pytest.raises(ValueError, match="in ordine"):
        planning.simulate(Retirement(age=70, retire_at=65))
    with pytest.raises(ValueError, match="negativi"):
        Retirement(wealth=-1).check()


def test_suggested_and_saved(app, db):
    db.session.add_all([Account(name="Corrente", kind="current", opening_balance=Decimal("20000")),
                        make_tx(description="Stipendio", type="income", category="Stipendio", amount=Decimal("30000"),
                                date=date(2026, 6, 1)),
                        make_tx(description="Spese", amount=Decimal("18000"), category="Altro", date=date(2026, 6, 2))])
    db.session.commit()
    with app.test_request_context():
        suggested = planning.suggested(TODAY)
        assert (suggested.wealth, suggested.expenses, suggested.yearly_saving) == (32000, 18000, 12000)
        assert planning.load() == suggested_without_today(app)
        planning.save(Retirement(age=45, wealth=1))
        db.session.commit()
        assert planning.load().age == 45


def suggested_without_today(app):
    return planning.suggested()


def test_pages(client, db):
    page = client.get("/forecast/retirement").get_data(as_text=True)
    assert "Probabilità di successo" in page and "retirementChart" in page
    page = client.post("/forecast/retirement", data={"age": "50", "retire_at": "67", "horizon": "95", "wealth": "300000",
                                                    "expenses": "25000", "pension": "15000"}, follow_redirects=True)
    assert "Simulazione aggiornata." in page.get_data(as_text=True)
    assert planning.load().age == 50
    page = client.post("/forecast/retirement", data={"age": "80"}, follow_redirects=True).get_data(as_text=True)
    assert "in ordine" in page and planning.load().age == 50
    client.post("/forecast/retirement", data={"reset": "1"})
    assert planning.load().age == 40
    assert "Pensione e FIRE" in client.get("/forecast/").get_data(as_text=True)


def test_goal_pages(client, db):
    saving = Account(name="Deposito", kind="savings", opening_balance=Decimal("1200"))
    db.session.add(saving)
    db.session.commit()
    form = {"name": "Viaggio", "target_amount": "3000", "saved_amount": "0", "target_date": "2027-06-01",
            "account_id": str(saving.id), "monthly_contribution": "150", "expected_return": "2"}
    client.post("/lifestyle/goals/new", data=form)
    goal = Goal.query.one()
    assert (goal.account_id, goal.monthly_contribution, goal.expected_return) == (saving.id, Decimal(150), Decimal(2))
    page = client.get("/lifestyle/goals").get_data(as_text=True)
    assert "Segue il saldo del conto" in page and "Con € 150,00 al mese lo raggiungi" in page
    db.session.refresh(goal)
    assert goal.saved_amount == Decimal("1200.00")
    page = client.post("/lifestyle/goals/new", data={**form, "expected_return": "50"}).get_data(as_text=True)
    assert "Rendimento atteso" in page
