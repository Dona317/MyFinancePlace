"""Routes and helpers no other test reaches: home redirect, deletes, rules apply, ECB download, the REST API."""
import io
from datetime import date
from decimal import Decimal

from app.models.category import CategoryRule
from app.models.currency import ExchangeRate
from app.models.setting import AppSetting
from app.models.transaction import Transaction
from app.models.user import User
from app.models.wealth import Document, Goal
from tests.conftest import make_tx
from tests.test_currency import ECB_XML


def test_home_goes_to_the_dashboard(client, db):
    assert client.get("/").headers["Location"].endswith("/dashboard")


def test_goal_delete(client, db):
    goal = Goal(name="Viaggio", target_amount=Decimal("1000"), saved_amount=0)
    db.session.add(goal)
    db.session.commit()
    response = client.post(f"/lifestyle/goals/{goal.id}/delete", follow_redirects=True)
    assert "Obiettivo «Viaggio» eliminato." in response.get_data(as_text=True)
    assert Goal.query.count() == 0
    assert client.post("/lifestyle/goals/999/delete").status_code == 404


def test_rules_delete_and_apply(client, db):
    rule = CategoryRule(keyword="esselunga", category="Alimentari")
    db.session.add_all([rule, make_tx(description="ESSELUNGA spa", category="Altro"),
                        make_tx(description="Esselunga", category="Svago")])
    db.session.commit()
    client.post("/settings/rules/apply")  # only the uncategorized ones
    assert sorted(t.category for t in Transaction.query.all()) == ["Alimentari", "Svago"]
    client.post("/settings/rules/apply", data={"all": "1"})
    assert {t.category for t in Transaction.query.all()} == {"Alimentari"}
    response = client.post(f"/settings/rules/{rule.id}/delete", follow_redirects=True)
    assert "Regola «esselunga» eliminata." in response.get_data(as_text=True) and CategoryRule.query.count() == 0


def test_ecb_download(client, db, monkeypatch):
    db.session.add(make_tx(date=date(2026, 6, 2), amount=125, currency="USD"))
    db.session.commit()
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: io.BytesIO(ECB_XML))
    response = client.post("/settings/currencies/ecb", follow_redirects=True)
    assert "Scaricati 2 cambi" in response.get_data(as_text=True)
    assert {r.currency for r in ExchangeRate.query.all()} == {"USD", "GBP"}
    assert Transaction.query.one().amount_base == Decimal("100.00")  # recomputed: 125 USD at 1.25

    def offline(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr("urllib.request.urlopen", offline)
    assert "Non riesco a scaricare" in client.post("/settings/currencies/ecb", follow_redirects=True).get_data(as_text=True)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: io.BytesIO(b"<Envelope/>"))
    assert "nessun cambio" in client.post("/settings/currencies/ecb", follow_redirects=True).get_data(as_text=True)


def test_rest_api_update_and_delete(client, db):
    created = client.post("/transactions/api", json={"date": "2026-06-01", "description": "Caffè", "amount": 1.5,
                                                     "type": "expense", "category": "Ristoranti"})
    assert created.status_code == 201
    tx_id = created.get_json()["id"]
    body = {"date": "2026-06-02", "description": "Colazione", "amount": 4, "type": "expense", "category": "Ristoranti"}
    updated = client.put(f"/transactions/api/{tx_id}", json=body)
    assert updated.status_code == 200 and updated.get_json()["description"] == "Colazione"
    assert db.session.get(Transaction, tx_id).amount == Decimal("4.00")
    assert client.put("/transactions/api/999", json=body).status_code == 404
    assert client.delete(f"/transactions/api/{tx_id}").get_json() == {"success": True, "deleted_id": tx_id}
    assert Transaction.query.count() == 0 and client.delete(f"/transactions/api/{tx_id}").status_code == 404


def test_model_helpers(db):
    assert repr(AppSetting(key="k", value="v")) == "<AppSetting k='v'>"
    assert repr(Transaction(id=3, description="Coop")) == "<Transaction 3 Coop>"
    assert repr(User(username="anna")) == "<User anna>"
    assert Document(filename="scontrino.jpg", mimetype="image/jpeg").is_image
    assert not Document(filename="a.pdf", mimetype="application/pdf").is_image
