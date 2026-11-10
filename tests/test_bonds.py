"""Bonds as real instruments (F53): the coupon schedule, the accrued interest, the yield to maturity, the form and
the pages — on a BTP worked by hand."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.wealth import Holding
from app.services import bonds

TODAY = date(2026, 11, 10)


def btp(**overrides) -> Holding:
    """BTP 3,5 % semiannual maturing in five years, 10.000 € nominal bought and quoted at 98."""
    values = dict(name="BTP 3,5% 2031", asset_class="Obbligazione", bond_type="btp", coupon_rate=Decimal("3.5"),
                  coupon_frequency=2, maturity_date=date(2031, 11, 10), quantity=10000, avg_price=Decimal("0.98"),
                  current_price=Decimal("0.98"), multiplier=1)
    values.update(overrides)
    return Holding(**values)


def test_the_schedule_steps_back_from_the_maturity():
    coupons = bonds.schedule(btp(), TODAY)
    # ten semiannual coupons of 10.000 × 3,5 % / 2 = 175 €, net of 12,5 % = 153,125 €; today's is already paid
    assert [c.on for c in coupons[:3]] == [date(2027, 5, 10), date(2027, 11, 10), date(2028, 5, 10)]
    assert len(coupons) == 10 and coupons[-1].on == date(2031, 11, 10)
    assert all(c.gross == pytest.approx(175) and c.net == pytest.approx(153.125) for c in coupons)
    assert coupons[-1].redemption == pytest.approx(10000) and not any(c.redemption for c in coupons[:-1])
    assert bonds.next_coupon(btp(), TODAY).on == date(2027, 5, 10)
    assert bonds.years_to_maturity(btp(), TODAY) == pytest.approx(5, abs=0.01)
    # until: only what falls in the window; a first coupon date drops the grid before it
    assert [c.on for c in bonds.schedule(btp(), TODAY, date(2027, 11, 10))] == [date(2027, 5, 10), date(2027, 11, 10)]
    assert bonds.schedule(btp(first_coupon_date=date(2029, 5, 10)), TODAY)[0].on == date(2029, 5, 10)
    assert bonds.schedule(btp(), date(2031, 11, 10)) == [] and bonds.schedule(btp(maturity_date=None)) == []


def test_month_ends_and_quarterly_and_annual_grids():
    end_of_month = btp(maturity_date=date(2030, 8, 31))
    assert [c.on for c in bonds.schedule(end_of_month, date(2029, 8, 31))] == [date(2030, 2, 28), date(2030, 8, 31)]
    quarterly = btp(coupon_frequency=4, maturity_date=date(2027, 12, 1))
    assert [c.on.month for c in bonds.schedule(quarterly, TODAY)] == [12, 3, 6, 9, 12]
    assert bonds.schedule(quarterly, TODAY)[0].gross == pytest.approx(87.5)
    annual = btp(coupon_frequency=None, maturity_date=date(2028, 6, 1))  # not set: one a year
    assert [c.on for c in bonds.schedule(annual, TODAY)] == [date(2027, 6, 1), date(2028, 6, 1)]


def test_accrued_interest_act_act_on_the_current_period():
    # 10 Feb 2027: 92 days of the 181 from 10 Nov 2026 to 10 May 2027 → 1,75 × 92 / 181 = 0,8895 % of the nominal
    assert bonds.accrued_pct(btp(), date(2027, 2, 10)) == pytest.approx(1.75 * 92 / 181)
    gross, net = bonds.accrued(btp(), date(2027, 2, 10))
    assert gross == pytest.approx(88.95, abs=0.01) and net == pytest.approx(gross * 0.875)
    assert bonds.accrued_pct(btp(), TODAY) == 0  # on a coupon date nothing has accrued yet
    assert bonds.accrued_pct(btp(), date(2032, 1, 1)) == 0  # past the maturity
    assert bonds.accrued_pct(btp(bond_type="bot"), date(2027, 2, 10)) == 0  # a zero coupon accrues nothing
    assert bonds.accrued_pct(btp(first_coupon_date=date(2029, 5, 10)), date(2027, 2, 10)) == 0


def test_yield_to_maturity_gross_and_net():
    # by hand: 98 = Σ 1,75 / (1 + y/2)^k + 100 / (1 + y/2)^10 → y = 3,945 % semiannual, 3,984 % effective a year;
    # net: coupons of 1,53125 and 100 − 12,5 % × 2 = 99,75 at maturity → 3,485 % a year
    assert bonds.yield_to_maturity(btp(), on=TODAY) == pytest.approx(3.984, abs=0.01)
    assert bonds.yield_to_maturity(btp(), on=TODAY, net=True) == pytest.approx(3.485, abs=0.01)
    assert bonds.yield_to_maturity(btp(), price=100, on=TODAY) == pytest.approx(3.531, abs=0.01)  # (1,0175)² − 1
    # between two coupons the accrued interest is paid on top of the price: the yield stays about the same
    assert bonds.yield_to_maturity(btp(), on=date(2027, 2, 10)) == pytest.approx(3.99, abs=0.03)
    # a BOT: 12 months at 97 → 100 / 97 − 1 = 3,09 %; a corporate's net yield at 26 %
    bot = btp(bond_type="bot", coupon_rate=None, maturity_date=date(2027, 11, 10), current_price=Decimal("0.97"))
    assert bonds.yield_to_maturity(bot, on=TODAY) == pytest.approx(3.093, abs=0.01)
    assert [c.redemption for c in bonds.schedule(bot, TODAY)] == [pytest.approx(10000)]
    assert bonds.next_coupon(bot, TODAY) is None
    corporate = btp(bond_type="corporate", maturity_date=date(2027, 11, 10), current_price=Decimal("1"))
    assert bonds.tax_rate(corporate) == 26 and bonds.yield_to_maturity(corporate, on=TODAY, net=True) == pytest.approx(
        ((1 + 1.75 * 0.74 / 100) * (1 + 1.75 * 0.74 / 100) - 1) * 100, abs=0.02)
    assert bonds.tax_rate(btp(tax_rate=Decimal("20"))) == 20
    assert bonds.yield_to_maturity(btp(maturity_date=date(2020, 1, 1)), on=TODAY) is None
    assert bonds.yield_to_maturity(btp(), price=1e15, on=TODAY) is None  # no rate solves it


def test_summary_and_upcoming():
    summary = bonds.summary(btp(), TODAY)
    assert summary["type"] == "BTP" and summary["frequency"] == "Semestrale" and summary["price_pct"] == pytest.approx(98)
    assert len(summary["coupons"]) == 6 and summary["ytm"] == pytest.approx(3.984, abs=0.01)
    assert bonds.summary(Holding(name="ETF", asset_class="ETF", quantity=1, avg_price=1)) is None
    assert bonds.summary(btp(maturity_date=None)) is None
    etf = Holding(name="ETF", asset_class="ETF", quantity=1, avg_price=1, multiplier=1)
    upcoming = bonds.upcoming([btp(), etf, btp(name="Venduto", quantity=0)], TODAY)
    assert [c.on for _, c in upcoming["rows"]] == [date(2027, 5, 10), date(2027, 11, 10)]
    assert upcoming["gross"] == pytest.approx(350) and upcoming["net"] == pytest.approx(306.25)


FORM = {"name": "BTP 3,5% 2031", "asset_class": "Obbligazione", "quantity": "10000", "avg_price": "0,98",
        "current_price": "0,98", "price_source": "manual", "bond_type": "btp", "coupon_rate": "3,5",
        "coupon_frequency": "2", "maturity_date": "2031-11-10", "redemption": "100", "first_coupon_date": "2022-05-10",
        "issue_price": "99,5"}


def test_the_form_round_trip_and_the_pages(client, db):
    assert "Caratteristiche dell'obbligazione" in client.get("/portfolio/new").text
    assert client.post("/portfolio/new", data=FORM).status_code == 302
    bond = Holding.query.one()
    assert (bond.bond_type, bond.coupon_rate, bond.coupon_frequency, bond.maturity_date, bond.redemption,
            bond.first_coupon_date, bond.issue_price) == ("btp", Decimal("3.5000"), 2, date(2031, 11, 10),
                                                          Decimal("100.000"), date(2022, 5, 10), Decimal("99.5000"))
    page = client.get(f"/portfolio/{bond.id}").text
    assert 'id="bond-card"' in page and "Rendimento a scadenza netto" in page and "Prossime cedole" in page
    assert "Rateo maturato" in page
    edit = client.get(f"/portfolio/{bond.id}/edit").text
    assert 'value="3.5' in edit or 'value="3,5' in edit
    income = client.get("/portfolio/income").text
    assert 'id="bond-coupons"' in income and "BTP 3,5% 2031" in income
    # wrong values are refused and nothing changes
    for field, value, message in (("coupon_rate", "60", "Cedola annua lorda"), ("coupon_frequency", "3", "scelta non valida"),
                                  ("redemption", "0", "Rimborso a scadenza"), ("issue_price", "2000", "Prezzo di emissione"),
                                  ("bond_type", "xyz", "scelta non valida"),
                                  ("first_coupon_date", "2032-01-01", "dopo la scadenza")):
        assert message in client.post(f"/portfolio/{bond.id}/edit", data=FORM | {field: value}).text
    assert Holding.query.one().coupon_rate == Decimal("3.5000")
    # emptied: no bond terms, no bond card
    blank = {k: "" for k in ("bond_type", "coupon_rate", "coupon_frequency", "maturity_date", "redemption",
                             "first_coupon_date", "issue_price")}
    assert client.post(f"/portfolio/{bond.id}/edit", data=FORM | blank).status_code == 302
    bond = Holding.query.one()
    assert (bond.bond_type, bond.coupon_frequency, bond.maturity_date) == (None, None, None)
    assert 'id="bond-card"' not in client.get(f"/portfolio/{bond.id}").text
    assert 'id="bond-coupons"' not in client.get("/portfolio/income").text
