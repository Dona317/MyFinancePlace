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

    def fake_urlopen(request, timeout=None):
        calls.append({"url": request.full_url, "body": json.loads(request.data)})
        reply = replies.pop(0) if len(replies) > 1 else replies[0]
        return Response(json.dumps({"message": {"content": json.dumps(reply)}}).encode())

    monkeypatch.setattr(ai_extraction.urllib.request, "urlopen", fake_urlopen)
    return SimpleNamespace(calls=calls, replies=replies)


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


# ── Disabled (default) ─────────────────────────────────────────────────────────

def test_scan_without_ai_explains_how_to_enable_it(app):
    with pytest.raises(bank_import.StatementImportError, match="LLM_PROVIDER"):
        bank_import.analyze_statement(SCAN, (SAMPLES / SCAN).read_bytes())


# ── Ollama (local) ─────────────────────────────────────────────────────────────

def test_scanned_pdf_read_page_by_page_with_ollama(ollama):
    movements = truth_movements()
    half = len(movements) // 2
    page1 = model_reply(movements[:half], has_balances=False)
    page2 = model_reply(movements[half:], opening=0, closing=3250.0 + sum(m["amount"] for m in movements))
    page1["has_balances"] = True  # page 1 prints the opening balance, page 2 the closing one
    page1["closing_balance"] = 0
    ollama.replies.extend([page1, page2])

    preview = bank_import.analyze_statement(SCAN, (SAMPLES / SCAN).read_bytes())

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
    preview = bank_import.analyze_statement(PHOTO, (SAMPLES / PHOTO).read_bytes())
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
    preview = bank_import.analyze_statement("foto.jpg", photo)
    assert not preview.balance_check.ok
    assert preview.balance_check.difference == Decimal(f"{movements[3]['amount']:.2f}")


def test_invalid_rows_from_the_model_are_discarded(ollama):
    reply = model_reply(truth_movements()[:4], has_balances=False)
    reply["movements"][0]["date"] = "31/02/2026"   # impossible date
    reply["movements"][1]["amount"] = 0            # no amount
    reply["movements"][2]["description"] = "  "    # no description
    ollama.replies.append(reply)
    preview = bank_import.analyze_statement("foto.jpg", (SAMPLES / PHOTO).read_bytes())
    assert len(preview.rows) == 1 and preview.discarded == 3


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
    preview = bank_import.analyze_statement("lettera.txt", text.encode())
    message = ollama.calls[0]["body"]["messages"][1]
    assert "images" not in message and "CONAD" in message["content"]
    assert [(r.description, r.type, r.category) for r in preview.rows] == [
        ("CONAD", "expense", "Alimentari"), ("Stipendio ACME SPA", "income", "Stipendio"),
    ]


def test_long_text_is_refused_not_truncated_for_the_local_model(ollama):
    text = "Movimento senza data riconoscibile\n" * 2000  # ~70k chars, over the local limit
    with pytest.raises(bank_import.StatementImportError, match="troppo lungo"):
        bank_import.analyze_statement("lungo.txt", text.encode())
    assert ollama.calls == []


def test_ollama_not_running(app, monkeypatch):
    import urllib.error
    app.config.update(LLM_PROVIDER="ollama")

    def refuse(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(ai_extraction.urllib.request, "urlopen", refuse)
    with pytest.raises(bank_import.StatementImportError, match="ollama serve"):
        bank_import.analyze_statement(PHOTO, (SAMPLES / PHOTO).read_bytes())


def test_model_not_pulled(app, monkeypatch):
    import urllib.error
    app.config.update(LLM_PROVIDER="ollama", LLM_MODEL="llama3.2-vision:11b")

    def not_found(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 404, "not found", {}, io.BytesIO(b""))

    monkeypatch.setattr(ai_extraction.urllib.request, "urlopen", not_found)
    with pytest.raises(bank_import.StatementImportError, match="ollama pull llama3.2-vision:11b"):
        bank_import.analyze_statement(PHOTO, (SAMPLES / PHOTO).read_bytes())


def test_well_formed_files_never_reach_the_model(ollama):
    """The rule-based reader stays first: AI is only a fallback."""
    name = "intesa_sanpaolo_lista_movimenti_2026-09.pdf"
    preview = bank_import.analyze_statement(name, (SAMPLES / name).read_bytes())
    assert ollama.calls == [] and preview.ai_model is None


# ── Anthropic (Claude) ─────────────────────────────────────────────────────────

def test_claude_receives_the_pdf_and_a_json_schema(claude):
    claude.reply = model_reply(truth_movements())
    preview = bank_import.analyze_statement(SCAN, (SAMPLES / SCAN).read_bytes())

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
    bank_import.analyze_statement(PHOTO, (SAMPLES / PHOTO).read_bytes())
    request = claude.requests[0]
    assert request["model"] == "claude-haiku-4-5"
    assert "fallbacks" not in request  # server-side fallbacks are only offered for Opus 5 / Fable 5
    image = request["messages"][0]["content"][0]
    assert image["type"] == "image" and image["source"]["media_type"] == "image/jpeg"


@pytest.mark.parametrize("stop_reason, message", [("refusal", "rifiutato"), ("max_tokens", "troppo lungo")])
def test_claude_stop_reasons(claude, stop_reason, message):
    claude.reply, claude.stop_reason = model_reply(truth_movements()[:1]), stop_reason
    with pytest.raises(bank_import.StatementImportError, match=message):
        bank_import.analyze_statement(PHOTO, (SAMPLES / PHOTO).read_bytes())


# ── Web flow ───────────────────────────────────────────────────────────────────

def test_upload_scan_preview_and_confirm_tags_rows_as_ai(client, ollama, db):
    movements = truth_movements()[:5]
    closing = 3250.0 + sum(m["amount"] for m in movements)
    ollama.replies.extend([  # one reply per scanned page
        model_reply(movements[:3], has_balances=False),
        model_reply(movements[3:], opening=3250.0, closing=closing),
    ])
    html = client.post("/export/bank", data={"file": (io.BytesIO((SAMPLES / SCAN).read_bytes()), SCAN), "bank": "auto"},
                       content_type="multipart/form-data").get_data(as_text=True)
    assert "Movimenti letti con intelligenza artificiale" in html
    assert "Quadratura verificata" in html
    assert len(re.findall(r"<div\b", html)) == len(re.findall(r"</div>", html))
    payload = re.search(r'name="payload" value="([^"]+)"', html).group(1)
    client.post("/export/bank/confirm", data={"payload": payload, "include": [str(i) for i in range(5)]})
    assert Transaction.query.count() == 5
    assert all("ai" in t.tags for t in Transaction.query.all())


def test_export_page_shows_ai_status(client, app):
    assert "Lettura AI non attiva" in client.get("/export/").get_data(as_text=True)
    app.config["LLM_PROVIDER"] = "ollama"
    html = client.get("/export/").get_data(as_text=True)
    assert "Lettura AI attiva" in html and "qwen2.5vl:7b" in html and ".jpg" in html
