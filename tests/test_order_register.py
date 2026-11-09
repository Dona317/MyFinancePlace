"""
F46: the order register — every operation of every holding in one list, the trade's commission on its row,
filters by portfolio, securities account, holding, kind and period, totals and a CSV.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.securities import Portfolio
from app.models.wealth import Holding
from app.services import order_register, portfolio_ops
from app.services.portfolio_ops import Operation


@pytest.fixture()
def book(app, db):
    directa = Account(name="Directa", kind="other")
    etf = Holding(name="All-World", isin="IE00BK5BQT80", asset_class="ETF", quantity=0, avg_price=0,
                  opening_quantity=0, opening_price=0)
    btp = Holding(name="BTP 2030", asset_class="Obbligazione", quantity=0, avg_price=0, opening_quantity=0,
                  opening_price=0)
    pension = Portfolio(name="Pensione")
    db.session.add_all([directa, etf, btp, pension])
    db.session.commit()
    with app.test_request_context():
        portfolio_ops.record(etf, Operation("buy", date(2025, 2, 3), directa, units=Decimal(10), price=Decimal(100),
                                            fee=Decimal(2), portfolio=pension))
        portfolio_ops.record(etf, Operation("sell", date(2025, 5, 2), directa, units=Decimal(4), price=Decimal(110),
                                            fee=Decimal("1.5"), portfolio=pension, notes="presa di profitto"))
        portfolio_ops.record(btp, Operation("buy", date(2025, 3, 3), directa, units=Decimal(1000),
                                            price=Decimal("0.99")))
        portfolio_ops.record(btp, Operation("coupon", date(2025, 9, 1), directa, amount=Decimal("17.50")))
        portfolio_ops.record(etf, Operation("tax", date(2025, 12, 31), directa, amount=Decimal(4)))
        db.session.commit()
    return directa, etf, btp, pension


def test_every_operation_once_with_the_commission_on_its_trade(app, db, book):
    _directa, etf, btp, pension = book
    found = order_register.register()
    assert [r.kind for r in found.rows] == ["tax", "coupon", "sell", "buy", "buy"]  # newest first, no fee rows
    sale = found.rows[2]
    assert (sale.fee, sale.gross, sale.holding.name) == (Decimal("1.50"), Decimal("440.00"), "All-World")
    t = found.totals
    assert (t["buy"], t["sell"], t["commissions"], t["coupon"], t["tax"]) == (
        Decimal("1990.00"), Decimal("440.00"), Decimal("3.50"), Decimal("17.50"), Decimal("4.00"))
    only = order_register.register(order_register.Filters(portfolio_id=pension.id))
    assert [r.kind for r in only.rows] == ["sell", "buy"]
    assert [r.kind for r in order_register.register(order_register.Filters(holding_id=btp.id, kind="buy")).rows] == ["buy"]
    dated = order_register.register(order_register.Filters(start=date(2025, 3, 1), end=date(2025, 6, 30)))
    assert [r.kind for r in dated.rows] == ["sell", "buy"]
    assert etf.quantity == Decimal(6)


def test_the_page_filters_and_downloads_a_csv(client, db, book):
    _directa, _etf, btp, pension = book
    page = client.get("/portfolio/orders")
    assert page.status_code == 200 and "Registro ordini" in page.text and "BTP 2030" in page.text
    assert "presa di profitto" in page.text  # the note, in its tooltip
    filtered = client.get(f"/portfolio/orders?portfolio={pension.id}&kind=sell").text
    assert "All-World" in filtered and "BTP 2030</a>" not in filtered
    csv = client.get(f"/portfolio/orders?holding={btp.id}&format=csv")
    assert csv.mimetype == "text/csv" and "attachment" in csv.headers["Content-Disposition"]
    lines = csv.text.strip().splitlines()
    assert lines[0].startswith("Data;Operazione;Titolo;ISIN") and len(lines) == 3
    assert "2025-03-03;Acquisto;BTP 2030;;" in lines[2] and ";1000,00000000;0,990000;990,00;;Directa;" in lines[2]
