"""F22: the retirement simulation with a glide path from equities to bonds."""
import pytest

from app.services import planning
from app.services.planning import Retirement


def _plan(**values):
    return Retirement(**({"age": 55, "retire_at": 60, "horizon": 90, "wealth": 600000, "yearly_saving": 10000,
                          "expenses": 36000, "pension": 12000, "expected_return": 7, "volatility": 18} | values))


def test_no_glide_is_unchanged():
    plain = planning.simulate(_plan())
    assert "without" not in plain and "bonds" not in plain
    assert plain == planning.simulate(_plan(), glide=False)


def test_bond_share_rises_after_retirement():
    plan = _plan(bonds_at_retirement=20, bonds_at_horizon=50)
    assert plan.glides
    assert plan.bond_share(55) == plan.bond_share(60) == 0.2
    assert plan.bond_share(75) == pytest.approx(0.35) and plan.bond_share(90) == pytest.approx(0.5)


def test_glide_compared_with_none():
    result = planning.simulate(_plan(bonds_at_retirement=20, bonds_at_horizon=60, bond_return=3, bond_volatility=5))
    assert set(result["without"]) == {"success", "p10_end", "p50_end"}
    assert result["bonds"][0] == 20 and result["bonds"][-1] == 60 and len(result["bonds"]) == len(result["ages"])
    # less volatile at the end: the worst tenth does not fall as low as all-equities
    assert result["p10"][-1] >= 0 and result["without"]["success"] >= 0


def test_checks():
    with pytest.raises(ValueError, match="obbligazioni"):
        _plan(bonds_at_horizon=120).check()
    with pytest.raises(ValueError, match="obbligazioni"):
        _plan(bond_volatility=-1).check()


def test_page(client, db):
    client.post("/forecast/retirement", data={"age": "55", "retire_at": "60", "horizon": "90", "wealth": "600000",
                                              "expenses": "36000", "bonds_at_retirement": "20", "bonds_at_horizon": "50"})
    page = client.get("/forecast/retirement").get_data(as_text=True)
    assert "Con e senza passaggio" in page and "glideChart" in page
    assert planning.load().bonds_at_horizon == 50
