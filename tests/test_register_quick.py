"""The register's quick edit, the edit pop-up's last step, the review page, the dashboard layout reset and the
report as PDF."""
from app.models.account import Account
from app.models.transaction import Transaction
from app.services import dashboard_prefs
from tests.conftest import make_tx


def add(db, **values):
    tx = make_tx(**values)
    db.session.add(tx)
    db.session.commit()
    return tx


def test_quick_edit_changes_the_row_in_place(client, db):
    tx = add(db, description="Pieno", amount=-60, category="Trasporto", tags=["auto"])
    response = client.post(f"/transactions/{tx.id}/quick", data={
        "date": "2026-10-15", "description": "Pieno Eni", "amount": "65,50", "type": "expense",
        "category": "Benzina e petroli", "tags": "auto, viaggio"})
    assert response.status_code == 200 and response.get_json() == {"ok": True}
    saved = db.session.get(Transaction, tx.id)
    assert (saved.description, saved.category, saved.tags) == ("Pieno Eni", "Benzina e petroli", ["auto", "viaggio"])
    assert saved.type == "expense" and abs(float(saved.amount)) == 65.5


def test_quick_edit_refuses_a_wrong_amount(client, db):
    tx = add(db, description="Pieno", amount=-60)
    response = client.post(f"/transactions/{tx.id}/quick", data={"date": "2026-10-15", "description": "Pieno",
                                                                 "amount": "abc"})
    assert response.status_code == 400 and "error" in response.get_json()


def test_the_pop_up_closes_itself_after_saving(client, db):
    assert "tx-done" in client.get("/transactions/embed-done").get_data(as_text=True)


def test_the_review_page_opens(client, db):
    add(db, description="Stipendio ottobre", amount=-2000, category="Stipendio")
    assert client.get("/transactions/review").status_code == 200


def test_the_dashboard_layout_goes_back_to_the_default(client, db):
    response = client.post("/dashboard/layout", json={"reset": True})
    assert response.get_json()["layout"] == dashboard_prefs.default_layout()


def test_the_report_downloads_as_pdf(client, db):
    account = Account(name="Fineco", kind="current", currency="EUR")
    db.session.add(account)
    db.session.commit()
    add(db, description="Spesa", amount=-40, category="Alimentari", account_id=account.id)
    for query in (f"?account={account.id}", "?account=none&tab=spending"):
        response = client.get("/reports/report.pdf" + query)
        assert response.status_code == 200 and response.data.startswith(b"%PDF")
