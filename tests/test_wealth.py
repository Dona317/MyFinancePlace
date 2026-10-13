"""Portfolio, debts, insurance, goals, documents, snapshots and the balance sheet built from them."""
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.wealth import Debt, Document, Goal, Holding, InsurancePolicy, Snapshot
from app.services import settings_store, wealth
from tests.conftest import make_tx
from tests.form_helper import assert_divs_balanced


@pytest.fixture()
def instance(app, tmp_path):
    """Keep uploaded documents and backups out of the real instance folder."""
    app.instance_path = str(tmp_path)
    return tmp_path


def mortgage(**overrides) -> Debt:
    values = dict(name="Mutuo", type="Mutuo", principal=Decimal("150000"), annual_rate=Decimal("3"),
                  term_months=300, start_date=date(2020, 1, 15))
    values.update(overrides)
    return Debt(**values)


# ── Amortization ───────────────────────────────────────────────────────────────

def test_installment_follows_french_amortization():
    assert wealth.installment(mortgage()) == 711.32
    assert wealth.installment(mortgage(annual_rate=0, principal=Decimal("1200"), term_months=12)) == 100
    assert wealth.installment(mortgage(monthly_payment=Decimal("800"))) == 800
    assert wealth.installment(mortgage(term_months=None)) is None


def test_schedule_repays_the_whole_principal():
    plan = wealth.schedule(mortgage())
    assert len(plan) == 300
    assert plan[0].due == date(2020, 2, 15) and plan[0].interest == 375.0
    assert plan[-1].balance == 0
    assert sum(row.principal for row in plan) == pytest.approx(150000, abs=0.05)


def test_balance_on_a_date_and_manual_balance():
    debt = mortgage()
    assert wealth.balance_on(debt, date(2020, 1, 1)) == 0  # not started yet
    assert wealth.balance_on(debt, date(2020, 2, 14)) == 150000
    assert wealth.balance_on(debt, date(2020, 2, 15)) == pytest.approx(149663.68, abs=0.01)
    debt.balance = Decimal("99000")
    assert wealth.balance_on(debt) == 99000  # what the user typed wins today
    assert wealth.balance_on(debt, date(2020, 2, 15)) == pytest.approx(149663.68, abs=0.01)  # the past follows the plan


def test_installment_below_interest_never_ends():
    debt = mortgage(monthly_payment=Decimal("100"))
    assert wealth.never_ends(debt)
    assert wealth.schedule(debt) == []
    assert wealth.debt_summary(debt)["never_ends"]


def test_debt_without_plan_counts_the_principal():
    debt = Debt(name="Prestito amico", type="Altro", principal=Decimal("2000"), annual_rate=0)
    assert wealth.balance_on(debt) == 2000
    assert wealth.debt_summary(debt)["end_date"] is None


# ── Holdings and balance sheet ─────────────────────────────────────────────────

def test_holding_values():
    h = Holding(name="VWCE", asset_class="ETF", quantity=Decimal("10"), avg_price=Decimal("100"),
                current_price=Decimal("120"))
    assert (h.cost, h.value, h.gain, h.gain_pct) == (1000, 1200, 200, 20)
    h.current_price = None
    assert h.value == 1000  # no price yet: worth what it cost


def test_balance_sheet_and_dashboard(db, sample_data):
    db.session.add_all([
        Holding(name="VWCE", asset_class="ETF", quantity=Decimal("10"), avg_price=Decimal("100"), current_price=Decimal("120")),
        Holding(name="Conto deposito", asset_class="Conto Risparmio", quantity=1, avg_price=Decimal("5000")),
        Holding(name="Casa", asset_class="Immobile", quantity=1, avg_price=Decimal("200000")),
        Holding(name="Futuro", asset_class="ETF", quantity=1, avg_price=Decimal("50"), purchase_date=date.today() + timedelta(days=30)),
        Debt(name="Carta", type="Carta di Credito", principal=Decimal("300"), annual_rate=0, balance=Decimal("300")),
        mortgage(start_date=date.today() - timedelta(days=40)),
    ])
    db.session.commit()
    settings_store.set(wealth.OPENING_CASH_SETTING, "1000")

    sheet = wealth.balance_sheet()
    # cash: 1000 opening + 6800 income − 1400 expenses (the 500 transfer moves money between own accounts)
    assert sheet["current_assets"] == {"Liquidità": 6400.0, "Conti deposito e risparmio": 5000.0}
    assert sheet["other_assets"] == {"Portafoglio investimenti": 1200.0, "Immobili": 200000.0}  # the future purchase is excluded
    assert sheet["current_liabilities"] == {"Carte di credito": 300.0}
    assert list(sheet["long_liabilities"]) == ["Mutui"]
    mortgage_left = sheet["long_liabilities"]["Mutui"]
    assert 149000 < mortgage_left < 150000
    assert sheet["net_worth"] == pytest.approx(6400 + 5000 + 1200 + 200000 - 300 - mortgage_left)

    from app.services import analytics
    kpis = analytics.dashboard_kpis()
    assert kpis["net_worth"] == sheet["net_worth"]
    assert kpis["total_investments"] == 1200
    assert kpis["total_debt"] == pytest.approx(300 + mortgage_left)


def test_balance_sheet_in_the_past_ignores_later_transactions(db, sample_data):
    sheet = wealth.balance_sheet(date(2026, 5, 31))
    assert sheet["cash"] == 1000 + 2800 - 600  # December bonus + May


# ── Pages ──────────────────────────────────────────────────────────────────────

PAGES = ["/portfolio/", "/portfolio/new", "/portfolio/prices", "/debt/", "/debt/new", "/insurance/", "/insurance/new",
         "/lifestyle/goals", "/lifestyle/goals/new", "/documents/", "/snapshots/", "/snapshots/compare",
         "/accounting/", "/accounting/balance-sheet", "/dashboard"]


@pytest.mark.parametrize("url", PAGES)
def test_pages_render_empty(client, instance, url):
    response = client.get(url)
    assert response.status_code == 200
    assert_divs_balanced(response.get_data(as_text=True))


@pytest.fixture()
def full_data(db, sample_data, instance):
    tx = make_tx(date=date(2026, 6, 5), description="Assicurazione auto", amount=400, category="Assicurazioni")
    db.session.add_all([
        tx,
        Holding(name="VWCE", ticker="VWCE", asset_class="ETF", quantity=Decimal("10.5"), avg_price=Decimal("100"),
                current_price=Decimal("120"), price_date=date.today()),
        mortgage(),
        InsurancePolicy(type="Auto", company="Generali", premium=Decimal("50"), frequency="monthly",
                        expiry_date=date.today() + timedelta(days=20)),
        Goal(name="Vacanza", target_amount=Decimal("3000"), saved_amount=Decimal("1000"),
             target_date=date.today() + timedelta(days=300)),
    ])
    db.session.commit()
    stored = "a" * 32 + ".pdf"
    (instance / "documents").mkdir(exist_ok=True)
    (instance / "documents" / stored).write_bytes(b"%PDF-1.4 test")
    db.session.add(Document(filename="polizza.pdf", stored_name=stored, mimetype="application/pdf", size=13,
                            doc_type="Polizza", fiscal_year=2026, transaction_id=tx.id))
    db.session.commit()
    wealth.take_snapshot("Inizio")
    return tx


@pytest.mark.parametrize("url", PAGES + ["/debt/1", "/debt/1/edit", "/portfolio/1/edit", "/insurance/1/edit",
                                         "/lifestyle/goals/1/edit", "/documents/1/edit", "/snapshots/compare?a=1",
                                         "/accounting/balance-sheet?date=2026-05-31"])
def test_pages_render_with_data(client, full_data, url):
    response = client.get(url)
    assert response.status_code == 200
    assert_divs_balanced(response.get_data(as_text=True))


def test_portfolio_crud_and_validation(client, db, instance):
    response = client.post("/portfolio/new", data={"name": "BTC", "asset_class": "Criptovaluta", "quantity": "0,5",
                                                   "avg_price": "30.000", "current_price": "60000"})
    assert response.status_code == 302
    holding = Holding.query.one()
    assert holding.quantity == Decimal("0.5") and holding.avg_price == 30000 and holding.price_date == date.today()
    html = client.get("/portfolio/").get_data(as_text=True)
    assert "€ 30.000,00" in html and "+€ 15.000,00" in html

    # a wrong number keeps what was typed and says what is wrong
    response = client.post("/portfolio/new", data={"name": "X", "asset_class": "ETF", "quantity": "tanti", "avg_price": "1"})
    html = response.get_data(as_text=True)
    assert "Quantità: «tanti» non è un numero valido." in html and 'value="X"' in html
    response = client.post("/portfolio/new", data={"name": "X", "asset_class": "Oro", "quantity": "1", "avg_price": "1"})
    assert "Classe: scelta non valida." in response.get_data(as_text=True)
    assert Holding.query.count() == 1

    client.post("/portfolio/prices", data={f"price-{holding.id}": "70000"})
    assert Holding.query.one().current_price == 70000
    client.post(f"/portfolio/{holding.id}/delete")
    assert Holding.query.count() == 0


def test_portfolio_filter_by_class(client, full_data):
    assert "VWCE" in client.get("/portfolio/?asset_class=ETF").get_data(as_text=True)
    assert "Nessuna posizione nella classe" in client.get("/portfolio/?asset_class=Immobile").get_data(as_text=True)


def test_debt_crud_and_plan(client, db, instance):
    response = client.post("/debt/new", data={"name": "Auto", "type": "Prestito Auto", "principal": "12000",
                                              "annual_rate": "0", "term_months": "24", "start_date": "2026-01-10"})
    debt = Debt.query.one()
    assert response.headers["Location"].endswith(f"/debt/{debt.id}")
    html = client.get(f"/debt/{debt.id}").get_data(as_text=True)
    assert "€ 500,00" in html and "10/01/2028" in html
    response = client.post(f"/debt/{debt.id}/edit", data={"name": "Auto", "type": "Prestito Auto", "principal": "12000",
                                                          "annual_rate": "150", "term_months": "24"})
    assert "Tasso annuo: al massimo 100%." in response.get_data(as_text=True)
    assert db.session.get(Debt, debt.id).annual_rate == 0
    client.post(f"/debt/{debt.id}/delete")
    assert Debt.query.count() == 0


def test_insurance_crud_and_reminder(client, db, instance):
    soon = (date.today() + timedelta(days=10)).isoformat()
    client.post("/insurance/new", data={"type": "Casa", "company": "Allianz", "frequency": "quarterly",
                                        "premium": "100", "expiry_date": soon})
    policy = InsurancePolicy.query.one()
    assert policy.annual_premium == 400
    html = client.get("/insurance/").get_data(as_text=True)
    assert "In scadenza" in html and "scade entro 60 giorni" in html and "€ 400,00" in html
    response = client.post(f"/insurance/{policy.id}/edit", data={"type": "Casa", "company": "Allianz", "frequency": "annual",
                                                                 "premium": "100", "start_date": "2027-01-01",
                                                                 "expiry_date": "2026-01-01"})
    assert "La scadenza non può essere prima" in response.get_data(as_text=True)
    client.post(f"/insurance/{policy.id}/delete")
    assert InsurancePolicy.query.count() == 0


def test_goal_contributions(client, db, instance):
    client.post("/lifestyle/goals/new", data={"name": "Vacanza", "target_amount": "1000", "saved_amount": "900"})
    goal = Goal.query.one()
    assert goal.progress == 90
    response = client.post(f"/lifestyle/goals/{goal.id}/contribute", data={"amount": "150"}, follow_redirects=True)
    assert "raggiunto" in response.get_data(as_text=True)
    assert db.session.get(Goal, goal.id).completed
    client.post(f"/lifestyle/goals/{goal.id}/contribute", data={"amount": "-2000"})
    assert db.session.get(Goal, goal.id).saved_amount == 0  # never below zero


def test_goal_monthly_needed():
    goal = Goal(name="X", target_amount=Decimal("1200"), saved_amount=Decimal("0"), target_date=date(2027, 1, 15))
    assert goal.monthly_needed(date(2026, 1, 1)) == 100
    goal.target_date = None
    assert goal.monthly_needed(date(2026, 1, 1)) is None


def test_goal_suggestion_prefills_the_form(client, instance):
    html = client.get("/lifestyle/goals/new?name=Vacanza&target_amount=3000").get_data(as_text=True)
    assert 'value="Vacanza"' in html and 'value="3000"' in html


def test_documents_upload_open_link_and_delete(client, db, sample_data, instance):
    response = client.post("/documents/upload", data={
        "files": [(io.BytesIO(b"%PDF-1.4 a"), "fattura.pdf"), (io.BytesIO(b"<script>x</script>"), "pagina.html")],
        "doc_type": "Fattura", "fiscal_year": "2026", "category": "Casa",
    }, content_type="multipart/form-data")
    assert response.status_code == 302
    pdf, html_doc = Document.query.order_by(Document.id).all()
    assert pdf.fiscal_year == 2026 and pdf.doc_type == "Fattura" and pdf.size == 10
    assert (instance / "documents" / pdf.stored_name).read_bytes() == b"%PDF-1.4 a"

    opened = client.get(f"/documents/{pdf.id}/file")
    assert opened.data == b"%PDF-1.4 a" and opened.headers["Content-Disposition"].startswith("inline")
    html_file = client.get(f"/documents/{html_doc.id}/file")  # never shown as a page: downloaded
    assert html_file.headers["Content-Disposition"].startswith("attachment")
    assert html_file.headers["X-Content-Type-Options"] == "nosniff"

    tx = make_tx(description="Idraulico", amount=90)
    db.session.add(tx)
    db.session.commit()
    client.post(f"/documents/{pdf.id}/edit", data={"filename": "fattura idraulico.pdf", "fiscal_year": "2026",
                                                  "transaction_id": str(tx.id)})
    assert db.session.get(Document, pdf.id).transaction_id == tx.id
    assert "Idraulico" in client.get("/documents/?q=idraulico").get_data(as_text=True)

    client.post(f"/documents/{pdf.id}/delete")
    assert not (instance / "documents" / pdf.stored_name).exists()


def test_deleting_a_transaction_unlinks_its_documents(client, db, full_data):
    client.post(f"/transactions/{full_data.id}/delete")
    db.session.expire_all()
    assert Document.query.one().transaction_id is None


def test_snapshots_create_compare_delete(client, db, sample_data, instance):
    client.post("/snapshots/create", data={"label": "Giugno"})
    db.session.add(Holding(name="ETF", asset_class="ETF", quantity=1, avg_price=Decimal("1000")))
    db.session.commit()
    client.post("/snapshots/create")
    first, second = Snapshot.query.order_by(Snapshot.id).all()
    assert float(second.net_worth) - float(first.net_worth) == 1000
    assert second.detail["holdings"][0]["name"] == "ETF"
    html = client.get(f"/snapshots/compare?a={first.id}&b={second.id}").get_data(as_text=True)
    assert "Portafoglio investimenti" in html and "+€ 1.000,00" in html
    client.post(f"/snapshots/{first.id}/delete")
    assert Snapshot.query.count() == 1


def test_opening_cash(client, db, sample_data, instance):
    client.post("/accounting/balance-sheet/opening", data={"opening_cash": "2.500,50"})
    assert wealth.opening_cash() == 2500.50
    html = client.get("/accounting/balance-sheet").get_data(as_text=True)
    assert "€ 7.900,50" in html  # 2500,50 + 6800 − 1400
    client.post("/accounting/balance-sheet/opening", data={"opening_cash": "boh"})
    assert wealth.opening_cash() == 2500.50


def test_numbers_survive_an_edit_round_trip(client, db, instance):
    """The form shows stored numbers with a decimal comma, so saving again never changes them."""
    client.post("/portfolio/new", data={"name": "Azione", "asset_class": "Azione", "quantity": "1.500",
                                        "avg_price": "1,234"})
    holding = Holding.query.one()
    assert holding.quantity == 1500 and holding.avg_price == Decimal("1.234")
    html = client.get(f"/portfolio/{holding.id}/edit").get_data(as_text=True)
    assert 'value="1500"' in html and 'value="1,234"' in html
    client.post(f"/portfolio/{holding.id}/edit", data={"name": "Azione", "asset_class": "Azione",
                                                       "quantity": "1500", "avg_price": "1,234"})
    db.session.expire_all()
    assert Holding.query.one().avg_price == Decimal("1.234")
