"""
AI reading of scans, photos and non-standard statements.

No real model is called: Ollama is faked at the HTTP level (urlopen) and Claude at the SDK client,
so these tests check both what we send to each provider and how we validate what comes back.
"""
import base64
import io
import json
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.transaction import Transaction
from app.services import ai_extraction, bank_import
from tests.form_helper import form_data

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "bank_statements"
SCAN = "SCANSIONE_fineco_2026-07_2026-08.pdf"
PHOTO = "FOTO_estratto_conto_intesa_2026-09.jpg"

sys.path.insert(0, str(SAMPLES))
import generate as sample_generator  # noqa: E402


def truth_movements():
    """What the scanned Fineco statement really contains (the generator's data)."""
    return sample_generator.movements(date(2026, 7, 1), date(2026, 8, 31), 77, salary=2450.0, rent=850.0)


def model_reply(movements, opening=3250.0, closing=None, has_balances=True, bank="FinecoBank"):
    closing = opening + sum(m["amount"] for m in movements) if closing is None else closing
    return {
        "bank_name": bank, "has_balances": has_balances,
        "opening_balance": opening, "closing_balance": round(closing, 2),
        "movements": [
            {"date": m["date"].isoformat(), "description": m["full"], "details": m["short"], "amount": m["amount"]}
            for m in movements
        ],
    }


@pytest.fixture()
def ollama(app, monkeypatch):
    """Enable the Ollama provider and fake its HTTP API; replies are queued per call."""
    app.config.update(LLM_PROVIDER="ollama", LLM_MODEL="", OLLAMA_URL="http://ollama.test:11434")
    calls, replies = [], []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    installed = ["qwen2.5vl:7b", "llama3.2:1b"]

    def fake_urlopen(request, timeout=None):
        if request.full_url.endswith("/api/version"):
            return Response(json.dumps({"version": "0.9.0"}).encode())
        if request.full_url.endswith("/api/tags"):
            return Response(json.dumps({"models": [{"name": n, "size": 3_000_000_000} for n in installed]}).encode())
        calls.append({"url": request.full_url, "body": json.loads(request.data)})
        reply = replies.pop(0) if len(replies) > 1 else replies[0]
        return Response(json.dumps({"message": {"content": json.dumps(reply)}}).encode())

    monkeypatch.setattr(ai_extraction.urllib.request, "urlopen", fake_urlopen)
    return SimpleNamespace(calls=calls, replies=replies, installed=installed)


@pytest.fixture()
def claude(app, monkeypatch):
    """Enable the Anthropic provider with a fake SDK client that records the request."""
    import anthropic

    app.config.update(LLM_PROVIDER="anthropic", LLM_MODEL="")
    state = SimpleNamespace(requests=[], reply=None, stop_reason="end_turn")

    class FakeStream:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_final_message(self):
            content = [SimpleNamespace(type="thinking", thinking=""),
                       SimpleNamespace(type="text", text=json.dumps(state.reply))]
            return SimpleNamespace(stop_reason=state.stop_reason, content=content, model=state.requests[-1]["model"])

    class FakeClient:
        def __init__(self, **kwargs):
            self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

        def _stream(self, **kwargs):
            state.requests.append(kwargs)
            return FakeStream()

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    return state


def read_with_ai(filename, raw, model=None):
    """What happens after the user confirms: the normal reader refuses, then the AI reads."""
    with pytest.raises(bank_import.AIRequired):
        bank_import.analyze_statement(filename, raw)
    return bank_import.analyze_with_ai(filename, raw, model=model)


# ── Never automatic ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("filename, kind", [(SCAN, "scan"), (PHOTO, "photo")])
def test_unreadable_files_require_confirmation_even_with_ai_enabled(ollama, filename, kind):
    with pytest.raises(bank_import.AIRequired) as error:
        bank_import.analyze_statement(filename, (SAMPLES / filename).read_bytes())
    assert error.value.kind == kind and error.value.needs_vision
    assert ollama.calls == []  # nothing was sent to the model


# ── Ollama (local) ─────────────────────────────────────────────────────────────

def test_scanned_pdf_read_page_by_page_with_ollama(ollama):
    movements = truth_movements()
    half = len(movements) // 2
    page1 = model_reply(movements[:half], has_balances=False)
    page2 = model_reply(movements[half:], opening=0, closing=3250.0 + sum(m["amount"] for m in movements))
    page1["has_balances"] = True  # page 1 prints the opening balance, page 2 the closing one
    page1["closing_balance"] = 0
    ollama.replies.extend([page1, page2])

    preview = read_with_ai(SCAN, (SAMPLES / SCAN).read_bytes())

    assert len(ollama.calls) == 2  # one request per page
    body = ollama.calls[0]["body"]
    assert ollama.calls[0]["url"] == "http://ollama.test:11434/api/chat"
    assert body["model"] == "qwen2.5vl:7b" and body["stream"] is False
    assert body["format"] == ai_extraction.MOVEMENTS_SCHEMA
    assert body["options"] == {"temperature": 0, "num_ctx": ai_extraction.OLLAMA_CONTEXT_TOKENS}
    image = base64.b64decode(body["messages"][1]["images"][0])
    assert image[:8] == b"\x89PNG\r\n\x1a\n"

    assert preview.ai_model == "qwen2.5vl:7b"
    assert preview.bank.key == "fineco"  # from the bank name the model read
    assert len(preview.rows) == len(movements)
    assert sorted((r.date, r.amount) for r in preview.rows) == sorted(
        (m["date"], Decimal(f"{m['amount']:.2f}")) for m in movements
    )
    assert preview.balance_check.ok


def test_photo_is_downscaled_and_sent_as_jpeg(ollama):
    ollama.replies.append(model_reply(truth_movements()[:3], has_balances=False, bank=""))
    preview = read_with_ai(PHOTO, (SAMPLES / PHOTO).read_bytes())
    image = base64.b64decode(ollama.calls[0]["body"]["messages"][1]["images"][0])
    assert image[:3] == b"\xff\xd8\xff"
    from PIL import Image
    assert max(Image.open(io.BytesIO(image)).size) <= ai_extraction.MAX_IMAGE_SIDE
    assert preview.bank.key == "intesa"  # the model found no bank name; the file name says Intesa
    assert preview.balance_check is None


def test_balance_mismatch_is_reported(ollama):
    movements = truth_movements()
    reply = model_reply(movements)
    reply["movements"].pop(3)  # the model skipped a row
    ollama.replies.append(reply)
    photo = (SAMPLES / PHOTO).read_bytes()
    preview = read_with_ai("foto.jpg", photo)
    assert not preview.balance_check.ok
    assert preview.balance_check.difference == Decimal(f"{movements[3]['amount']:.2f}")


def test_invalid_rows_from_the_model_are_discarded(ollama):
    reply = model_reply(truth_movements()[:4], has_balances=False)
    reply["movements"][0]["date"] = "31/02/2026"   # impossible date
    reply["movements"][1]["amount"] = 0            # no amount
    reply["movements"][2]["description"] = "  "    # no description
    reply["movements"].append(dict(reply["movements"][3], amount=float("nan")))  # json.loads accepts NaN
    reply["movements"].append(dict(reply["movements"][3], amount=1e20))            # too large for the column
    ollama.replies.append(reply)
    preview = read_with_ai("foto.jpg", (SAMPLES / PHOTO).read_bytes())
    assert len(preview.rows) == 1 and preview.discarded == 5


def test_non_standard_text_document_goes_to_the_model_as_text(ollama):
    text = (
        "Gentile cliente, ecco i suoi movimenti di luglio.\n"
        "Il giorno 3 luglio 2026 ha pagato 45,10 euro da CONAD.\n"
        "Il 27 luglio 2026 ha ricevuto lo stipendio di 2.450,00 euro da ACME SPA.\n"
    )
    ollama.replies.append({
        "bank_name": "", "has_balances": False, "opening_balance": 0, "closing_balance": 0,
        "movements": [
            {"date": "2026-07-03", "description": "CONAD", "details": "", "amount": -45.10},
            {"date": "2026-07-27", "description": "Stipendio ACME SPA", "details": "", "amount": 2450.00},
        ],
    })
    preview = read_with_ai("lettera.txt", text.encode())
    message = ollama.calls[0]["body"]["messages"][1]
    assert "images" not in message and "CONAD" in message["content"]
    assert [(r.description, r.type, r.category) for r in preview.rows] == [
        ("CONAD", "expense", "Alimentari"), ("Stipendio ACME SPA", "income", "Stipendio"),
    ]


def test_long_text_is_refused_not_truncated_for_the_local_model(ollama):
    text = "Movimento senza data riconoscibile\n" * 2000  # ~70k chars, over the local limit
    with pytest.raises(bank_import.StatementImportError, match="troppo lungo"):
        read_with_ai("lungo.txt", text.encode())
    assert ollama.calls == []


def test_ollama_not_running(app, monkeypatch):
    import urllib.error
    app.config.update(LLM_PROVIDER="ollama")

    def refuse(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(ai_extraction.urllib.request, "urlopen", refuse)
    with pytest.raises(bank_import.StatementImportError, match="ollama serve"):
        read_with_ai(PHOTO, (SAMPLES / PHOTO).read_bytes())


def test_model_not_pulled(app, monkeypatch):
    import urllib.error
    app.config.update(LLM_PROVIDER="ollama", LLM_MODEL="llama3.2-vision:11b")

    def not_found(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 404, "not found", {}, io.BytesIO(b""))

    monkeypatch.setattr(ai_extraction.urllib.request, "urlopen", not_found)
    with pytest.raises(bank_import.StatementImportError, match="ollama pull llama3.2-vision:11b"):
        read_with_ai(PHOTO, (SAMPLES / PHOTO).read_bytes())


def test_well_formed_files_never_reach_the_model(ollama):
    """The rule-based reader stays first: AI is only a fallback."""
    name = "intesa_sanpaolo_lista_movimenti_2026-09.pdf"
    preview = bank_import.analyze_statement(name, (SAMPLES / name).read_bytes())
    assert ollama.calls == [] and preview.ai_model is None


# ── Anthropic (Claude) ─────────────────────────────────────────────────────────

def test_claude_receives_the_pdf_and_a_json_schema(claude):
    claude.reply = model_reply(truth_movements())
    preview = read_with_ai(SCAN, (SAMPLES / SCAN).read_bytes())

    request = claude.requests[0]
    assert request["model"] == "claude-opus-5"
    assert request["output_config"] == {"format": {"type": "json_schema", "schema": ai_extraction.MOVEMENTS_SCHEMA}}
    assert request["fallbacks"] == "default" and request["betas"] == ["server-side-fallback-2026-07-01"]
    document = request["messages"][0]["content"][0]
    assert document["type"] == "document" and document["source"]["media_type"] == "application/pdf"
    assert base64.b64decode(document["source"]["data"]) == (SAMPLES / SCAN).read_bytes()
    assert len(preview.rows) == len(truth_movements()) and preview.balance_check.ok


def test_claude_photo_and_cheaper_model(claude, app):
    app.config["LLM_MODEL"] = "claude-haiku-4-5"
    claude.reply = model_reply(truth_movements()[:2], has_balances=False)
    read_with_ai(PHOTO, (SAMPLES / PHOTO).read_bytes())
    request = claude.requests[0]
    assert request["model"] == "claude-haiku-4-5"
    assert "fallbacks" not in request  # server-side fallbacks are only offered for Opus 5 / Fable 5
    image = request["messages"][0]["content"][0]
    assert image["type"] == "image" and image["source"]["media_type"] == "image/jpeg"


@pytest.mark.parametrize("stop_reason, message", [("refusal", "rifiutato"), ("max_tokens", "troppo lungo")])
def test_claude_stop_reasons(claude, stop_reason, message):
    claude.reply, claude.stop_reason = model_reply(truth_movements()[:1]), stop_reason
    with pytest.raises(bank_import.StatementImportError, match=message):
        read_with_ai(PHOTO, (SAMPLES / PHOTO).read_bytes())


# ── Web flow ───────────────────────────────────────────────────────────────────

def _upload(client, filename):
    return client.post("/export/bank", data={"file": (io.BytesIO((SAMPLES / filename).read_bytes()), filename), "bank": "auto"},
                       content_type="multipart/form-data")


def _balanced(html):
    return len(re.findall(r"<div\b", html)) == len(re.findall(r"</div>", html))


def test_scan_upload_asks_then_reads_then_saves_edited_rows(client, ollama, db):
    movements = truth_movements()[:5]
    closing = 3250.0 + sum(m["amount"] for m in movements)
    ollama.replies.extend([  # one reply per scanned page
        model_reply(movements[:3], has_balances=False),
        model_reply(movements[3:], opening=3250.0, closing=closing),
    ])

    # 1. Upload: nothing is sent to the model, the user is asked first
    response = _upload(client, SCAN)
    assert response.status_code == 302 and "/export/bank/ai/" in response.location
    assert ollama.calls == []
    page = client.get(response.location).get_data(as_text=True)
    assert "PDF scansionato" in page and "Sì, leggi con l" in page and _balanced(page)
    # only vision models can read a scan: the text-only one is listed but disabled
    assert re.search(r'<option value="llama3.2:1b"\s+disabled', page)

    # 2. Confirm with the chosen model → editable preview
    html = client.post(response.location, data={"model": "qwen2.5vl:7b"}).get_data(as_text=True)
    assert len(ollama.calls) == 2 and ollama.calls[0]["body"]["model"] == "qwen2.5vl:7b"
    assert "Movimenti letti con intelligenza artificiale" in html and "Quadratura verificata" in html
    assert _balanced(html)

    # 3. Save, correcting one amount the model misread
    client.post("/export/bank/confirm", data=form_data(html, "preview-form", **{"amount-0": "851,00"}))
    txs = Transaction.query.order_by(Transaction.date, Transaction.id).all()
    assert len(txs) == 5 and all("ai" in t.tags for t in txs)
    assert float(txs[0].amount) == 851.0

    # the pending upload was removed once read
    assert client.get(response.location).status_code == 302


def test_user_can_decline_ai(client, ollama, db):
    location = _upload(client, PHOTO).location
    client.post(location + "/cancel")
    assert ollama.calls == [] and client.get(location).status_code == 302  # file discarded


def test_ai_error_keeps_the_file_to_try_another_model(client, ollama, db):
    ollama.replies.append({"bank_name": "", "has_balances": False, "opening_balance": 0, "closing_balance": 0, "movements": []})
    location = _upload(client, PHOTO).location
    page = client.post(location, data={"model": "qwen2.5vl:7b"}).get_data(as_text=True)
    assert "nessun movimento riconosciuto" in page and "Sì, leggi con l" in page


def test_text_only_model_is_rejected_for_a_photo(client, ollama, db):
    location = _upload(client, PHOTO).location
    page = client.post(location, data={"model": "llama3.2:1b"}).get_data(as_text=True)
    assert "non può leggere questo file" in page and ollama.calls == []


def test_confirm_page_without_ai_links_to_the_setup(client, db):
    page = client.get(_upload(client, SCAN).location).get_data(as_text=True)
    assert "non è ancora configurata" in page and "/settings/ai" in page


def test_export_page_shows_ai_status(client, app):
    assert "Lettura AI non attiva" in client.get("/export/").get_data(as_text=True)
    app.config["LLM_PROVIDER"] = "ollama"
    html = client.get("/export/").get_data(as_text=True)
    assert "Lettura AI disponibile" in html and "qwen2.5vl:7b" in html and ".jpg" in html
