"""
Undo and redo for the transactions (F13): the last change — transactions added or deleted — can be taken back
for a while, and an undo can be redone.

One step each way, kept server-side (`app_settings`: a list of deleted rows does not fit in a session cookie).
Every step is the action that takes it back: "created" (ids to delete again) or "deleted" (the rows, splits
included, to put back with their own ids). Applying a step returns the opposite one, which becomes the redo of an
undo and the undo of a redo.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import insert

from app.extensions import db
from app.models.transaction import Transaction, TransactionSplit
from app.services import settings_store
from app.services.backup import _dump, _row

UNDO_KEY, REDO_KEY = "undo.last", "undo.redo"
KEEP_FOR = timedelta(minutes=30)  # an older step is not offered any more


def _snapshot(transactions: list[Transaction]) -> list[dict]:
    rows = []
    for tx in transactions:
        rows.append({
            "transaction": {c.name: _dump(getattr(tx, c.name)) for c in Transaction.__table__.columns},
            "splits": [{c.name: _dump(getattr(s, c.name)) for c in TransactionSplit.__table__.columns} for s in tx.splits],
        })
    return rows


def _store(key: str, step: dict | None) -> None:
    settings_store.set(key, json.dumps(step | {"at": datetime.now().isoformat(timespec="seconds")}) if step else None)


def _read(key: str) -> dict | None:
    try:
        step = json.loads(settings_store.get(key) or "null")
    except ValueError:
        return None
    if not isinstance(step, dict) or "kind" not in step:
        return None
    try:
        fresh = datetime.now() - datetime.fromisoformat(step.get("at", "")) <= KEEP_FOR
    except ValueError:
        fresh = False
    return step if fresh else None


def _label(transactions: list[Transaction]) -> str:
    return transactions[0].description if len(transactions) == 1 else str(len(transactions))


def remember_created(transactions: list[Transaction]) -> None:
    """Transactions just saved: undoing deletes them again."""
    _store(UNDO_KEY, {"kind": "created", "ids": [tx.id for tx in transactions], "label": _label(transactions),
                      "count": len(transactions)})
    _store(REDO_KEY, None)


def remember_deleted(transactions: list[Transaction]) -> None:
    """Call before deleting: undoing puts them back as they were."""
    _store(UNDO_KEY, {"kind": "deleted", "rows": _snapshot(transactions), "label": _label(transactions),
                      "count": len(transactions)})
    _store(REDO_KEY, None)


def _apply(step: dict) -> dict:
    """Take the step back; returns the opposite step."""
    if step["kind"] == "created":
        transactions = Transaction.query.filter(Transaction.id.in_(step["ids"])).all()
        opposite = {"kind": "deleted", "rows": _snapshot(transactions)}
        for tx in transactions:
            db.session.delete(tx)
    else:
        ids = []
        for row in step["rows"]:
            values = _row(Transaction, row["transaction"])
            if db.session.get(Transaction, values["id"]) is not None:  # the id was taken again meanwhile
                values.pop("id")
            new_id = db.session.execute(insert(Transaction).values(**values).returning(Transaction.id)).scalar_one()
            for split in row["splits"]:
                split = _row(TransactionSplit, split) | {"transaction_id": new_id}
                split.pop("id", None)
                db.session.execute(insert(TransactionSplit).values(**split))
            ids.append(new_id)
        opposite = {"kind": "created", "ids": ids}
    db.session.commit()
    return opposite | {"label": step.get("label"), "count": step.get("count", 0)}


def available() -> dict:
    """What the page can offer: {"undo": step or None, "redo": step or None}."""
    return {"undo": _read(UNDO_KEY), "redo": _read(REDO_KEY)}


def undo() -> dict | None:
    step = _read(UNDO_KEY)
    if step is None:
        return None
    _store(REDO_KEY, _apply(step))
    _store(UNDO_KEY, None)
    return step


def redo() -> dict | None:
    step = _read(REDO_KEY)
    if step is None:
        return None
    _store(UNDO_KEY, _apply(step))
    _store(REDO_KEY, None)
    return step
