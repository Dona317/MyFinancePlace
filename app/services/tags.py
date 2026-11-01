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


def usage() -> list[tuple[str, int]]:
    """(tag, how many transactions have it), most used first."""
    rows = db.session.execute(text(
        "SELECT tag, count(*) FROM (SELECT unnest(tags) AS tag FROM transactions) t "
        "GROUP BY tag ORDER BY count(*) DESC, lower(tag)")).all()
    return [(tag, count) for tag, count in rows]


def rename(old: str, new: str) -> int:
    """Rename a tag on every transaction; a transaction that already has `new` keeps it once (the two merge).
    Returns how many transactions changed."""
    new = " ".join((new or "").replace(",", " ").split())
    if not new or new == old:
        return 0
    changed = db.session.execute(text(
        "UPDATE transactions SET tags = (SELECT array_agg(t ORDER BY i) FROM ("
        "  SELECT DISTINCT ON (lower(t)) t, i FROM unnest(array_replace(tags, :old, :new)) WITH ORDINALITY AS u(t, i)"
        "  ORDER BY lower(t), i) d) WHERE :old = ANY(tags)"), {"old": old, "new": new}).rowcount
    db.session.commit()
    return changed


def delete(tag: str) -> int:
    """Take a tag off every transaction. Returns how many."""
    changed = db.session.execute(text(
        "UPDATE transactions SET tags = array_remove(tags, :tag) WHERE :tag = ANY(tags)"), {"tag": tag}).rowcount
    db.session.commit()
    return changed


def all_tags() -> list[str]:
    """Every tag already used, to pick from (most used first, then alphabetical)."""
    rows = db.session.execute(text(
        "SELECT tag, count(*) FROM (SELECT unnest(tags) AS tag FROM transactions) t "
        "GROUP BY tag ORDER BY count(*) DESC, lower(tag)")).all()
    return [tag for tag, _count in rows]
