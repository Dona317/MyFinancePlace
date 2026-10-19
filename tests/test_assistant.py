"""F20k: the assistant answers from a summary of the archive, read only, with links to the pages."""
import json
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.wealth import Goal, Holding
from app.services import ai_extraction, assistant
from app.services.ai_extraction import AIExtractionError
from tests.conftest import make_tx


@pytest.fixture()
def archive(db):
    db.session.add_all([Account(name="Corrente", kind="current", opening_balance=Decimal("5000")),
                        Holding(name="ETF", asset_class="ETF", quantity=10, avg_price=100, current_price=110),
                        Goal(name="Vacanza", target_amount=Decimal("3000"), saved_amount=Decimal("500")),
                        make_tx(description="Pizzeria", amount=Decimal("40"), category="Ristoranti", date=date(2026, 9, 5))])
    db.session.commit()


@pytest.fixture()
def model(monkeypatch):
    seen = {}

    def fake(model_name, system, prompt, schema, images=None):
        seen.update(system=system, prompt=prompt, schema=schema)
        return json.dumps(seen.get("reply") or {"answer": "Hai speso 40,00 € in ristoranti.", "links": ["reports", "nope", "reports"]})

    monkeypatch.setattr(ai_extraction, "provider", lambda: "ollama")
    monkeypatch.setattr(ai_extraction, "ollama_json", fake)
    return seen


def test_facts(app, archive):
    with app.test_request_context():
        facts = assistant.facts(date(2026, 10, 13))
    assert facts["patrimonio"]["investimenti"] == 1100 and facts["conti"][0]["saldo"] == 5000
    assert facts["spese_per_categoria_ultimi_3_mesi"]["2026-09"] == {"Ristoranti": 40.0}
    assert facts["obiettivi"][0]["risparmiato"] == 500 and "Pizzeria" not in json.dumps(facts)  # no single movement


def test_ask(app, archive, model):
    with app.test_request_context():
        answer = assistant.ask("  Quanto ho speso   in ristoranti? ", date(2026, 10, 13))
    assert answer.question == "Quanto ho speso in ristoranti?" and answer.text.startswith("Hai speso")
    assert answer.links == [("Report", "/reports/")]  # unknown pages dropped, each once
    assert "Ristoranti" in model["prompt"] and "SOLO i dati" in model["system"]
    model["reply"] = {"answer": "", "links": []}
    with app.test_request_context(), pytest.raises(AIExtractionError, match="leggibile"):
        assistant.ask("x")
    model["reply"] = "non json"
    with app.test_request_context(), pytest.raises(AIExtractionError):
        assistant.ask("x")
    with app.test_request_context(), pytest.raises(AIExtractionError, match="Scrivi"):
        assistant.ask("   ")


def test_anthropic_and_no_model(app, archive, monkeypatch):
    calls = []
    monkeypatch.setattr(ai_extraction, "provider", lambda: "anthropic")
    monkeypatch.setattr(ai_extraction, "anthropic_json",
                        lambda *args, **kw: calls.append(kw) or json.dumps({"answer": "Ok", "links": []}))
    with app.test_request_context():
        assert assistant.leaves_computer() and assistant.ask("Saldo?").text == "Ok"
    assert calls[0]["max_tokens"] == 4000
    monkeypatch.setattr(ai_extraction, "provider", lambda: None)
    with app.test_request_context(), pytest.raises(AIExtractionError, match="Nessun modello"):
        assistant.ask("Saldo?")


def test_page(client, db, archive, model):
    page = client.get("/assistant/").get_data(as_text=True)
    assert "Fai una domanda" in page and "nulla esce" in page
    page = client.post("/assistant/", data={"question": "Ristoranti?"}).get_data(as_text=True)
    assert "Hai speso 40,00 €" in page and 'href="/reports/"' in page
    page = client.post("/assistant/", data={"question": ""}).get_data(as_text=True)
    assert "Scrivi una domanda." in page


def test_page_without_model(client, db, monkeypatch):
    monkeypatch.setattr(ai_extraction, "provider", lambda: None)
    assert "Nessun modello AI configurato." in client.get("/assistant/").get_data(as_text=True)
