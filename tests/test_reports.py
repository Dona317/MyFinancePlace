"""Report page: spending / income / cash flow by period and account, split by category, list by day, summary."""
from datetime import date
from decimal import Decimal

from app.models.account import Account
from app.services import reports
from tests.conftest import make_tx


def test_period_ranges():
    today = date(2026, 9, 30)
    assert reports.period_range("this_month", today=today) == (date(2026, 9, 1), date(2026, 10, 1))
    assert reports.period_range("last_month", today=today) == (date(2026, 8, 1), date(2026, 9, 1))
    assert reports.period_range("last_3", today=today) == (date(2026, 7, 1), date(2026, 10, 1))
    assert reports.period_range("last_year", today=today) == (date(2025, 1, 1), date(2026, 1, 1))
    # custom: both ends included, in any order
    assert reports.period_range("custom", date(2026, 3, 31), date(2026, 1, 1), today=today) == (date(2026, 1, 1), date(2026, 4, 1))
    assert reports.previous_range(date(2026, 7, 1), date(2026, 10, 1)) == (date(2026, 4, 1), date(2026, 7, 1))


def test_spending_split_list_by_day_and_summary(client, db):
    db.session.add_all([
        make_tx(date=date(2026, 6, 3), description="Esselunga", category="Alimentari", amount=60),
        make_tx(date=date(2026, 6, 3), description="Cena", category="Ristoranti", amount=40),
        make_tx(date=date(2026, 6, 10), description="Affitto", category="Casa", amount=700),
        make_tx(date=date(2026, 6, 27), description="Stipendio", category="Stipendio", amount=2000, type="income"),
        make_tx(date=date(2026, 5, 10), description="Affitto", category="Casa", amount=400),  # previous month
    ])
    db.session.commit()
    html = client.get("/reports/?period=custom&start=2026-06-01&end=2026-06-30").get_data(as_text=True)
    legend = html.split('<ul class="report-legend">')[1].split("</ul>")[0]
    assert legend.index("Casa") < legend.index("Alimentari") < legend.index("Ristoranti")  # biggest first
    assert "(87,5%)" in legend and "Stipendio" not in legend  # 700 of 800; income is on its own tab
    # the list: one heading per day with the day's total, newest first
    assert html.index("10/06/2026") < html.index("03/06/2026")
    day = html.split("03/06/2026")[1][:200]
    assert "−€ 100,00" in day.split("</div>")[0]  # 60 + 40 spent that day
    summary = html.split('class="card report-summary"')[1]
    assert ">3<" in summary and "€ 700,00" in summary and "€ 800,00" in summary and "Affitto" in summary
    # the same period one month earlier, for comparison
    assert "+100% rispetto al periodo precedente (€ 400,00)" in summary


def test_category_drill_down_and_income_tab(client, db):
    db.session.add_all([
        make_tx(date=date.today(), description="Coop", category="Alimentari", amount=30),
        make_tx(date=date.today(), description="Treno", category="Trasporti", amount=12),
        make_tx(date=date.today(), description="Bonus", category="Stipendio", amount=500, type="income"),
    ])
    db.session.commit()
    html = client.get("/reports/?category=Alimentari").get_data(as_text=True)
    listed = html.split('class="report-list"')[1].split('class="card report-summary"')[0]
    assert "Coop" in listed and "Treno" not in listed and 'class="selected"' in html
    income = client.get("/reports/?tab=income").get_data(as_text=True)
    assert "Bonus" in income and "Coop" not in income.split('class="report-list"')[1]


def test_account_filter_and_cash_flow(client, db):
    main, card = Account(name="Conto"), Account(name="Carta", kind="card")
    db.session.add_all([main, card])
    db.session.flush()
    db.session.add_all([
        make_tx(date=date(2026, 2, 5), description="Spesa carta", amount=80, account_id=card.id),
        make_tx(date=date(2026, 2, 6), description="Spesa conto", amount=20, account_id=main.id),
        make_tx(date=date(2026, 3, 27), description="Stipendio", amount=1000, type="income", account_id=main.id),
    ])
    db.session.commit()
    html = client.get(f"/reports/?period=custom&start=2026-01-01&end=2026-03-31&account={card.id}").get_data(as_text=True)
    assert "Spesa carta" in html and "Spesa conto" not in html
    flow = reports.cash_flow(reports.base_query(date(2026, 1, 1), date(2026, 4, 1)), date(2026, 1, 1), date(2026, 4, 1))
    assert flow["income"] == [0, 0, 1000] and flow["expenses"] == [0, 100, 0]
    assert flow["net_total"] == 900 and round(flow["savings_rate"]) == 90
    page = client.get("/reports/?tab=cashflow&period=custom&start=2026-01-01&end=2026-03-31").get_data(as_text=True)
    assert 'id="flowChart"' in page and "€ 900,00" in page


def test_csv_has_the_listed_transactions(client, db):
    db.session.add_all([make_tx(date=date.today(), description="Coop", category="Alimentari", amount=Decimal("30")),
                        make_tx(date=date.today(), description="Treno", category="Trasporti", amount=12)])
    db.session.commit()
    response = client.get("/reports/csv?category=Trasporti")
    body = response.get_data(as_text=True)
    assert response.mimetype == "text/csv" and "Treno" in body and "Coop" not in body


def test_sidebar_link(client, db):
    html = client.get("/reports/").get_data(as_text=True)
    assert 'href="/reports/"' in html and "nav-item active" in html.split('href="/reports/"')[1][:80]
