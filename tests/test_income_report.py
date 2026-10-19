"""F20c: passive income — dividends, coupons and interest by month, year and holding, with yields."""
from datetime import date
from decimal import Decimal

from app.models.wealth import Holding
from app.services import income_report
from tests.conftest import make_tx

TODAY = date(2026, 10, 13)


def _book(db):
    etf = Holding(name="All-World", asset_class="ETF", quantity=100, avg_price=100, current_price=125)
    btp = Holding(name="BTP 2030", asset_class="Obbligazione", quantity=10000, avg_price=1, current_price=1)
    db.session.add_all([etf, btp])
    db.session.flush()
    db.session.add_all([
        make_tx(description="Dividendo VWCE", type="income", category="Dividendi e cedole", amount=Decimal("80"),
                date=date(2026, 3, 25), holding_id=etf.id),
        make_tx(description="Dividendo VWCE", type="income", category="Dividendi e cedole", amount=Decimal("90"),
                date=date(2025, 9, 25), holding_id=etf.id),
        make_tx(description="Cedola BTP", type="income", category="Dividendi e cedole", amount=Decimal("150"),
                date=date(2026, 6, 1), holding_id=btp.id),
        make_tx(description="Interessi conto deposito", type="income", category="Interessi", amount=Decimal("30"),
                date=date(2026, 6, 30)),
        make_tx(description="Stipendio", type="income", category="Stipendio", amount=Decimal("2000"), date=date(2026, 6, 27)),
        make_tx(description="Dividendo vecchio", type="income", category="Dividendi e cedole", amount=Decimal("10"),
                date=date(2024, 5, 1)),
    ])
    db.session.commit()
    return etf, btp


def test_report(app, db):
    etf, btp = _book(db)
    with app.test_request_context():
        r = income_report.report(2026, TODAY)
        kinds = [p.kind for p in income_report.payments()]
    assert kinds == ["dividend", "dividend", "dividend", "coupon", "interest"]  # by date; the salary is not income
    assert r["months"]["dividend"][2] == Decimal(80) and r["months"]["coupon"][5] == Decimal(150)
    assert r["months"]["interest"][5] == Decimal(30) and r["total"] == Decimal(260)
    assert r["by_year"] == [(2024, Decimal(10)), (2025, Decimal(90)), (2026, Decimal(260))]
    assert r["last_12"] == Decimal(260) and r["monthly_average"] == Decimal("21.67")  # since 13/10/2025
    assert r["years"] == [2026, 2025, 2024]
    rows = {row.holding.name: row for row in r["holdings"]}
    assert (rows["BTP 2030"].year, rows["All-World"].last_12) == (Decimal(150), Decimal(80))
    assert round(rows["All-World"].yield_on_cost, 2) == 0.8 and round(rows["All-World"].yield_on_value, 2) == 0.64
    with app.test_request_context():
        assert len(income_report.payments(date(2026, 1, 1), date(2026, 3, 31))) == 1


def test_yields_without_cost(app, db):
    gift = Holding(name="Regalo", asset_class="Azione", quantity=0, avg_price=0)
    assert income_report.HoldingIncome(gift, Decimal(1), Decimal(1)).yield_on_cost is None
    assert income_report.HoldingIncome(gift, Decimal(1), Decimal(1)).yield_on_value is None


def test_page(client, db):
    assert "Ancora nessuna rendita" in client.get("/portfolio/income").get_data(as_text=True)
    _book(db)
    page = client.get("/portfolio/income?year=2026").get_data(as_text=True)
    assert "BTP 2030" in page and "incomeChart" in page and "€ 260,00" in page
