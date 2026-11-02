"""F23: the year in review — numbers, page, PDF, and the PDF of a group of archives."""
import io
from datetime import date
from decimal import Decimal

import pdfplumber
import pytest

from app.extensions import db as _db
from app.models.account import Account
from app.models.client import ClientGroup
from app.models.event import SpendingEvent
from app.models.gig import Gig
from app.models.wealth import Debt, Goal
from app.services import annual_review, gigs
from tests.conftest import make_tx
from tests.test_groups import family, office  # noqa: F401 - fixtures

TODAY = date(2026, 3, 1)


def _text(raw: bytes) -> str:
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


@pytest.fixture()
def year(db):
    db.session.add_all([
        Account(name="Banca", opening_balance=1000),
        make_tx(date=date(2024, 5, 1), description="Stipendio", amount=2000, type="income", category="Stipendio"),
        make_tx(date=date(2024, 6, 1), description="Spesa", amount=500, category="Spesa"),
        make_tx(date=date(2025, 3, 1), description="Stipendio", amount=3000, type="income", category="Stipendio"),
        make_tx(date=date(2025, 4, 1), description="Supermercato", amount=800, category="Spesa"),
        make_tx(date=date(2025, 8, 1), description="Condominio", amount=400, category="Casa"),
        Goal(name="Vacanze", target_amount=2000, saved_amount=2000),
        SpendingEvent(name="Viaggio a Lisbona", start=date(2025, 8, 1), end=date(2025, 8, 10), budget=Decimal(1000)),
    ])
    db.session.commit()
    gigs.save(Gig(), client="Studio Bianchi", description="Sito", owner=None, on=date(2025, 5, 1), hours=None,
              gross=Decimal(500), withholding_agent=True, expenses=None, method="transfer", notes=None)
    db.session.commit()


def test_review_numbers(app, db, year):
    with app.test_request_context():
        data = annual_review.review(2025, TODAY)
    worth = data["net_worth"]
    assert data["complete"] and data["until"] == date(2025, 12, 31)
    assert worth["start"] == 2500 and worth["end"] == 4300 and worth["change"] == 1800 and worth["pct"] == 72.0
    assert ("Liquidità", 2500.0, 4300.0) in worth["lines"] and worth["liabilities"] == (0, 0)
    assert data["summary"]["income"] == 3000 and data["summary"]["expenses"] == 1200 and data["summary"]["savings_rate"] == 60.0
    assert data["changes"] == {"income": 50.0, "expenses": 140.0, "net": 20.0}
    assert [(c["category"], c["before"], c["change"]) for c in data["categories"]] == [("Spesa", 500, 60.0), ("Casa", None, None)]
    assert data["growth"]["savings"] == 1800 and data["growth"]["change"] == 1800 and data["growth"]["other"] == 0
    assert data["gigs"] == {"gross": 500, "withheld": 100}
    assert [e["name"] for e in data["events"]] == ["Viaggio a Lisbona"] and data["goals"][0]["completed"]
    assert data["debts"] == [] and data["repaid"] == 0 and data["limits"] == []
    with app.test_request_context():
        empty = annual_review.review(2023, TODAY)
    assert empty["gigs"] is None and empty["categories"] == [] and empty["changes"]["income"] is None


def test_current_year_and_debts(app, db):
    _db.session.add(Debt(name="Prestito", type="Prestito Auto", principal=Decimal(1200), annual_rate=0, term_months=12,
                         start_date=date(2025, 6, 1)))
    _db.session.commit()
    with app.test_request_context():
        data = annual_review.review(2026, TODAY)
    assert not data["complete"] and data["until"] == TODAY
    debt = data["debts"][0]
    assert debt["name"] == "Prestito" and debt["repaid"] == round(debt["before"] - debt["after"], 2) > 0
    assert data["repaid"] == debt["repaid"] and data["net_worth"]["liabilities"][1] == debt["after"]


def test_pdf_and_pages(app, client, db, year):
    with app.test_request_context():
        raw = annual_review.build_pdf(annual_review.review(2025, TODAY))
    text = _text(raw)
    assert raw.startswith(b"%PDF") and "Bilancio dell'anno 2025" in text and "Spesa" in text
    assert "Viaggio a Lisbona" in text and "Vacanze" in text and "Ritenute d'acconto subite" in text
    page = client.get("/reports/year?year=2025").get_data(as_text=True)
    assert "Da dove viene la variazione" in page and "Viaggio a Lisbona" in page and "Bilancio dell’anno" in page
    assert "fino a oggi" not in page
    response = client.get("/reports/year.pdf?year=2025")
    assert response.mimetype == "application/pdf" and "bilancio_2025.pdf" in response.headers["Content-Disposition"]
    assert "Bilancio dell’anno" in client.get("/reports/summary").get_data(as_text=True)


def test_group_pdf(office, family, client):  # noqa: F811 - fixtures from test_groups
    year = date.today().year
    with office.test_request_context():
        group = _db.session.get(ClientGroup, family["group"])
        text = _text(annual_review.build_group_pdf(group, year))
    assert f"Bilancio dell'anno {year} · Famiglia Rossi" in text and "Per archivio" in text
    assert "Giulia Rossi" in text and "Archivio principale" in text
    response = client.get(f"/reports/year/group/{family['group']}.pdf")
    assert response.mimetype == "application/pdf" and "famiglia_rossi" in response.headers["Content-Disposition"]
    assert "Famiglia Rossi" in client.get("/reports/year").get_data(as_text=True)
    assert client.get("/reports/year/group/999.pdf").status_code == 404
