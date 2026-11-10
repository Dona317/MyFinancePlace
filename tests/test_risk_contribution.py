"""F58/F59: risk measures from the monthly returns, the contribution of each holding, several benchmarks."""
import math
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.currency import ExchangeRate
from app.models.wealth import Holding, HoldingPrice
from app.services import data_health, performance, portfolio_ops, price_feed, settings_store
from app.services.portfolio_ops import Operation
from tests.conftest import make_tx

TODAY = date(2026, 4, 15)


# ── Risk, from given monthly returns ───────────────────────────────────────────

def test_sharpe_and_sortino_by_hand():
    returns = [0.02, -0.01, 0.03, -0.02]
    # mean 0,5 %; deviations ±1,5 and ±2,5 points: variance (2×0,000225 + 2×0,000625) / 3 = 0,00056667
    sd = math.sqrt(0.0017 / 3)
    assert performance.sharpe(returns, 0.0) == pytest.approx(0.005 / sd * math.sqrt(12))
    assert round(performance.sharpe(returns, 0.0), 2) == 0.73
    # only the two negative months: √((0,01² + 0,02²) / 4) = 0,01118
    assert performance.downside_deviation(returns, 0.0) == pytest.approx(math.sqrt(0.0005 / 4))
    assert round(performance.sortino(returns, 0.0), 2) == 1.55
    # 2 % a year is 0,165 % a month: a lower Sharpe
    rf = performance.monthly_rate(2.0)
    assert rf == pytest.approx(1.02 ** (1 / 12) - 1) and round(rf * 100, 3) == 0.165
    assert performance.sharpe(returns, rf) == pytest.approx((0.005 - rf) / sd * math.sqrt(12))
    assert performance.sharpe([0.01], 0.0) is None and performance.sharpe([0.01, 0.01], 0.0) is None
    assert performance.sortino([0.01, 0.02], 0.0) is None  # never below the rate: no downside
    assert performance.downside_deviation([], 0.0) is None and performance.sortino([0.01], 0.0) is None


def test_drawdown_duration_by_hand():
    # levels 1,10 (peak, month 1) · 0,99 · 1,0395 · 1,1019 (back above: 3 months) · 1,0909 (below again, ongoing)
    returns = [0.10, -0.10, 0.05, 0.06, -0.01]
    assert performance.drawdown_spells(returns) == [(1, 4), (4, None)]
    assert performance.drawdown_spells([0.01, 0.02]) == []
    assert performance.drawdown_spells([-0.05, 0.01]) == [(0, None)]
    result = performance.Report(labels=[f"m{i}" for i in range(5)])
    performance._risk(result, returns)
    assert (result.drawdown_months, result.drawdown_recovered, result.underwater_months) == (3, True, 1)
    result = performance.Report(labels=["a", "b", "c"])
    performance._risk(result, [-0.05, 0.01, 0.01])  # 3 months under the start and still under
    assert (result.drawdown_months, result.drawdown_recovered, result.underwater_months) == (3, False, 3)
    assert result.best_12 is None


def test_best_and_worst_twelve_months():
    returns = [0.01] * 12 + [-0.05]
    windows = performance.rolling_12(returns)
    assert [i for i, _r in windows] == [11, 12]
    assert windows[0][1] == pytest.approx(1.01 ** 12 - 1) and windows[1][1] == pytest.approx(1.01 ** 11 * 0.95 - 1)
    result = performance.Report(labels=[f"m{i}" for i in range(13)])
    performance._risk(result, returns)
    assert result.best_12 == ("m11", 12.68) and result.worst_12 == ("m12", 5.99)


def test_risk_free_setting(app, db):
    with app.test_request_context():
        assert performance.risk_free() == 2.0
        performance.save_risk_free(3.5)
        assert performance.risk_free() == 3.5
        with pytest.raises(ValueError):
            performance.save_risk_free(80)
        settings_store.set(performance.RISK_FREE_KEY, "boh")
        assert performance.risk_free() == 2.0


# ── A portfolio: one holding kept, one sold, commissions and a tax ─────────────

@pytest.fixture()
def book(db):
    directa = Account(name="Directa", kind="other")
    kept = Holding(name="Tenuto", asset_class="ETF", quantity=0, avg_price=0, purchase_date=date(2025, 12, 1),
                   opening_quantity=0, opening_price=0)
    sold = Holding(name="Venduto", asset_class="Azione", quantity=0, avg_price=0, purchase_date=date(2025, 12, 1),
                   opening_quantity=0, opening_price=0)
    db.session.add_all([directa, kept, sold])
    db.session.flush()
    for day, price in ((date(2025, 12, 31), 100), (date(2026, 1, 31), 110), (date(2026, 2, 28), 99),
                       (date(2026, 3, 31), 110), (date(2026, 4, 15), 115)):
        db.session.add(HoldingPrice(holding_id=kept.id, on=day, price=price))
    for day, price in ((date(2025, 12, 31), 52), (date(2026, 1, 31), 55), (date(2026, 2, 28), 58)):
        db.session.add(HoldingPrice(holding_id=sold.id, on=day, price=price))
    db.session.commit()
    portfolio_ops.record(kept, Operation("buy", date(2025, 12, 10), directa, units=Decimal(10), price=Decimal(100),
                                         fee=Decimal(1)))
    portfolio_ops.record(kept, Operation("dividend", date(2026, 3, 20), directa, amount=Decimal(11)))
    portfolio_ops.record(sold, Operation("buy", date(2025, 12, 15), directa, units=Decimal(10), price=Decimal(50),
                                         fee=Decimal(2)))
    portfolio_ops.record(sold, Operation("sell", date(2026, 3, 10), directa, units=Decimal(10), price=Decimal(60),
                                         fee=Decimal(3)))
    portfolio_ops.record(sold, Operation("tax", date(2026, 3, 10), directa, amount=Decimal(20)))
    kept.current_price, kept.price_date = Decimal(115), TODAY
    db.session.commit()
    return kept, sold


def test_contributions_add_up(app, book):
    kept, sold = book
    with app.test_request_context():
        found = performance.contributions([kept, sold], "all", TODAY)
    rows = {r.holding.name: r for r in found["rows"]}
    a, b = rows["Tenuto"], rows["Venduto"]
    # Tenuto: worth 10 × 115 = 1.150, 1.000 put in, 11 of dividend, 1 of commission
    assert (a.start_value, a.end_value, a.put, a.gain, a.income, a.fees, a.taxes) == (0, 1150, 1000, 150, 11, 1, 0)
    assert a.total == 160
    # Venduto: bought for 500, sold for 600 (realized +100), commissions 2 + 3, tax 20
    assert (b.end_value, b.put, b.gain, b.fees, b.taxes, b.total) == (0, -100, 100, 5, 20, 75)
    assert found["total"] == 235 and found["fees"] == 6 and found["taxes"] == 20
    assert [r.holding.name for r in found["rows"]] == ["Tenuto", "Venduto"]  # biggest first
    # points on the average capital: 136 days from 30/11; each flow weighted by the days it stayed in
    capital = 1000 * 126 / 136 + 500 * 121 / 136 - 600 * 36 / 136
    assert found["capital"] == round(capital, 2)
    assert a.points == round(160 / capital * 100, 2) and b.points == round(75 / capital * 100, 2)
    assert found["points"] == round(235 / capital * 100, 2)
    assert a.points + b.points == pytest.approx(found["points"], abs=0.011)


def test_contributions_since_january(app, book):
    kept, sold = book
    with app.test_request_context():
        found = performance.contributions([kept, sold], "ytd", TODAY)
        same = performance.contributions([kept, sold], "12", TODAY)  # less than 12 months: from the start
        empty = performance.contributions([], "all", TODAY)
    assert found["start"] == date(2025, 12, 31) and same["start"] == date(2025, 11, 30)
    rows = {r.holding.name: r for r in found["rows"]}
    # Tenuto from 1.000 (10 × 100 on 31/12) to 1.150, the dividend; the commission was in December
    assert (rows["Tenuto"].start_value, rows["Tenuto"].total) == (1000, 161)
    # Venduto from 520 (10 × 52) to the sale for 600: +80, less 3 of commission and 20 of tax
    assert (rows["Venduto"].start_value, rows["Venduto"].gain, rows["Venduto"].total) == (520, 80, 57)
    assert found["total"] == 218 and empty["rows"] == [] and empty["points"] is None


def test_contribution_matches_the_portfolio_values(app, book):
    """The sum is the change in the portfolio's value less the money put in, plus income, less costs; a holding sold
    out counts for what it held at past dates."""
    kept, sold = book
    holdings = [kept, sold]
    with app.test_request_context():
        found = performance.contributions(holdings, "ytd", TODAY)
        start, end = performance._value(holdings, date(2025, 12, 31)), performance._value(holdings, TODAY)
    assert start == 1520 and end == 1150
    assert found["total"] == pytest.approx(end - start - (-600) + 11 - 3 - 20)


def test_contribution_of_an_entered_holding(app, db):
    """A holding without trades that appears in the period counts as money put in at its month-end value."""
    h = Holding(name="Fondo", asset_class="ETF", quantity=5, avg_price=10, current_price=12,
                purchase_date=date(2026, 2, 10))
    db.session.add(h)
    db.session.flush()
    db.session.add_all([HoldingPrice(holding_id=h.id, on=date(2026, 2, 27), price=11),
                        HoldingPrice(holding_id=h.id, on=date(2026, 3, 31), price=12)])
    db.session.commit()
    with app.test_request_context():
        found = performance.contributions([h], "all", date(2026, 3, 31))
        assert performance.contribution_of(h, [], "all") is None
    row = found["rows"][0]
    assert (row.put, row.end_value, row.total) == (55, 60, 5)


# ── Several benchmarks (F59) ───────────────────────────────────────────────────

def test_single_benchmark_moves_into_the_list(app, db):
    with app.test_request_context():
        settings_store.set_json(performance.BENCHMARK_KEY, {"ticker": "VWCE.MI", "prices": {"2026-01-31": 1.0},
                                                            "updated": "2026-02-01"})
        assert [b["ticker"] for b in performance.benchmarks()] == ["VWCE.MI"]
        assert performance.benchmark_settings()["ticker"] == "VWCE.MI"
        performance.save_benchmark("SWDA.MI", {"2026-01-31": 2.0}, TODAY)
        assert [b["ticker"] for b in performance.benchmarks()] == ["VWCE.MI", "SWDA.MI"]
        assert settings_store.get(performance.BENCHMARK_KEY) is None  # moved
        performance.save_benchmark("VWCE.MI", {"2026-01-31": 3.0}, TODAY)  # refreshed in place
        performance.save_benchmark("EIMI.MI", {}, TODAY)
        assert [b["prices"].get("2026-01-31") for b in performance.benchmarks()] == [3.0, 2.0, None]
        assert not performance.can_add_benchmark("CSPX.MI") and performance.can_add_benchmark("SWDA.MI")
        with pytest.raises(ValueError):
            performance.save_benchmark("CSPX.MI", {}, TODAY)
        performance.remove_benchmark("SWDA.MI")
        assert [b["ticker"] for b in performance.benchmarks()] == ["VWCE.MI", "EIMI.MI"]
        performance.save_benchmark("", {}, TODAY)
        assert performance.benchmarks() == [] and performance.benchmark_settings() == {}


def test_report_with_two_benchmarks_and_risk(app, book):
    kept, sold = book
    with app.test_request_context():
        performance.save_risk_free(0)
        performance.save_benchmark("A.MI", {"2025-11-30": 100.0, "2026-03-31": 110.0}, TODAY)
        performance.save_benchmark("B.MI", {"2025-11-30": 50.0, "2026-03-31": 45.0}, TODAY)
        dates, returns = performance.monthly_returns([kept, sold], TODAY)
        r = performance.report([kept, sold], TODAY)
    assert [b["ticker"] for b in r.benchmarks] == ["A.MI", "B.MI"]
    assert r.benchmarks[0]["twr"] == 10.0 and r.benchmarks[1]["twr"] == -10.0
    assert r.benchmark_twr == 10.0 and r.benchmark == r.benchmarks[0]["series"]
    assert [p[0] for p in r.periods] == ["1A", "3A", "5A"] and r.periods[0][2] == [None, None]
    assert r.sharpe == round(performance.sharpe(returns, 0.0), 2) and r.risk_free == 0
    assert r.from_peak == r.drawdowns[-1] and r.from_peak <= 0


def test_pages(client, db, book, monkeypatch):
    monkeypatch.setattr(price_feed, "benchmark_history", lambda ticker: {"2025-11-30": 100.0, "2026-03-31": 110.0})
    for ticker in ("A.MI", "B.MI", "C.MI"):
        client.post("/portfolio/performance", data={"ticker": ticker})
    page = client.post("/portfolio/performance", data={"ticker": "D.MI"}, follow_redirects=True).text
    assert "Al massimo 3 benchmark" in page
    page = client.get("/portfolio/performance?period=ytd").text
    for text in ("Indice di Sharpe", "Indice di Sortino", "Distanza dal massimo", "Durata del calo più lungo",
                 "Contributo dei titoli", "contributionChart", "A.MI", "C.MI", "Venduto"):
        assert text in page
    assert page.count("dash: [6, 4]") == 3
    page = client.post("/portfolio/performance", data={"remove": "B.MI"}, follow_redirects=True).text
    assert "Benchmark tolto." in page and "B.MI" not in page
    page = client.post("/portfolio/performance", data={"risk_free": "3,5"}, follow_redirects=True).text
    assert "Tasso senza rischio salvato." in page and 'value="3,5"' in page
    page = client.post("/portfolio/performance", data={"risk_free": "x"}, follow_redirects=True).text
    assert "Indica un tasso tra -10 e 50" in page
    kept, _sold = book
    assert "Contributo al portafoglio" in client.get(f"/portfolio/{kept.id}").text


# ── Data health (F58) ──────────────────────────────────────────────────────────

def test_data_health_sales_beyond_and_holding_rates(app, db):
    h = Holding(name="Troppo venduto", asset_class="ETF", isin="IE00B4L5Y983", quantity=2, avg_price=10,
                opening_quantity=5, opening_price=10, price_date=date(2026, 4, 1))
    usd = Holding(name="Apple", asset_class="Azione", ticker="AAPL", currency="USD", quantity=1, avg_price=100,
                  price_date=date(2026, 4, 1))
    chf = Holding(name="Nestlé", asset_class="Azione", ticker="NESN.SW", currency="CHF", quantity=1, avg_price=90,
                  price_date=date(2026, 4, 1))
    db.session.add_all([h, usd, chf, ExchangeRate(currency="CHF", on=date(2026, 4, 1), rate=Decimal("1.05"))])
    db.session.flush()
    db.session.add_all([  # 5 held, 8 sold on 2 March (before the purchase of 5 on the 10th): 3 too many
        make_tx(description="Vendita", type="transfer", amount=Decimal(80), date=date(2026, 3, 2), holding_id=h.id,
                units=Decimal(-8), unit_price=Decimal(10)),
        make_tx(description="Acquisto", type="transfer", amount=Decimal(50), date=date(2026, 3, 10), holding_id=h.id,
                units=Decimal(5), unit_price=Decimal(10)),
        make_tx(description="Stesso giorno", type="transfer", amount=Decimal(10), date=date(2026, 3, 12),
                holding_id=usd.id, units=Decimal(-1), unit_price=Decimal(10)),
        make_tx(description="Stesso giorno", type="transfer", amount=Decimal(10), date=date(2026, 3, 12),
                holding_id=usd.id, units=Decimal(1), unit_price=Decimal(10)),
    ])
    db.session.commit()
    with app.test_request_context():
        checks = {c.key: c for c in data_health.run(date(2026, 4, 2))}
    assert checks["sold_beyond"].count == 1 and checks["sold_beyond"].level == "danger"
    assert checks["sold_beyond"].items[0].label == "Troppo venduto — 02/03/2026: vendute 8, possedute 5"
    assert checks["holding_rates"].count == 1 and checks["holding_rates"].items[0].label == "Apple — USD"
