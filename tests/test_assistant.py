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


def test_the_panel_asks_with_json(client, db, archive, model):
    assert client.get("/assistant/status").get_json()["available"] is True
    answer = client.post("/assistant/ask", json={"question": "Ristoranti?"}).get_json()
    assert answer["state"] == "done"  # AI_JOBS_SYNC: the background job ran inline
    assert "Hai speso 40,00 €" in answer["text"] and any(url == "/reports/" for _label, url in answer["links"])
    # the page polls the job: the same answer, also from another page; another user's job is not shown
    again = client.get(f"/assistant/job/{answer['id']}").get_json()
    assert again["text"] == answer["text"] and again["question"] == "Ristoranti?"
    assert client.get("/assistant/job/nope").status_code == 404
    response = client.post("/assistant/ask", json={"question": ""})
    assert response.status_code == 400 and response.get_json()["error"] == "Scrivi una domanda."
    page = client.get("/dashboard").get_data(as_text=True)
    assert 'id="ask-bubble"' in page and 'id="ask-panel"' in page and 'href="/assistant/"' not in page  # out of the menu


def test_a_failed_answer_is_an_error_of_the_job(client, db, archive, model, monkeypatch):
    from app.services import assistant as service
    from app.services.ai_extraction import AIExtractionError

    def broken(question):
        raise AIExtractionError("Il modello non risponde.")
    monkeypatch.setattr(service, "ask", broken)
    response = client.post("/assistant/ask", json={"question": "Quanto ho speso?"})
    assert response.status_code == 400 and response.get_json()["error"] == "Il modello non risponde."

    def crash(question):
        raise RuntimeError("boom")
    monkeypatch.setattr(service, "ask", crash)
    response = client.post("/assistant/ask", json={"question": "Quanto ho speso?"})
    assert response.status_code == 400 and "errore imprevisto" in response.get_json()["error"]


def test_old_jobs_are_forgotten(app, db):
    import time

    from app.services import assistant_jobs
    assistant_jobs._jobs["old"] = {"id": "old", "owner": "x", "started_at": time.time() - 7200, "finished_at": None}
    assistant_jobs._forget_old()
    assert "old" not in assistant_jobs._jobs


def test_the_background_thread_answers_in_the_archive_of_who_asked(app, db, monkeypatch):
    import time

    from app.services import assistant as service
    from app.services import assistant_jobs

    class Answer:
        text, links = "Fatto.", [("Report", "/reports/")]
    monkeypatch.setattr(service, "ask", lambda question: Answer())
    assistant_jobs._jobs["t1"] = {"id": "t1", "owner": "u", "question": "?", "state": "running",
                                  "started_at": time.time(), "finished_at": None, "text": None, "links": [], "error": None}
    assistant_jobs._run(app, None, "t1", "?")
    assert assistant_jobs.get("t1", "u")["state"] == "done" and assistant_jobs.get("t1", "other") is None
