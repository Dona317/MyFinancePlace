"""
AI reading of an uploaded statement in the background (Esporta → importa estratto conto → "Leggi con AI").

A local model can need minutes per page: the request only starts a job, the browser polls its status.
There is one job per pending upload, identified by the upload token (see upload_store).

    queued ──▶ running ──▶ done | error | cancelled
                  └── the process stopped mid-reading ──▶ interrupted (shown with "Riprova")

State lives in memory (gunicorn runs one process with threads, see gunicorn.conf.py) and is mirrored
to <token>.job.json next to the upload, so every thread, a page reload or a restarted process sees it.
While a job runs a heartbeat refreshes the file: a queued/running job whose heartbeat is stale and whose
thread is not alive in this process was interrupted.

The job keeps the model's raw result (AIExtraction as a dict); the editable preview is built from it by
the request that shows it, so duplicates and categories reflect the database at that moment.
With AI_JOBS_SYNC (TestingConfig) the job runs inline, in the request that starts it.
"""
from __future__ import annotations

import dataclasses
import json
import os
import threading
import time
from pathlib import Path

from flask import Flask, current_app

from app.services import ai_extraction, bank_import, studio, upload_store

ACTIVE = ("queued", "running")
DONE_LABELS = {"pagina": "Pagine lette", "parte": "Parti lette", "blocco di pagine": "Blocchi di pagine letti"}
HEARTBEAT_SECONDS = 10
STALE_SECONDS = 3 * HEARTBEAT_SECONDS


class Cancelled(Exception):
    """Raised from the progress callback when the user asked to stop the reading."""


_jobs: dict[str, dict] = {}                   # token → state (same content as the JSON file)
_files: dict[str, Path] = {}                  # token → its JSON file
_threads: dict[str, threading.Thread] = {}
_cancel: dict[str, threading.Event] = {}
_lock = threading.Lock()


# ── State ──────────────────────────────────────────────────────────────────────

def _file(token: str) -> Path | None:
    with _lock:
        if token in _files:
            return _files[token]
    try:
        return upload_store.sidecar_path(token, "job")
    except KeyError:
        return None


def _read_file(path: Path | None) -> dict | None:
    try:
        return json.loads(path.read_text()) if path else None
    except (OSError, ValueError):
        return None


def _write(path: Path, state: dict) -> None:
    """Atomic write; skipped once the upload is gone (read, cancelled or expired)."""
    if not path.with_name(path.name.split(".")[0] + ".bin").exists():
        return
    tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(state))
    os.replace(tmp, path)


def _update(token: str, **values) -> dict:
    with _lock:
        job = _jobs.get(token) or _read_file(_files.get(token)) or {}
        job.update(values, heartbeat=time.time())
        _jobs[token] = job
        if token in _files:
            _write(_files[token], job)
        return dict(job)


def _alive(token: str) -> bool:
    thread = _threads.get(token)
    return bool(thread and thread.is_alive())


def get(token: str) -> dict | None:
    """The job of an upload (None if never started or the upload is gone), with `elapsed` seconds."""
    path = _file(token)
    stored = _read_file(path)
    with _lock:
        if stored is None:  # upload read, cancelled or expired: forget the job
            _jobs.pop(token, None)
            return None
        _files.setdefault(token, path)  # e.g. after a restart: later updates go to the same file
        job = dict(_jobs.get(token) or stored)
        if job["state"] in ACTIVE and not _alive(token):
            ours = token in _threads  # our thread died, or another process stopped sending heartbeats
            if ours or time.time() - job.get("heartbeat", 0) > STALE_SECONDS:
                job["state"] = "interrupted"
    job["elapsed"] = round((job.get("finished_at") or time.time()) - job["started_at"])
    job["progress"] = (f"{DONE_LABELS.get(job['unit'], 'Parti lette')}: {job['done']} di {job['total']}"
                       if job.get("total", 0) > 1 else "")
    return job


def is_active(job: dict | None) -> bool:
    return bool(job and job["state"] in ACTIVE)


def result(token: str) -> ai_extraction.AIExtraction | None:
    """What the model read, once the job is done."""
    job = get(token)
    if not job or job["state"] != "done" or not job.get("result"):
        return None
    return ai_extraction.AIExtraction(**job["result"])


# ── Running ────────────────────────────────────────────────────────────────────

def start(token: str, filename: str, raw: bytes, bank: str, model: str | None) -> dict:
    """Start reading the upload with `model` (None: the configured one); an already running job is kept."""
    current = get(token)
    if is_active(current):  # a double submit, or a reload of the confirmation form
        return current

    model_name = model or ai_extraction.model_name()
    now = time.time()
    job = {
        "token": token, "state": "queued", "filename": filename, "model": model_name,
        "label": ai_extraction.describe(model_name), "started_at": now, "finished_at": None, "heartbeat": now,
        "done": 0, "total": 0, "unit": "", "rows": 0, "error": None, "cancel_requested": False, "result": None,
    }
    path = upload_store.sidecar_path(token, "job")
    with _lock:
        _jobs[token], _files[token], _cancel[token] = job, path, threading.Event()
        _threads.pop(token, None)
        _write(path, job)

    args = (token, filename, raw, bank, model)
    if current_app.config.get("AI_JOBS_SYNC"):
        _work(*args)
    else:
        app = current_app._get_current_object()
        thread = threading.Thread(target=_run, args=(app, studio.current(), *args), daemon=True, name=f"ai-job-{token[:8]}")
        with _lock:
            _threads[token] = thread
            thread.start()
    return get(token) or job


def _run(app: Flask, client, token: str, *args) -> None:
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(HEARTBEAT_SECONDS):
            _update(token)

    threading.Thread(target=heartbeat, daemon=True, name=f"ai-job-heartbeat-{token[:8]}").start()
    try:
        with app.app_context():
            studio.activate(client)  # the archive of the client that uploaded the file (F11)
            _work(token, *args)
    finally:
        stop.set()


def _cancel_requested(token: str) -> bool:
    event = _cancel.get(token)
    if event and event.is_set():
        return True
    return bool((_read_file(_files.get(token)) or {}).get("cancel_requested"))  # e.g. from another process


def _work(token: str, filename: str, raw: bytes, bank: str, model: str | None) -> None:
    def progress(done: int, total: int, unit: str) -> None:
        if _cancel_requested(token):
            raise Cancelled
        _update(token, state="running", done=done, total=total, unit=unit)

    _update(token, state="running")
    try:
        extraction = bank_import.read_with_ai(filename, raw, model, progress)
        if _cancel_requested(token):  # asked while the last model call was running
            raise Cancelled
        preview = bank_import.preview_from_ai(filename, extraction, bank)  # validates: e.g. no movements found
    except Cancelled:
        _update(token, state="cancelled", finished_at=time.time())
    except bank_import.StatementImportError as exc:
        _update(token, state="error", error=str(exc), finished_at=time.time())
    except Exception:
        current_app.logger.exception("AI reading of %s failed", filename)
        _update(token, state="error", error="Lettura AI non riuscita: errore imprevisto, riprova.",
                finished_at=time.time())
    else:
        _update(token, state="done", result=dataclasses.asdict(extraction), rows=len(preview.rows),
                finished_at=time.time())


def cancel(token: str) -> None:
    """Ask a running job to stop: it checks between pages/parts (a model call already sent may finish first)."""
    job = get(token)
    if not job:
        return
    with _lock:
        if token in _cancel:
            _cancel[token].set()
    if job["state"] == "interrupted":
        _update(token, state="cancelled", finished_at=time.time())
    elif is_active(job):
        _update(token, cancel_requested=True)


def discard(token: str) -> None:
    """Stop the job and remove it together with the upload."""
    cancel(token)
    upload_store.delete(token)
    with _lock:
        for registry in (_jobs, _files):  # the cancel flag stays set for a thread still running
            registry.pop(token, None)


def wait(token: str, timeout: float | None = None) -> None:
    """Wait for the job's thread to finish (tests)."""
    thread = _threads.get(token)
    if thread:
        thread.join(timeout)
