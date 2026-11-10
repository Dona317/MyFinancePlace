"""
F47/F49: the value of the investments month by month from the prices (not the snapshots) against the money put in,
the year × month table of returns and the fall from the peak.
"""
from datetime import date
from decimal import Decimal

from app.models.account import Account
from app.models.wealth import Holding, HoldingPrice
from app.services import performance, portfolio_ops
from app.services.portfolio_ops import Operation


def _book(app, db):
    directa = Account(name="Directa", kind="other")
    etf = Holding(name="All-World", asset_class="ETF", quantity=10, avg_price=100, purchase_date=date(2025, 1, 2),
                  opening_quantity=10, opening_price=100, opening_date=date(2025, 1, 2))
    db.session.add_all([directa, etf])
    db.session.commit()
    for on, price in ((date(2025, 1, 31), 100), (date(2025, 2, 28), 110), (date(2025, 3, 31), 99),
                      (date(2025, 4, 30), 104.5)):
        db.session.add(HoldingPrice(holding_id=etf.id, on=on, price=Decimal(str(price))))
    db.session.commit()
    with app.test_request_context():
        portfolio_ops.record(etf, Operation("buy", date(2025, 3, 10), directa, units=Decimal(5), price=Decimal(100),
                                            fee=Decimal(2)))
        etf.current_price, etf.price_date = Decimal("104.5"), date(2025, 4, 30)
        db.session.commit()
    return etf


def test_value_against_money_put_in(app, db):
    etf = _book(app, db)
    series = performance.value_series([etf], date(2025, 4, 30))
    assert series["labels"][:4] == ["12/24", "01/25", "02/25", "03/25"]
    assert series["value"][1:4] == [1000.0, 1100.0, 1485.0]  # 10 × 100, 10 × 110, 15 × 99
    assert series["invested"][1:4] == [1000.0, 1000.0, 1502.0]  # + 5 × 100 + 2 of commission in March
    assert series["value"][-1] == 1567.5 and series["invested"][-1] == 1502.0


def test_monthly_table_and_fall_from_the_peak(app, db):
    etf = _book(app, db)
    report = performance.report([etf], date(2025, 4, 30))
    assert set(report.heatmap) == {2025}
    feb, mar = report.heatmap[2025][1], report.heatmap[2025][2]
    assert feb == 10.0 and mar < 0
    assert report.drawdowns[0] == 0 and min(report.drawdowns) < 0 and len(report.drawdowns) == len(report.returns)


def test_pages_show_the_new_charts(client, db):
    _book(client.application, db)
    page = client.get("/portfolio/").text
    assert "valueInvestedChart" in page and "Valore e versato" in page
    perf = client.get("/portfolio/performance").text
    assert "Rendimenti mese per mese" in perf and "drawdownChart" in perf and "Feb" in perf
