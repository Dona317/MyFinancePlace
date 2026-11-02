"""F20g: where the net worth growth comes from — saving, markets, debt repaid, new assets."""
from datetime import date
from decimal import Decimal

from app.models.account import Account
from app.models.wealth import Debt, Holding, HoldingPrice
from app.services import net_worth_growth
from tests.conftest import make_tx

TODAY = date(2026, 10, 13)


def test_months(app, db):
    current = Account(name="Corrente", kind="current", opening_balance=Decimal("10000"))
    etf = Holding(name="ETF", asset_class="ETF", quantity=10, avg_price=100, current_price=120,
                  purchase_date=date(2026, 1, 10), opening_quantity=0, opening_price=0)
    house = Holding(name="Casa", asset_class="Immobile", quantity=1, avg_price=200000, current_price=200000,
                    purchase_date=date(2026, 9, 15))
    loan = Debt(name="Prestito", type="Prestito Auto", principal=12000, annual_rate=0, term_months=12,
                start_date=date(2026, 1, 1))
    db.session.add_all([current, etf, house, loan])
    db.session.flush()
    db.session.add_all([
        HoldingPrice(holding_id=etf.id, on=date(2026, 8, 31), price=100),
        HoldingPrice(holding_id=etf.id, on=date(2026, 9, 30), price=110),
        make_tx(description="Stipendio", type="income", category="Stipendio", amount=Decimal("3000"),
                date=date(2026, 9, 27), account_id=current.id),
        make_tx(description="Spesa", amount=Decimal("1000"), category="Alimentari", date=date(2026, 9, 10),
                account_id=current.id),
        make_tx(description="Acquisto ETF", type="transfer", category="Investimenti", amount=Decimal("500"),
                date=date(2026, 9, 12), account_id=current.id, holding_id=etf.id, units=Decimal(5),
                unit_price=Decimal(100)),
    ])
    db.session.commit()
    with app.test_request_context():
        rows = net_worth_growth.months(2, TODAY)
    september = rows[0]
    assert september.end == date(2026, 9, 30)
    assert september.savings == 2000 and september.new_assets == 200000 and september.debt_repaid == 1000
    # the ETF went from 5 units × 100 to 10 × 110: +600, of which 500 € bought in the month — a gain of 100
    assert september.markets == 100
    assert september.change == 203100 and september.other == 0
    v = net_worth_growth.velocity(rows)
    assert v["monthly"] == round(sum(r.change for r in rows) / 2, 2)
    assert net_worth_growth.velocity([]) == {"monthly": 0.0, "savings": 0.0, "markets": 0.0, "savings_share": None}


def test_page(client, db):
    page = client.get("/accounting/growth?months=24").get_data(as_text=True)
    assert "Crescita del patrimonio" in page and "growthChart" in page and 'value="24" selected' in page
    assert 'value="12" selected' in client.get("/accounting/growth?months=5").get_data(as_text=True)
