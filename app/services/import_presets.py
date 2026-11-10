"""
Saved import presets (F61): the column mapping of a bank's or broker's file, remembered under a name («Fineco carta»)
and applied again when a file with the same columns is uploaded.

Stored in the key-value settings (services.settings_store) as a JSON list, no table of their own. A preset holds:
- id, name, kind ("bank" for the CSV / Excel movements with manual mapping, "broker" kept for the broker files);
- signature: the file's column titles, normalized (lowercase words and numbers), in order: the same layout has the
  same signature whatever the case, accents or punctuation of the titles;
- mapping: field → column title, as the user confirmed it;
- options: what else the import used (the header line, the account the movements went to).
"""
from __future__ import annotations

import secrets
import unicodedata

from app.services import settings_store
from app.services.parsing import normalize

KEY = "import_presets"
KINDS = ("bank", "broker")
NAME_LENGTH = 60


def _key(title: str) -> str:
    """A column title without case, accents and punctuation: «Quantità (€)» → «quantita»."""
    return normalize(unicodedata.normalize("NFKD", str(title or "")).encode("ascii", "ignore").decode())


def signature(headers: list[str]) -> list[str]:
    """The layout of a file: its normalized column titles, in order."""
    return [_key(h) for h in headers]


def clean_name(name: str | None) -> str:
    return " ".join((name or "").split())[:NAME_LENGTH]


def all_presets(kind: str | None = None) -> list[dict]:
    """The saved presets (of one kind), by name."""
    presets = [p for p in settings_store.get_json(KEY, [], expect=list)
               if isinstance(p, dict) and p.get("id") and p.get("name")]
    if kind:
        presets = [p for p in presets if p.get("kind") == kind]
    return sorted(presets, key=lambda p: p["name"].lower())


def _store(presets: list[dict]) -> None:
    settings_store.set_json(KEY, presets or None)


def get(preset_id: str | None) -> dict | None:
    return next((p for p in all_presets() if p["id"] == preset_id), None) if preset_id else None


def resolve(preset: dict, headers: list[str]) -> dict[str, str | None]:
    """The preset's mapping on this file's headers (matched by normalized title); a column the file lacks is None."""
    by_key = {_key(h): h for h in headers}
    return {field: by_key.get(_key(column)) if column else None
            for field, column in (preset.get("mapping") or {}).items()}


def usable(headers: list[str], kind: str) -> list[dict]:
    """Presets that can be applied to a file with these headers: every column they map is in the file."""
    keys = set(signature(headers))
    return [p for p in all_presets(kind)
            if all(_key(c) in keys for c in (p.get("mapping") or {}).values() if c)]


def match(headers: list[str], kind: str) -> dict | None:
    """The preset saved for exactly this layout (the most recently saved one, if several)."""
    wanted = signature(headers)
    found = [p for p in settings_store.get_json(KEY, [], expect=list)
             if isinstance(p, dict) and p.get("kind") == kind and p.get("signature") == wanted and p.get("id")]
    return found[-1] if found else None


def save(name: str, kind: str, headers: list[str], mapping: dict, options: dict | None = None) -> dict:
    """Save (or replace, when the name is taken) a preset; returns it."""
    name = clean_name(name)
    if not name:
        raise ValueError("a preset needs a name")
    if kind not in KINDS:
        raise ValueError(f"unknown preset kind: {kind}")
    presets = settings_store.get_json(KEY, [], expect=list)
    old = next((p for p in presets if isinstance(p, dict) and str(p.get("name", "")).lower() == name.lower()), None)
    preset = {
        "id": old["id"] if old and old.get("id") else secrets.token_hex(4),
        "name": name,
        "kind": kind,
        "signature": signature(headers),
        "mapping": {field: column for field, column in mapping.items() if column},
        "options": {k: v for k, v in (options or {}).items() if v not in (None, "")},
    }
    presets = [p for p in presets if p is not old] + [preset]
    _store(presets)
    return preset


def rename(preset_id: str, name: str) -> dict:
    """Give a preset another name; ValueError when empty or used by another preset."""
    name = clean_name(name)
    if not name:
        raise ValueError("empty name")
    presets = settings_store.get_json(KEY, [], expect=list)
    preset = next((p for p in presets if isinstance(p, dict) and p.get("id") == preset_id), None)
    if preset is None:
        raise KeyError(preset_id)
    if any(isinstance(p, dict) and p is not preset and str(p.get("name", "")).lower() == name.lower()
           for p in presets):
        raise ValueError("name taken")
    preset["name"] = name
    _store(presets)
    return preset


def delete(preset_id: str) -> bool:
    presets = settings_store.get_json(KEY, [], expect=list)
    kept = [p for p in presets if not (isinstance(p, dict) and p.get("id") == preset_id)]
    if len(kept) == len(presets):
        return False
    _store(kept)
    return True
