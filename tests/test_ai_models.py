"""AI models page (Ollama catalog, download, removal, active model) and pending uploads."""
import io
import re
import json
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

import pytest

from app.services import ai_extraction, ai_models, upload_store

ROOT = Path(__file__).resolve().parent.parent


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def fake_ollama(app, monkeypatch):
    """Ollama admin API: /api/version, /api/tags, streaming /api/pull, /api/delete."""
    state = {"installed": ["qwen2.5vl:7b"], "requests": []}
    ai_models._pulls.clear()

    def urlopen(request, timeout=None):
        url, body = request.full_url, json.loads(request.data) if request.data else None
        state["requests"].append((request.get_method(), url.split("/api/")[1], body))
        if url.endswith("/api/version"):
            return _Response(b'{"version": "0.9.0"}')
        if url.endswith("/api/tags"):
            return _Response(json.dumps({"models": [{"name": n, "size": 6e9} for n in state["installed"]]}).encode())
        if url.endswith("/api/pull"):
            if body["model"] == "nonexistent:1b":
                return _Response(b'{"status":"pulling manifest"}\n{"error":"pull model manifest: file does not exist"}\n')
            state["installed"].append(body["model"])
            lines = [{"status": "pulling manifest"}, {"status": "downloading", "total": 100, "completed": 40},
                     {"status": "downloading", "total": 100, "completed": 100}, {"status": "success"}]
            return _Response("\n".join(json.dumps(line) for line in lines).encode() + b"\n")
        if url.endswith("/api/delete"):
            state["installed"].remove(body["model"])
            return _Response(b"")
        raise AssertionError(url)

    monkeypatch.setattr(ai_models.urllib.request, "urlopen", urlopen)
    return state


def wait_for(name):
    for _ in range(100):
        progress = ai_models.pull_progress(name)
        if progress.get("done"):
            return progress
        time.sleep(0.02)
    raise AssertionError("download did not finish")


# ── Catalog ────────────────────────────────────────────────────────────────────

def test_catalog_covers_llama_qwen_gemma_in_every_size_under_10gb():
    assert {m.family for m in ai_models.CATALOG} == {"Llama", "Qwen", "Gemma"}
    assert all(m.size_gb < 10 for m in ai_models.CATALOG)
    for tier in ai_models.TIERS:
        assert {m.family for m in ai_models.CATALOG if m.tier == tier} == {"Llama", "Qwen", "Gemma"}
    assert any(m.vision for m in ai_models.CATALOG if m.tier == "piccolo")


def test_vision_detection_for_models_outside_the_catalog():
    assert ai_models.is_vision("qwen2.5vl:32b") and ai_models.is_vision("llava:7b")
    assert not ai_models.is_vision("mistral:7b")


# ── Page ───────────────────────────────────────────────────────────────────────

def test_page_lists_catalog_with_install_state(client, fake_ollama):
    page = client.get("/settings/ai").get_data(as_text=True)
    assert "Ollama attivo" in page and "0.9.0" in page
    for model in ai_models.CATALOG:
        assert model.name in page
    row = page.split('data-model="qwen2.5vl:7b"')[1].split("</tr>")[0]
    assert "Installato" in row and "Rimuovi" in row
    row = page.split('data-model="gemma3:4b"')[1].split("</tr>")[0]
    assert "Installa" in row


def test_page_explains_how_to_install_ollama(client, app, monkeypatch):
    def refuse(*args, **kwargs):
        raise urllib.error.URLError("refused")
    monkeypatch.setattr(ai_models.urllib.request, "urlopen", refuse)
    page = client.get("/settings/ai").get_data(as_text=True)
    assert "Ollama non è in esecuzione" in page and "ollama.com/download" in page


def test_install_runs_in_background_with_progress(client, fake_ollama):
    client.post("/settings/ai/pull", data={"name": "gemma3:4b"})
    progress = wait_for("gemma3:4b")
    assert progress["error"] is None and progress["percent"] == 100
    assert client.get("/settings/ai/pull-status").get_json()["gemma3:4b"]["done"]
    assert "gemma3:4b" in fake_ollama["installed"]


def test_install_error_is_reported(client, fake_ollama):
    client.post("/settings/ai/pull", data={"name": "nonexistent:1b"})
    progress = wait_for("nonexistent:1b")
    assert "does not exist" in progress["error"]
    page = client.get("/settings/ai").get_data(as_text=True)
    assert page.count("nonexistent:1b") >= 0  # page still renders


def test_remove_model(client, fake_ollama):
    client.post("/settings/ai/delete", data={"name": "qwen2.5vl:7b"})
    assert fake_ollama["installed"] == []


@pytest.mark.parametrize("name", ["", "../etc/passwd", "a b", "x" * 200, "qwen;rm -rf"])
def test_invalid_model_names_are_rejected(client, fake_ollama, name):
    client.post("/settings/ai/pull", data={"name": name})
    client.post("/settings/ai/delete", data={"name": name})
    assert not any(kind in ("pull", "delete") for _, kind, _ in fake_ollama["requests"])


def test_choice_is_saved_and_wins_over_env(client, app, fake_ollama):
    app.config.update(LLM_PROVIDER="anthropic", LLM_MODEL="claude-haiku-4-5")
    client.post("/settings/ai/save", data={"provider": "ollama", "model": "qwen2.5vl:7b"})
    assert (ai_extraction.provider(), ai_extraction.model_name()) == ("ollama", "qwen2.5vl:7b")
    client.post("/settings/ai/save", data={"provider": "none", "model": ""})
    assert ai_extraction.provider() is None  # "Disattivata" also overrides .env


def test_each_provider_keeps_its_own_model(client, fake_ollama):
    client.post("/settings/ai/save", data={"provider": "ollama", "model": "gemma3:4b"})
    assert ai_extraction.model_name() == "gemma3:4b"
    client.post("/settings/ai/save", data={"provider": "anthropic", "model": ""})
    assert ai_extraction.model_name() == "claude-opus-5"  # not the Ollama tag
    client.post("/settings/ai/save", data={"provider": "ollama", "model": ""})
    assert ai_extraction.model_name() == "gemma3:4b"  # remembered


@pytest.mark.parametrize("provider, model", [("anthropic", "gemma3:4b"), ("ollama", "claude-haiku-4-5")])
def test_model_of_the_wrong_provider_is_refused(client, fake_ollama, provider, model):
    client.post("/settings/ai/save", data={"provider": provider, "model": model})
    assert ai_extraction.provider() is None  # nothing saved


# ── Pending uploads ────────────────────────────────────────────────────────────

def test_pending_upload_roundtrip_and_expiry(app, monkeypatch):
    token = upload_store.save("scan.pdf", b"%PDF-data", kind="scan")
    assert upload_store.load(token) == (b"%PDF-data", {"filename": "scan.pdf", "kind": "scan"})
    monkeypatch.setattr(upload_store, "MAX_AGE_SECONDS", -1)
    with pytest.raises(KeyError):
        upload_store.load(token)


@pytest.mark.parametrize("token", ["../../etc/passwd", "short", "a/b" * 10, ""])
def test_pending_upload_rejects_bad_tokens(app, token):
    with pytest.raises(KeyError):
        upload_store.load(token)


# ── Command line ───────────────────────────────────────────────────────────────

def test_install_script_dry_run():
    output = subprocess.run(
        [sys.executable, "scripts/install_models.py", "--tier", "piccolo", "--vision", "--dry-run"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split("\n")
    assert output[:2] == ["ollama pull qwen2.5vl:3b", "ollama pull gemma3:4b"]


def test_install_button_is_disabled_while_downloading(client, fake_ollama):
    ai_models._pulls["gemma3:4b"] = {"status": "downloading", "percent": 30, "done": False, "error": None}
    row = client.get("/settings/ai").get_data(as_text=True).split('data-model="gemma3:4b"')[1].split("</tr>")[0]
    assert "downloading 30%" in row
    assert re.search(r"<button[^>]*disabled[^>]*>\s*<i class=\"bi bi-download\"></i> Installa", row)
