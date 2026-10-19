"""F22: contribution limits — pension fund, PIR, the user's own."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.limit import ContributionLimit
from app.models.wealth import Holding
from app.services import contribution_limits as limits
from app.services import notifications
from tests.conftest import make_tx


@pytest.fixture()
def money(db):
    bank, pir = Account(name="Banca"), Account(name="Conto PIR")
    fund = Holding(name="Fondo Cometa", asset_class="Fondo Pensione", quantity=1, avg_price=1000)
    etf = Holding(name="PIR Equity", asset_class="Fondo", quantity=10, avg_price=100)
    db.session.add_all([bank, pir, fund, etf])
    db.session.flush()
    db.session.add_all([
        make_tx(date=date(2026, 1, 16), description="Contributo Cometa", amount=2000, type="transfer", holding_id=fund.id,
                account_id=bank.id),
        make_tx(date=date(2026, 6, 16), description="Contributo Cometa", amount=2500, type="transfer", holding_id=fund.id,
                account_id=bank.id),
        make_tx(date=date(2025, 6, 16), description="Contributo 2025", amount=5000, type="transfer", holding_id=fund.id),
        make_tx(date=date(2026, 3, 1), description="Giroconto al PIR", amount=30000, type="transfer", account_id=bank.id,
                counter_account_id=pir.id),
        make_tx(date=date(2025, 3, 1), description="Giroconto al PIR", amount=40000, type="transfer", counter_account_id=pir.id),
        make_tx(date=date(2026, 4, 1), description="Acquisto PIR", amount=1000, type="transfer", holding_id=etf.id,
                units=10, unit_price=100),
        make_tx(date=date(2026, 5, 1), description="Vendita PIR", amount=500, type="transfer", holding_id=etf.id,
                units=-5, unit_price=100),
        make_tx(date=date(2026, 7, 1), description="Versamento extra", amount=900, category="Previdenza"),
    ])
    db.session.commit()
    return {"bank": bank.id, "pir": pir.id, "fund": fund.id, "etf": etf.id}


def _save(db, **values):
    base = dict(name="X", kind="custom", yearly=Decimal(100), total=None, since_year=None, account_ids=[],
                holding_ids=[], category=None, notes=None)
    limit = limits.save(None, **(base | values))
    db.session.commit()
    return limit


def test_pension_fund_counts_contributions_and_category(db, money):
    limit = _save(db, name="Cometa", kind="pension", yearly=Decimal("5164.57"), holding_ids=[money["fund"], 999],
                  category="Previdenza")
    assert limit.holding_ids == [money["fund"]]  # an unknown holding is dropped
    s = limits.standing(limit, 2026)
    assert s.paid == Decimal(5400) and s.left == 0 and s.over == Decimal("235.43") and s.pct == 100.0
    assert s.deductible and [tx.description for tx in s.movements][-1] == "Versamento extra"
    s25 = limits.standing(limit, 2025)
    assert s25.paid == 5000 and s25.left == Decimal("164.57") and s25.total_pct is None and s25.over == 0


def test_pir_yearly_and_lifetime(db, money):
    limit = _save(db, name="PIR", kind="pir", yearly=Decimal(40000), total=Decimal(200000), since_year=2025,
                  account_ids=[money["pir"]], holding_ids=[money["etf"]])
    s = limits.standing(limit, 2026)
    assert s.paid == 31000 and s.paid_total == 71000  # the sale frees no room
    assert s.left == 9000 and s.total_pct == 35.5 and not s.deductible
    tight = _save(db, name="Quasi pieno", yearly=Decimal(40000), total=Decimal(75000), account_ids=[money["pir"]])
    assert limits.standing(tight, 2026).left == 5000  # the lifetime room is smaller than the year's
    assert limits.standing(_save(db, name="Zero", yearly=Decimal(1), category="Nessuna"), 2026).pct == 0.0


def test_validation(db, money):
    with pytest.raises(ValueError, match="nome"):
        _save(db, name="  ", category="Previdenza")
    with pytest.raises(ValueError, match="positivo"):
        _save(db, yearly=None, category="Previdenza")
    with pytest.raises(ValueError, match="più basso"):
        _save(db, yearly=Decimal(100), total=Decimal(50), category="Previdenza")
    with pytest.raises(ValueError, match="almeno un conto"):
        _save(db, account_ids=["x", 999])
    assert _save(db, kind="strano", category="Previdenza").kind == "custom"


def test_reminder_late_in_the_year(app, db, money):
    limit = _save(db, name="Cometa", kind="pension", yearly=Decimal(6000), holding_ids=[money["fund"]])
    assert limits.reminders(date(2026, 9, 30)) == []
    [s] = limits.reminders(date(2026, 10, 1))
    assert s.left == 1500
    _save(db, name="PIR", kind="pir", yearly=Decimal(40000), account_ids=[money["pir"]])  # not deductible: no reminder
    assert len(limits.reminders(date(2026, 12, 1))) == 1
    with app.test_request_context():
        keys = [n.key for n in notifications.collect(date(2026, 11, 2))]
    assert f"limit-{limit.id}-2026" in keys


def test_pages(client, db, money):
    page = client.get("/tax/limits?year=2026").get_data(as_text=True)
    assert "Nessun tetto" in page and "Tetti di versamento" in page
    # a ready-made limit: its amounts and name when left empty
    client.post("/tax/limits/new", data={"kind": "pir", "account_ids": [money["pir"]]})
    pir = ContributionLimit.query.one()
    assert pir.name == "PIR ordinario" and pir.yearly == 40000 and pir.total == 200000
    page = client.get("/tax/limits?year=2026").get_data(as_text=True)
    assert "PIR ordinario" in page and "Giroconto al PIR" in page and "Totale versato" in page
    assert "almeno un conto" in client.post("/tax/limits/new", data={"kind": "custom", "name": "Mio", "yearly": "100"},
                                            follow_redirects=True).get_data(as_text=True)
    client.post(f"/tax/limits/{pir.id}/edit", data={"name": "Il mio PIR", "kind": "pir", "yearly": "30000",
                                                    "total": "150000", "since_year": "2025", "holding_ids": [money["etf"]]})
    db.session.refresh(pir)
    assert pir.name == "Il mio PIR" and pir.yearly == 30000 and pir.since_year == 2025 and pir.account_ids == []
    assert "più basso" in client.post(f"/tax/limits/{pir.id}/edit", data={"name": "x", "yearly": "10", "total": "5",
                                      "account_ids": [money["pir"]]}, follow_redirects=True).get_data(as_text=True)
    assert client.post(f"/tax/limits/{pir.id}/delete").status_code == 302
    assert ContributionLimit.query.count() == 0
