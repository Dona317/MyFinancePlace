"""
The fee calculator: basis points a year on price × quantity of each asset plus the liquidity, with TER and stamp duty.
"""
from datetime import date
from decimal import Decimal

from app.models.account import Account
from app.models.securities import SecuritiesAccount
from app.models.wealth import Holding
from app.services import fee_calculator
from app.services.fee_calculator import Result, Row, number


def test_the_numbers_of_a_year():
    rows = [Row("All-World", Decimal(100), Decimal(110), Decimal("0.22")), Row("Enel", Decimal(500), Decimal(8))]
    r = Result(rows, Decimal(5000), Decimal(50))
    assert (r.invested, r.total) == (Decimal(15000), Decimal(20000))
    assert r.fee == Decimal("100.00")            # 0,50 % of 20.000, the liquidity included
    assert r.ter == Decimal("24.20")             # 0,22 % of the 11.000 of the ETF; the share has no TER
    assert r.stamp == Decimal("30.00")           # 0,2 % of the securities, not of the liquidity
    assert r.costs == Decimal("154.20") and r.costs_pct == Decimal("0.771") and r.over_years == Decimal("1542.00")
    bare = Result(rows, Decimal(0), Decimal(0), with_ter=False, with_stamp=False)
    assert (bare.fee, bare.ter, bare.stamp, bare.costs) == (0, 0, 0, 0)
    assert Result([], Decimal(0), Decimal(10)).costs_pct == 0


def test_numbers_typed_on_the_page():
    assert number("1.234,5") == Decimal("1234.5") and number("1234.5") == Decimal("1234.5")
    assert number("€ 10") == Decimal(10) and number("0,22 %") == Decimal("0.22")
    assert number("", Decimal(3)) == 3 and number("abc") is None and number("NaN") is None


def test_the_form_is_read_with_its_edits():
    form = {"count": "4", "name-0": "ETF", "units-0": "10", "price-0": "100", "ter-0": "0,2",
            "name-1": "", "units-1": "5", "price-1": "20", "ter-1": "-1",
            "units-2": "x", "price-2": "1", "units-3": "-1", "price-3": "1",
            "cash": "1.000", "bps": "100", "with_ter": "1", "years": "99"}
    r = fee_calculator.from_form(form)
    assert [(row.name, row.value, row.ter) for row in r.rows] == [("ETF", 1000, Decimal("0.2")), ("—", 100, None)]
    assert (r.cash, r.bps, r.with_ter, r.with_stamp, r.years) == (1000, 100, True, False, 50)
    assert r.fee == Decimal("21.00")


def _book(db):
    settle = Account(name="Directa", kind="other", opening_balance=Decimal(4000))
    db.session.add(settle)
    db.session.flush()
    db.session.add(SecuritiesAccount(name="Titoli Directa", settlement_account_id=settle.id, active=True))
    db.session.add(Holding(name="All-World", ticker="VWCE", asset_class="ETF", quantity=10, avg_price=100,
                           current_price=Decimal(110), ter=Decimal("0.22"), opening_quantity=10, opening_price=100,
                           opening_date=date(2025, 1, 2)))
    db.session.commit()


def test_the_page_starts_from_the_positions_and_recomputes(client, db):
    _book(db)
    page = client.get("/portfolio/fees?bps=50")
    assert page.status_code == 200 and "Calcolo commissioni" in page.text
    assert 'name="units-0" value="10"' in page.text and 'name="ter-0" value="0,22"' in page.text
    assert 'name="cash" value="4000"' in page.text
    assert "5.100,00" in page.text and "25,50" in page.text  # 1.100 + 4.000 of liquidity; 0,50 % of it
    posted = client.post("/portfolio/fees", data={"count": "1", "name-0": "All-World", "units-0": "20", "price-0": "110",
                                                  "ter-0": "0,22", "cash": "0", "bps": "100", "years": "10"})
    assert posted.status_code == 200 and "2.200,00" in posted.text and "22,00" in posted.text


def test_one_portfolio_counts_no_liquidity(client, db):
    _book(db)
    from app.services import securities
    folio = securities.default_portfolio()
    db.session.commit()
    rows, cash = fee_calculator.starting_rows(portfolio_id=folio.id)
    assert [r.name for r in rows] == ["All-World"] and cash == 0
    assert client.get(f"/portfolio/fees?portfolio={folio.id}").status_code == 200
