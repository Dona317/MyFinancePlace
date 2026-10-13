"""Tags of the transactions: parsing what the user typed, and the ones already used."""
from sqlalchemy import text

from app.extensions import db


def parse_tags(raw: str) -> list[str]:
    """Comma-separated tags, trimmed, without repeats (case-insensitive), in the order given."""
    tags, seen = [], set()
    for tag in (t.strip() for t in (raw or "").split(",")):
        if tag and tag.casefold() not in seen:
            seen.add(tag.casefold())
            tags.append(tag)
    return tags


def all_tags() -> list[str]:
    """Every tag already used, to pick from (most used first, then alphabetical)."""
    rows = db.session.execute(text(
        "SELECT tag, count(*) FROM (SELECT unnest(tags) AS tag FROM transactions) t "
        "GROUP BY tag ORDER BY count(*) DESC, lower(tag)")).all()
    return [tag for tag, _count in rows]
