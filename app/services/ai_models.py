"""
Local AI models (Ollama): catalog of Llama / Qwen / Gemma models under 10 GB, and helpers to list,
download ("pull") and remove them through Ollama's HTTP API.

Vision models read scans and photos; text-only models can read only text documents with a
non-standard layout. Sizes are the approximate download size of Ollama's default (Q4) build.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass

TIERS = {"medio": "Medi (5–10 GB)", "piccolo": "Piccoli (2–4 GB)", "tiny": "Tiny (< 2 GB)"}


@dataclass(frozen=True)
class CatalogModel:
    name: str          # Ollama tag
    family: str        # Llama | Qwen | Gemma
    size_gb: float     # approximate download size
    tier: str          # medio | piccolo | tiny
    vision: bool       # can read images (scans, photos)
    note: str = ""

    @property
    def ram_gb(self) -> int:
        """Rough RAM needed to run it comfortably."""
        return int(self.size_gb + 2.5) + 1


CATALOG: list[CatalogModel] = [
    # ── Medium: best accuracy under 10 GB ─────────────────────────────────────
    CatalogModel("qwen2.5vl:7b", "Qwen", 6.0, "medio", True, "Consigliato: il più preciso nel leggere documenti e tabelle"),
    CatalogModel("llama3.2-vision:11b", "Llama", 7.8, "medio", True),
    CatalogModel("gemma3:12b", "Gemma", 8.1, "medio", True),
    CatalogModel("qwen3:8b", "Qwen", 5.2, "medio", False),
    CatalogModel("llama3.1:8b", "Llama", 4.9, "medio", False),
    # ── Small: laptops with 8 GB of RAM ───────────────────────────────────────
    CatalogModel("qwen2.5vl:3b", "Qwen", 3.2, "piccolo", True, "Il vision più leggero: buon compromesso"),
    CatalogModel("gemma3:4b", "Gemma", 3.3, "piccolo", True),
    CatalogModel("qwen3:4b", "Qwen", 2.5, "piccolo", False),
    CatalogModel("llama3.2:3b", "Llama", 2.0, "piccolo", False),
    # ── Tiny: very old or low-memory machines, text documents only ────────────
    CatalogModel("qwen3:1.7b", "Qwen", 1.4, "tiny", False),
    CatalogModel("llama3.2:1b", "Llama", 1.3, "tiny", False),
    CatalogModel("gemma3:1b", "Gemma", 0.8, "tiny", False),
    CatalogModel("qwen3:0.6b", "Qwen", 0.5, "tiny", False, "Il più piccolo: solo testi semplici"),
]
BY_NAME = {m.name: m for m in CATALOG}
VISION_FAMILIES = ("vl", "vision", "gemma3:4b", "gemma3:12b", "gemma3:27b", "llava", "minicpm-v", "moondream")


def is_vision(name: str) -> bool:
    """True when a model can read images; unknown models are judged by their name."""
    if name in BY_NAME:
        return BY_NAME[name].vision
    return any(marker in name for marker in VISION_FAMILIES)


class OllamaError(RuntimeError):
    """User-facing (Italian) message about an Ollama problem."""


# ── Ollama admin API ───────────────────────────────────────────────────────────

def _request(base_url: str, path: str, method: str = "GET", body: dict | None = None, timeout: float = 10):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        base_url.rstrip("/") + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:200].decode(errors="replace")
        raise OllamaError(f"Ollama ha risposto con un errore ({exc.code}): {detail}")
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        raise OllamaError(f"Ollama non è raggiungibile su {base_url}: è installato e avviato (`ollama serve`)?")


def status(base_url: str) -> dict:
    """{"running": bool, "version": str|None, "installed": {name: size_gb}, "error": str|None}"""
    try:
        with _request(base_url, "/api/version", timeout=3) as response:
            version = json.loads(response.read()).get("version")
        with _request(base_url, "/api/tags", timeout=5) as response:
            models = json.loads(response.read()).get("models", [])
    except OllamaError as exc:
        return {"running": False, "version": None, "installed": {}, "error": str(exc)}
    installed = {m["name"]: round(m.get("size", 0) / 1e9, 1) for m in models if "name" in m}
    return {"running": True, "version": version, "installed": installed, "error": None}


def delete(base_url: str, name: str) -> None:
    with _request(base_url, "/api/delete", method="DELETE", body={"model": name}):
        pass


# ── Background downloads ───────────────────────────────────────────────────────

_pulls: dict[str, dict] = {}
_lock = threading.Lock()


def pull_progress(name: str | None = None) -> dict:
    with _lock:
        if name is not None:
            return dict(_pulls.get(name, {}))
        return {k: dict(v) for k, v in _pulls.items()}


def _update(name: str, **values) -> None:
    with _lock:
        _pulls.setdefault(name, {}).update(values)


def start_pull(base_url: str, name: str) -> bool:
    """Start downloading a model in a background thread; False if it is already downloading."""
    with _lock:
        current = _pulls.get(name)
        if current and not current.get("done"):
            return False
        _pulls[name] = {"status": "in attesa", "completed": 0, "total": 0, "percent": 0, "done": False, "error": None}
    threading.Thread(target=_pull, args=(base_url, name), daemon=True, name=f"ollama-pull-{name}").start()
    return True


def _pull(base_url: str, name: str) -> None:
    """Stream Ollama's pull progress (one JSON object per line) into the shared progress table."""
    try:
        with _request(base_url, "/api/pull", method="POST", body={"model": name, "stream": True}, timeout=3600) as response:
            for line in response:
                if not line.strip():
                    continue
                event = json.loads(line)
                if "error" in event:
                    raise OllamaError(event["error"])
                total, completed = event.get("total") or 0, event.get("completed") or 0
                values = {"status": event.get("status", "")}
                if total:
                    values.update(total=total, completed=completed, percent=int(completed * 100 / total))
                _update(name, **values)
        _update(name, status="completato", percent=100, done=True)
    except (OllamaError, json.JSONDecodeError, OSError) as exc:
        _update(name, status="errore", error=str(exc), done=True)
