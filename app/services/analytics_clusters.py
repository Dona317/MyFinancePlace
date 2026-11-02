"""
The spending model on two levels: each cluster (Necessità, Scelte e svago, Risparmio e investimenti) with its
total and share, and under it the categories that make it up.
"""
from datetime import date

from app.models.transaction import Transaction
from app.services import clusters
from app.services.categories import UNCATEGORIZED


def cluster_breakdown(start: date, end: date) -> list[dict]:
    """Expenses of [start, end) grouped by cluster, biggest first; each cluster lists its categories, biggest first.
    A transaction without a cluster gets the one the rules give it."""
    groups: dict[str, dict] = {}
    for tx in Transaction.query.filter(Transaction.type == "expense",
                                       Transaction.date >= start, Transaction.date < end).all():
        key = tx.cluster if tx.cluster in clusters.CLUSTERS else clusters.suggest(tx)
        if key is None:
            continue
        group = groups.setdefault(key, {"cluster": key, "label": clusters.label(key), "amount": 0.0, "by": {}})
        amount = tx.magnitude
        group["amount"] += amount
        category = tx.category or UNCATEGORIZED
        group["by"][category] = group["by"].get(category, 0.0) + amount

    total = sum(group["amount"] for group in groups.values())
    rows = []
    for group in sorted(groups.values(), key=lambda g: -g["amount"]):
        categories = [
            {"category": name, "amount": amount, "share": round(amount / group["amount"] * 100, 1) if group["amount"] else 0.0}
            for name, amount in sorted(group["by"].items(), key=lambda item: -item[1])
        ]
        rows.append({
            "cluster": group["cluster"], "label": group["label"], "amount": group["amount"],
            "share": round(group["amount"] / total * 100, 1) if total else 0.0, "categories": categories,
        })
    return rows
