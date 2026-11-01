"""
The blocks of a page the user arranges with Modifica (static/js/blocks.js): their order, width (one to three
thirds), height (0 automatic, 1–3 taller) and whether they are shown, kept in the settings, one entry per page.
"""
from app.services import settings_store

SPANS = (1, 2, 3)
HEIGHTS = (0, 1, 2, 3)


def default(blocks: dict[str, int]) -> list[dict]:
    """`blocks`: {id: default width}, in the default order."""
    return [{"id": key, "span": span, "height": 0, "visible": True} for key, span in blocks.items()]


def normalize(items, blocks: dict[str, int]) -> list[dict]:
    """Known blocks once each, in the given order, with a valid width and height; missing ones added at the end."""
    out, seen = [], set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or item.get("id") not in blocks or item["id"] in seen:
            continue
        seen.add(item["id"])
        span, height = item.get("span"), item.get("height", 0)
        out.append({"id": item["id"], "span": span if span in SPANS else blocks[item["id"]],
                    "height": height if height in HEIGHTS else 0, "visible": item.get("visible", True) is not False})
    return out + [b for b in default(blocks) if b["id"] not in seen]


def load(setting: str, blocks: dict[str, int]) -> list[dict]:
    return normalize(settings_store.get_json(setting, [], expect=list), blocks)


def save(setting: str, blocks: dict[str, int], items) -> list[dict]:
    items = normalize(items, blocks)
    settings_store.set_json(setting, items)
    return items


def reset(setting: str, blocks: dict[str, int]) -> list[dict]:
    settings_store.set(setting, None)
    return default(blocks)
