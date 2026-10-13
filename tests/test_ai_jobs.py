"""
AI reading in the background: the request starts a job, the waiting page polls its status.

These tests run the real thread (AI_JOBS_SYNC off) with a fake model that reads one "page" each time
the test lets it, so progress, cancellation, errors and the final preview can be checked step by step.
"""
import io
import json
import threading
import time
from pathlib import Path

import pytest

from app.services import ai_extraction, ai_jobs, upload_store

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "bank_statements"
PHOTO = "FOTO_estratto_conto_intesa_2026-09.jpg"
MOVEMENTS = [
    {"date": "2026-09-02", "description": "Esselunga Milano", "details": "Pagamento POS", "amount": -45.30},
    {"date": "2026-09-05", "description": "Stipendio settembre", "details": "Bonifico", "amount": 2450.00},
]


class FakeModel:
    """Stands in for ai_extraction.extract: reads `pages` pages, each one when the test calls step()."""

    def __init__(self, pages=3, error=None, movements=MOVEMENTS):
        self.pages, self.error, self.movements = pages, error, movements
        self.permits = threading.Semaphore(0)
        self.read = []  # page numbers actually sent to the "model"

    def __call__(self, filename, raw, text=None, model=None, progress=None):
        progress(0, self.pages, "pagina")
        for number in range(1, self.pages + 1):
            assert self.permits.acquire(timeout=10), "the test never let the page finish"
            self.read.append(number)
            if self.error:
                raise ai_extraction.AIExtractionError(self.error)
            progress(number, self.pages, "pagina")
        return ai_extraction.AIExtraction(movements=list(self.movements), bank_name="Intesa Sanpaolo", model=model)

    def step(self, pages=1):
        for _ in range(pages):
            self.permits.release()


@pytest.fixture()
def fake_model(app, monkeypatch):
    app.config.update(LLM_PROVIDER="anthropic", LLM_MODEL="", AI_JOBS_SYNC=False)
    fake = FakeModel()
    monkeypatch.setattr(ai_extraction, "extract", fake)
    yield fake
    fake.step(100)  # never leave a thread waiting on the test database
    for thread in list(ai_jobs._threads.values()):
        thread.join(10)


def _start(client, model="claude-haiku-4-5"):
    upload = client.post("/export/bank", data={"file": (io.BytesIO((SAMPLES / PHOTO).read_bytes()), PHOTO), "bank": "auto"},
                         content_type="multipart/form-data")
    location = upload.location
    response = client.post(location, data={"model": model})
    assert response.status_code == 302 and response.location == location + "/wait"
    return location, location.rsplit("/", 1)[1]


def _status(client, location):
    return client.get(location + "/status").get_json()


def _until(client, location, check, timeout=10):
    """Poll the status endpoint like the waiting page does, until `check(status)` holds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = _status(client, location)
        if check(status):
            return status
        time.sleep(0.02)
    raise AssertionError(f"status never matched: {status}")


def test_reading_runs_in_the_background_with_progress_then_shows_the_preview(client, fake_model, db):
    location, token = _start(client)

    status = _until(client, location, lambda s: s["state"] == "running" and s["total"] == 3)
    assert status["done"] == 0 and status["model"] == "claude-haiku-4-5"
    assert "Anthropic" in status["label"] and "claude-haiku-4-5" in status["label"]

    page = client.get(location + "/wait").get_data(as_text=True)
    assert "Lettura in corso" in page and "claude-haiku-4-5" in page
    assert '<meta http-equiv="refresh"' in page and "/status" in page  # works with and without JavaScript
    assert client.get(location).location.endswith("/wait")  # the confirmation form is not offered twice

    fake_model.step()
    status = _until(client, location, lambda s: s["done"] == 1)
    assert status["progress"] == "Pagine lette: 1 di 3" and status["state"] == "running"
    assert "Pagine lette: 1 di 3" in client.get(location + "/wait").get_data(as_text=True)

    # the state is also on disk, next to the upload
    stored = json.loads(upload_store.sidecar_path(token, "job").read_text())
    assert stored["state"] == "running" and stored["done"] == 1

    fake_model.step(2)
    ai_jobs.wait(token, 10)
    status = _status(client, location)
    assert status["state"] == "done" and status["rows"] == 2 and status["url"].endswith("/result")

    # the waiting page (e.g. without JavaScript) goes to the result, which is the usual editable preview
    assert client.get(location + "/wait").location.endswith("/result")
    html = client.get(status["url"]).get_data(as_text=True)
    assert "Movimenti letti con intelligenza artificiale" in html and "Esselunga Milano" in html
    assert 'name="payload"' in html

    # the upload and the job are gone once the preview is shown
    assert client.get(location).status_code == 302 and client.get(location).location.endswith("/export/")
    assert client.get(location + "/status").status_code == 404


def test_cancel_stops_between_pages(client, fake_model, db):
    location, token = _start(client)
    _until(client, location, lambda s: s["total"] == 3)

    response = client.post(location + "/cancel", data={"scope": "job"})
    assert response.location.endswith("/wait")
    status = _status(client, location)
    assert status["state"] == "running" and status["cancel_requested"] is True
    assert "Annullamento in corso" in client.get(location + "/wait").get_data(as_text=True)

    fake_model.step()  # the page being read finishes, then the job stops
    ai_jobs.wait(token, 10)
    assert _status(client, location)["state"] == "cancelled"
    assert fake_model.read == [1]

    page = client.get(location + "/wait").get_data(as_text=True)
    assert "Lettura annullata" in page and "Riprova" in page and "Scegli un altro modello" in page
    assert "Sì, leggi con l" in client.get(location).get_data(as_text=True)  # the file is kept

    # "Riprova" reads it again with the same model
    fake_model.read.clear()
    assert client.post(location, data={"model": "claude-haiku-4-5"}).location.endswith("/wait")
    fake_model.step(3)
    ai_jobs.wait(token, 10)
    assert _status(client, location)["state"] == "done" and fake_model.read == [1, 2, 3]


def test_model_errors_are_shown_on_the_waiting_page(client, fake_model, db):
    fake_model.error = "Ollama non raggiungibile su http://localhost:11434/api/chat: avvialo con `ollama serve`."
    location, token = _start(client)
    fake_model.step()
    ai_jobs.wait(token, 10)

    status = _status(client, location)
    assert status["state"] == "error" and status["error"].startswith("Lettura AI non riuscita: Ollama non raggiungibile")
    page = client.get(location + "/wait").get_data(as_text=True)
    assert "Ollama non raggiungibile" in page and "Scegli un altro modello" in page and "Annulla l'importazione" in page
    assert "Sì, leggi con l" in client.get(location).get_data(as_text=True)  # the way back

    client.post(location + "/cancel")
    assert client.get(location).status_code == 302  # import dropped


def test_no_movements_is_an_error_not_an_empty_preview(client, fake_model, db):
    fake_model.pages, fake_model.movements = 1, []
    location, token = _start(client)
    fake_model.step()
    ai_jobs.wait(token, 10)
    assert "nessun movimento riconosciuto" in _status(client, location)["error"]


def test_a_reading_cut_by_a_restart_can_be_retried(client, fake_model, app, db):
    location, token = _start(client)
    _until(client, location, lambda s: s["total"] == 3)
    fake_model.step(3)
    ai_jobs.wait(token, 10)

    # what a restarted process finds: the file says "running", no thread, no heartbeat for a while
    path = upload_store.sidecar_path(token, "job")
    state = json.loads(path.read_text())
    state.update(state="running", heartbeat=time.time() - 120, finished_at=None, result=None)
    path.write_text(json.dumps(state))
    for registry in (ai_jobs._jobs, ai_jobs._threads, ai_jobs._files):
        registry.clear()

    assert _status(client, location)["state"] == "interrupted"
    page = client.get(location + "/wait").get_data(as_text=True)
    assert "si è interrotta" in page and "Riprova" in page and '<meta http-equiv="refresh"' not in page

    assert client.post(location, data={"model": "claude-haiku-4-5"}).location.endswith("/wait")
    fake_model.step(3)
    ai_jobs.wait(token, 10)
    assert _status(client, location)["state"] == "done"


def test_a_job_in_another_process_is_not_interrupted_while_its_heartbeat_is_fresh(client, fake_model, db):
    location, token = _start(client)
    _until(client, location, lambda s: s["total"] == 3)
    thread = ai_jobs._threads.pop(token)  # as seen from another process: no thread here, but a recent heartbeat
    try:
        assert _status(client, location)["state"] == "running"
    finally:
        fake_model.step(3)
        thread.join(10)


def test_double_submit_keeps_the_running_job(client, fake_model, db):
    location, token = _start(client)
    thread = ai_jobs._threads[token]
    assert client.post(location, data={"model": "claude-haiku-4-5"}).location.endswith("/wait")
    assert ai_jobs._threads[token] is thread


def test_unknown_or_finished_upload(client, db):
    assert client.get("/export/bank/ai/" + "x" * 32 + "/status").status_code == 404
    assert client.get("/export/bank/ai/" + "x" * 32 + "/wait").location.endswith("/export/")
    assert client.get("/export/bank/ai/" + "x" * 32 + "/result").location.endswith("/export/")
