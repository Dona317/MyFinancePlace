"""
AI quick classification (category + counterparty from the bank's causale) and the causale on record.

The model is faked: Ollama at the HTTP level (it reads the movements from the prompt and answers with
simple keyword rules), Claude at the SDK client.
"""
import io
import json
import re
from datetime import date
from types import SimpleNamespace

import pytest

from app.extensions import db as _db
from app.models.transaction import Transaction
from app.services import ai_classification, ai_extraction, settings_store
from tests.conftest import make_tx
from tests.form_helper import form_data
from tests.statements import fineco_xlsx

RULES = [("esselunga", "Alimentari", "Esselunga"), ("netflix", "Abbonamenti", "Netflix"),
         ("stipendio", "Stipendio", "ACME SPA"), ("palestra", "Sport", "Palestra FIT")]


def fake_answer(movements, categories):
    items = []
    for m in movements:
        text = m["causale"].lower()
        hit = next((r for r in RULES if r[0] in text and r[1] in categories), None)
        items.append({"id": m["id"], "category": hit[1] if hit else "Altro",
                      "counterparty": hit[2] if hit else "", "confidence": "alta" if hit else "bassa"})
    return {"items": items}


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def ollama(app, monkeypatch):
    app.config.update(LLM_PROVIDER="ollama", LLM_MODEL="", OLLAMA_URL="http://ollama.test:11434")
    state = SimpleNamespace(calls=[], override=None)

    def urlopen(request, timeout=None):
        body = json.loads(request.data)
        state.calls.append(body)
        prompt = body["messages"][1]["content"]
        movements = json.loads(prompt.split("movimenti:\n", 1)[1])
        categories = body["format"]["properties"]["items"]["items"]["properties"]["category"]["enum"]
        reply = state.override(movements) if state.override else fake_answer(movements, categories)
        return _Response(json.dumps({"message": {"content": json.dumps(reply)}}).encode())

    monkeypatch.setattr(ai_extraction.urllib.request, "urlopen", urlopen)
    return state


def items(*texts):
    return [{"id": i + 1, "text": t, "amount": -10.0} for i, t in enumerate(texts)]


# ── Service ────────────────────────────────────────────────────────────────────

def test_classify_suggests_category_and_counterparty(ollama):
    result = ai_classification.classify(
        items("Pagamento Visa Debit presso ESSELUNGA MILANO", "NETFLIX.COM AMSTERDAM", "XYZ 123"),
        ["Alimentari", "Abbonamenti", "Casa"],
    )
    assert result[1].to_dict() == {"category": "Alimentari", "counterparty": "Esselunga", "confidence": "alta"}
    assert result[2].category == "Abbonamenti"
    assert result[3].to_dict() == {"category": "Altro", "counterparty": "", "confidence": "bassa"}


def test_request_constrains_categories_and_sends_the_causale(ollama):
    ai_classification.classify(items("PALESTRA FIT MILANO"), ["Sport", "Casa"])
    body = ollama.calls[0]
    enum = body["format"]["properties"]["items"]["items"]["properties"]["category"]["enum"]
    assert enum == ["Sport", "Casa", "Altro"]  # the user's categories, plus a fallback
    assert "PALESTRA FIT MILANO" in body["messages"][1]["content"]
    assert "Casa: affitto" in body["messages"][1]["content"]  # hints for known categories
    assert body["model"] == "qwen2.5vl:7b"  # no classification model set: the reading model


def test_large_sets_are_sent_in_batches(ollama):
    result = ai_classification.classify(items(*["ESSELUNGA"] * 95), ["Alimentari"])
    assert [len(json.loads(c["messages"][1]["content"].split("movimenti:\n", 1)[1])) for c in ollama.calls] == [40, 40, 15]
    assert len(result) == 95


def test_invalid_model_output_is_filtered(ollama):
    ollama.override = lambda movements: {"items": [
        {"id": 1, "category": "Alimentari", "counterparty": "  Esselunga   Milano ", "confidence": "altissima"},
        {"id": 1, "category": "Casa", "counterparty": "", "confidence": "alta"},            # duplicate id
        {"id": 2, "category": "Categoria inventata", "counterparty": "", "confidence": "alta"},
        {"id": 99, "category": "Casa", "counterparty": "", "confidence": "alta"},           # not asked
    ]}
    result = ai_classification.classify(items("ESSELUNGA", "NETFLIX"), ["Alimentari", "Casa"])
    assert list(result) == [1]
    assert result[1].to_dict() == {"category": "Alimentari", "counterparty": "Esselunga Milano", "confidence": "bassa"}


def test_empty_causali_are_not_sent(ollama):
    assert ai_classification.classify(items("", "   "), ["Casa"]) == {}
    assert ollama.calls == []


def test_classification_needs_a_provider(app):
    with pytest.raises(ai_extraction.AIExtractionError, match="Modelli AI"):
        ai_classification.classify(items("ESSELUNGA"), ["Alimentari"])


def test_separate_classification_model(client, ollama):
    client.post("/settings/ai/save", data={"provider": "ollama", "model": "qwen2.5vl:7b", "classify_model": "qwen3:1.7b"})
    ai_classification.classify(items("ESSELUNGA"), ["Alimentari"])
    assert ollama.calls[-1]["model"] == "qwen3:1.7b"
    assert ai_extraction.model_name() == "qwen2.5vl:7b"  # reading scans still uses the vision model
    client.post("/settings/ai/save", data={"provider": "ollama", "model": "", "classify_model": ""})
    assert ai_classification.model_name() == "qwen2.5vl:7b"  # empty = same model as reading


def test_claude_classification_request(app, monkeypatch):
    import anthropic
    app.config.update(LLM_PROVIDER="anthropic", LLM_MODEL="")
    settings_store.set(ai_classification.classify_setting("anthropic"), "claude-haiku-4-5")
    requests = []

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_final_message(self):
            movements = json.loads(requests[-1]["messages"][0]["content"][0]["text"].split("movimenti:\n", 1)[1])
            reply = fake_answer(movements, ["Alimentari", "Altro"])
            return SimpleNamespace(stop_reason="end_turn", model="claude-haiku-4-5",
                                   content=[SimpleNamespace(type="text", text=json.dumps(reply))])

    class Client:
        def __init__(self, **kwargs):
            self.beta = SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: requests.append(kw) or Stream()))

    monkeypatch.setattr(anthropic, "Anthropic", Client)
    result = ai_classification.classify(items("ESSELUNGA"), ["Alimentari"])
    request = requests[0]
    assert request["model"] == "claude-haiku-4-5" and request["max_tokens"] == 16000
    assert request["output_config"]["format"]["schema"] == ai_classification.response_schema(["Alimentari", "Altro"])
    assert "fallbacks" not in request
    assert result[1].category == "Alimentari"


# ── Import preview ─────────────────────────────────────────────────────────────

def _preview(client):
    return client.post("/export/bank", data={"file": (io.BytesIO(fineco_xlsx()), "movimenti.xlsx")},
                       content_type="multipart/form-data").get_data(as_text=True)


def test_preview_classify_endpoint(client, ollama, db):
    html = _preview(client)
    assert 'id="ai-classify"' in html
    causale = re.search(r'data-index="0" data-causale="([^"]*)"', html).group(1)
    assert "ESSELUNGA" in causale and "Pagamento Visa Debit" in causale
    response = client.post("/export/bank/classify", json={"rows": [
        {"index": 0, "text": causale, "amount": -87.5},
        {"index": 4, "text": "PALESTRA FIT", "amount": -12},
    ]})
    assert response.status_code == 200
    data = response.get_json()
    assert data["model"] == "qwen2.5vl:7b"
    assert data["suggestions"]["0"] == {"category": "Alimentari", "counterparty": "Esselunga", "confidence": "alta"}
    assert data["suggestions"]["4"]["category"] == "Altro"  # "Sport" is not one of the categories yet


def test_preview_classify_without_ai(client, db):
    assert 'Attiva la classificazione AI' in _preview(client)
    response = client.post("/export/bank/classify", json={"rows": [{"index": 0, "text": "ESSELUNGA", "amount": -1}]})
    assert response.status_code == 400 and "Modelli AI" in response.get_json()["error"]


@pytest.mark.parametrize("payload", [{}, {"rows": []}, {"rows": [{"text": "no index"}]}, {"rows": "x"},
                                     [1, 2], {"rows": ["x", 3, None]}, {"rows": [{"index": "a", "text": "t"}]}])
def test_preview_classify_bad_requests(client, ollama, payload):
    assert client.post("/export/bank/classify", json=payload).status_code == 400


def test_saved_rows_keep_counterparty_ai_tag_and_bank_causale(client, ollama, db):
    html = _preview(client)
    # the user accepted the AI category on row 0 (aicat) and rewrote its description; row 1 was changed by hand
    client.post("/export/bank/confirm", data=form_data(html, "preview-form", include=["0", "1"], **{
        "description-0": "Spesa settimanale", "counterparty-0": "Esselunga", "aicat-0": "1",
        "category-1": "Svago",
    }))
    first, second = Transaction.query.order_by(Transaction.date, Transaction.id).all()
    assert first.description == "Spesa settimanale"
    assert first.bank_description == "Pagamento Visa Debit presso ESSELUNGA MILANO"  # the bank's text is kept
    assert first.counterparty == "Esselunga" and "categoria-ai" in first.tags
    assert "categoria-ai" not in second.tags and second.bank_description.startswith("NETFLIX.COM")


# ── Saved transactions ─────────────────────────────────────────────────────────

@pytest.fixture()
def saved(db):
    txs = [
        make_tx(date=date(2026, 6, 3), description="Spesa", bank_description="PAGAMENTO POS ESSELUNGA MILANO", category="Altro", amount=80),
        make_tx(date=date(2026, 6, 5), description="NETFLIX.COM", category=None, amount=17.99),
        make_tx(date=date(2026, 6, 7), description="Bonifico XYZ", category="Altro", amount=50),
        make_tx(date=date(2026, 6, 9), description="ESSELUNGA", category="Casa", amount=20),  # already categorized
    ]
    db.session.add_all(txs)
    db.session.commit()
    return txs


def test_list_offers_classification_of_uncategorized(client, ollama, saved):
    page = client.get("/transactions/").get_data(as_text=True)
    assert "Classifica con AI (3 senza categoria)" in page


def test_classify_uncategorized_then_apply(client, ollama, saved):
    page = client.post("/transactions/classify", data={}).get_data(as_text=True)
    assert len(re.findall(r"<div\b", page)) == len(re.findall(r"</div>", page))
    assert "PAGAMENTO POS ESSELUNGA MILANO" in ollama.calls[0]["messages"][1]["content"]  # the causale is used
    assert "Bonifico XYZ" in page and f'name="apply" value="{saved[3].id}"' not in page  # "Casa" is not asked
    data = form_data(page, "classify-form")
    assert sorted(data["apply"]) == sorted([str(saved[0].id), str(saved[1].id)])  # the "bassa" one is not preselected
    client.post("/transactions/classify/apply", data=form_data(page, "classify-form", **{f"category-{saved[1].id}": "Svago"}))

    spesa, netflix, bonifico, casa = (_db.session.get(Transaction, t.id) for t in saved)
    assert (spesa.category, spesa.counterparty) == ("Alimentari", "Esselunga") and "categoria-ai" in spesa.tags
    assert netflix.category == "Svago" and "categoria-ai" not in (netflix.tags or [])  # corrected by the user
    assert bonifico.category == "Altro" and casa.category == "Casa"  # not applied / not asked


def test_classify_selected_only(client, ollama, saved):
    client.post("/transactions/classify", data={"ids": [str(saved[3].id)]})
    sent = ollama.calls[0]["messages"][1]["content"]
    assert "ESSELUNGA" in sent and "NETFLIX" not in sent


def test_classify_error_is_reported(client, app, saved):
    response = client.post("/transactions/classify", data={})
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert "Classificazione AI non riuscita" in session["_flashes"][0][1]


def test_causale_shown_and_never_edited(client, db):
    tx = make_tx(description="Spesa", bank_description="PAGAMENTO POS ESSELUNGA MILANO")
    db.session.add(tx)
    db.session.commit()
    assert "PAGAMENTO POS ESSELUNGA MILANO" in client.get("/transactions/").get_data(as_text=True)
    page = client.get(f"/transactions/{tx.id}/edit").get_data(as_text=True)
    assert "Causale della banca" in page
    client.post(f"/transactions/{tx.id}/edit", data=form_data(page, "edit-form", description="Spesa Esselunga"))
    db.session.refresh(tx)
    assert (tx.description, tx.bank_description) == ("Spesa Esselunga", "PAGAMENTO POS ESSELUNGA MILANO")
    assert "PAGAMENTO POS ESSELUNGA MILANO" in client.get("/export/csv").get_data(as_text=True)


def test_review_never_proposes_a_worse_category(client, ollama, db):
    """A specific category is not replaced by "Altro" or by an unsure suggestion."""
    tx = make_tx(description="Giroconto verso conto deposito", category="Giroconto", type="transfer", amount=200)
    db.session.add(tx)
    db.session.commit()
    page = client.post("/transactions/classify", data={"ids": [str(tx.id)]}).get_data(as_text=True)
    assert f'name="apply" value="{tx.id}" ' in page and f'name="apply" value="{tx.id}" checked' not in page
    assert form_data(page, "classify-form")[f"category-{tx.id}"] == ["Giroconto"]  # kept, even if applied
