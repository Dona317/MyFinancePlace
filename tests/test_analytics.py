from datetime import date

from app.services import analytics


def test_totals_and_savings_rate(sample_data):
    result = analytics.totals(date(2026, 6, 1), date(2026, 7, 1))
    assert result["income"] == 3000
    assert result["expenses"] == 800
    assert result["net"] == 2200
    assert result["savings_rate"] == 73.3


def test_savings_rate_without_income():
    assert analytics.savings_rate(0, 100) == 0.0


def test_category_breakdown_sorted_with_shares(sample_data):
    breakdown = analytics.category_breakdown(date(2026, 6, 1), date(2026, 7, 1))
    assert [c["category"] for c in breakdown] == ["Casa", "Alimentari", "Abbonamenti"]
    assert breakdown[0]["share"] == 75.0


def test_monthly_series(sample_data):
    series = analytics.monthly_series(2026)
    assert series["income"][4] == 2800 and series["income"][5] == 3000
    assert series["expenses"][5] == 800
    assert series["net"][5] == 2200
    assert sum(series["income"]) == 5800  # December 2025 bonus excluded


def test_last_12_months_crosses_year_boundary(sample_data):
    data = analytics.last_12_months(date(2026, 6, 15))
    assert data["labels"][0] == "Lug 25" and data["labels"][-1] == "Giu 26"
    assert data["income"][5] == 1000  # Dec 2025
    assert data["income"][-1] == 3000


def test_dashboard_kpis(sample_data):
    kpis = analytics.dashboard_kpis(date(2026, 6, 15))
    assert kpis["monthly_income"] == 3000
    assert kpis["monthly_expenses"] == 800
    assert kpis["net_worth"] == 3000 + 2800 + 1000 - 800 - 600
    assert kpis["emergency_months"] > 0


def test_cash_flow_classifies_investment_transfers(sample_data):
    report = analytics.cash_flow(2026)
    assert report["operating"] == 5800 - 1400
    assert report["investing"] == -500
    assert report["financing"] == 0
    assert report["net_change"] == 5800 - 1400 - 500
    assert report["cumulative"][-1] == report["net_change"]


def test_income_statement_lines(sample_data):
    report = analytics.income_statement(2026)
    assert report["income_lines"][0] == {
        "category": "Stipendio", "amount": 5800.0, "share": 100.0, "share_of_income": 100.0,
    }
    assert {line["category"] for line in report["expense_lines"]} == {"Casa", "Alimentari", "Abbonamenti"}


def test_lifestyle_month_over_month(sample_data):
    report = analytics.lifestyle_report(2026, today=date(2026, 6, 15))
    casa = next(r for r in report["rows"] if r["category"] == "Casa")
    assert casa["this_month"] == 600 and casa["last_month"] == 600 and casa["change"] == 0
    alimentari = next(r for r in report["rows"] if r["category"] == "Alimentari")
    assert alimentari["change"] is None
    assert report["top_category"] == "Casa"
    assert report["discretionary_share"] == round(50 / 1400 * 100, 1)


def test_available_years(sample_data):
    assert analytics.available_years() == [2026, 2025]


def test_available_years_empty_db(app):
    assert analytics.available_years() == [date.today().year]
