"""
Saved views of the register (F101): a name and a search — the text, the filters and the order — to open again with one
click («Spese auto», «Da classificare»). The period is not part of a view: it is the shared one (services.shared_period),
so a view works on whatever period is chosen. The views are the signed-in user's, the same on every tab of Transazioni;
a tab's own fixed filter (the income of Entrate, …) still holds over a view.
"""
from __future__ import annotations

from app.services import settings_store

SETTING = "register.views.{user}"
MAX_VIEWS = 20
MAX_NAME = 40
# what a view keeps: the register's filters without the dates (the period is shared), and the order
KEYS = ("q", "type", "category", "recurring", "account", "tag", "person", "cluster", "min", "max", "card", "sort", "dir")


def _key() -> str:
    from flask_login import current_user

    user = getattr(current_user, "id", None) if getattr(current_user, "is_authenticated", False) else None
    return SETTING.format(user=user or 0)


def _clean(item) -> dict | None:
    if not isinstance(item, dict):
        return None
    name = " ".join(str(item.get("name") or "").split())[:MAX_NAME]
    query = item.get("query") if isinstance(item.get("query"), dict) else {}
    query = {k: str(v)[:200] for k, v in query.items() if k in KEYS and str(v).strip()}
    return {"name": name, "query": query} if name and query else None


def load() -> list[dict]:
    """The saved views, in the order they were saved."""
    stored = settings_store.get_json(_key(), [], expect=list) or []
    return [view for view in (_clean(item) for item in stored) if view]


def query_of(args) -> dict:
    """The search a view would keep, from the register's address (the empty fields and the dates left out)."""
    return {k: args.get(k, "").strip() for k in KEYS if args.get(k, "").strip()}


def save(name: str, query: dict) -> dict:
    """A new view, or the one with the same name replaced. ValueError when there is nothing to keep."""
    view = _clean({"name": name, "query": query})
    if view is None:
        raise ValueError("empty")
    views = [v for v in load() if v["name"].casefold() != view["name"].casefold()]
    views.append(view)
    settings_store.set_json(_key(), views[-MAX_VIEWS:])
    return view


def delete(name: str) -> None:
    settings_store.set_json(_key(), [v for v in load() if v["name"] != name])


# ── The register's own settings (F101, «Gestisci» of Transazioni): rows per page, columns shown, the cards on top ──

PREFS_SETTING = "register.prefs.{user}"
PAGE_SIZES = (25, 50, 100, 200)
HIDEABLE = ("category", "tags")


def prefs() -> dict:
    """The signed-in user's choices: {"page_size", "hide": [columns], "cards": bool}."""
    stored = settings_store.get_json(_key().replace("register.views.", "register.prefs."), {}, expect=dict) or {}
    size = stored.get("page_size")
    return {"page_size": size if size in PAGE_SIZES else 100,
            "hide": [c for c in stored.get("hide", []) if c in HIDEABLE],
            "cards": stored.get("cards", True) is not False}


def save_prefs(page_size, hide, cards) -> dict:
    try:
        page_size = int(page_size)
    except (TypeError, ValueError):
        page_size = 100
    value = {"page_size": page_size if page_size in PAGE_SIZES else 100,
             "hide": [c for c in hide if c in HIDEABLE], "cards": bool(cards)}
    settings_store.set_json(_key().replace("register.views.", "register.prefs."), value)
    return value
