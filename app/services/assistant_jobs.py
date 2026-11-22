"""
The questions of the «Chiedi ai tuoi dati» panel answered in the background (22 Nov 2026): the request only starts
a job and the page polls it, so the user can close the panel or move to another page while the model thinks — the
next page picks the job up again and a note says when the answer is ready.

    running ──▶ done | error

Jobs live in memory (one process with threads, as ai_jobs), each for the user and archive that asked, and are
forgotten an hour after they finish. With AI_JOBS_SYNC (TestingConfig) a job runs inline, in the request.
"""
from __future__ import annotations

import secrets
import threading
import time

from flask import Flask, current_app

from app.services import assistant, studio
from app.services.ai_extraction import AIExtractionError

KEEP_SECONDS = 3600
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def _forget_old() -> None:
    limit = time.time() - KEEP_SECONDS
    with _lock:
        for key in [k for k, job in _jobs.items() if (job.get("finished_at") or job["started_at"]) < limit]:
            _jobs.pop(key, None)


def _set(job_id: str, **values) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(values)


def start(question: str, owner: str) -> dict:
    """Start answering `question` for `owner` (the user and archive asking); returns the job as get() does."""
    _forget_old()
    job_id = secrets.token_urlsafe(9)
    with _lock:
        _jobs[job_id] = {"id": job_id, "owner": owner, "question": question, "state": "running",
                         "started_at": time.time(), "finished_at": None, "text": None, "links": [], "error": None}
    if current_app.config.get("AI_JOBS_SYNC"):
        _work(job_id, question)
    else:
        app = current_app._get_current_object()
        threading.Thread(target=_run, args=(app, studio.current(), job_id, question), daemon=True,
                         name=f"ask-{job_id}").start()
    return get(job_id, owner)


def _run(app: Flask, client, job_id: str, question: str) -> None:
    with app.app_context():
        studio.activate(client)  # the archive of who asked
        _work(job_id, question)


def _work(job_id: str, question: str) -> None:
    try:
        answer = assistant.ask(question)
    except AIExtractionError as exc:
        _set(job_id, state="error", error=str(exc), finished_at=time.time())
    except Exception:
        current_app.logger.exception("Assistant question failed")
        _set(job_id, state="error", error="Risposta non riuscita: errore imprevisto, riprova.", finished_at=time.time())
    else:
        _set(job_id, state="done", text=answer.text, links=[list(link) for link in answer.links],
             finished_at=time.time())


def get(job_id: str, owner: str) -> dict | None:
    """The job, if it is `owner`'s; with `elapsed` seconds."""
    with _lock:
        job = dict(_jobs.get(job_id) or {})
    if not job or job["owner"] != owner:
        return None
    job["elapsed"] = round((job["finished_at"] or time.time()) - job["started_at"])
    job.pop("owner")
    return job
