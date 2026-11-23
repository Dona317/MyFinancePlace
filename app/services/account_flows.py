"""
The flows between the accounts (F105): a graph of the money of a period — each account a node, «Esterno» the world
outside (incomes come from it, expenses go to it), «Senza conto» the movements on no account. An edge is the total of
one kind of movement between two nodes: the transfers from an account to another, the incomes into an account, the
expenses out of it. Each node and edge carries the register's filter that lists exactly its movements.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from flask_babel import gettext as _
from sqlalchemy import and_, case, func, or_

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.services.totals import analysed

OUTSIDE, NOWHERE = "outside", "none"
INVESTED = "invested"  # 23 Nov 2026: the securities — purchases go there, sales come from there
SIZE = func.abs(func.coalesce(Transaction.amount_base, Transaction.amount))


def _node_id(account_id: int | None) -> str:
    return f"a{account_id}" if account_id else NOWHERE


GIROCONTO = "Giroconto"  # the category of a transfer read from a bank statement


def flows(start: date, end: date) -> dict:
    """{"nodes": [{id, label, kind, value, filter}], "edges": [{source, target, kind, value, count, filter}]} of the
    movements in [start, end); `value` in the base currency, `filter` the register's query for them."""
    giro = (Transaction.category == GIROCONTO)
    # a trade of a security or its commission: an investment, drawn to (or from) the «Investimenti» node
    trade = and_(Transaction.holding_id.isnot(None), Transaction.units.isnot(None))
    invest = case((trade, "trade"), (Transaction.fee_for_id.isnot(None), "fee"), else_="")
    rows = (db.session.query(Transaction.type, Transaction.account_id, Transaction.counter_account_id,
                             func.sum(SIZE), func.count(Transaction.id), func.coalesce(giro, False), invest)
            .filter(Transaction.date >= start, Transaction.date < end,
                    Transaction.type.in_(("income", "expense", "transfer")),
                    # the excluded categories (Riconciliazione…) and the reversals are left out of incomes and
                    # expenses; the transfers always count — «Giroconto» is excluded from the analyses, not from here
                    or_(Transaction.type == "transfer", giro, Transaction.fee_for_id.isnot(None), analysed()))
            .group_by(Transaction.type, Transaction.account_id, Transaction.counter_account_id,
                      func.coalesce(giro, False), invest).all())
    edges: dict[tuple, dict] = {}
    through: dict[str, float] = defaultdict(float)
    for kind, account_id, counter_id, total, count, giroconto, investment in rows:
        value = float(total or 0)
        if not value:
            continue
        here = _node_id(account_id)
        if investment == "trade":  # bought: from the account to the securities; sold: back to the account
            buying = account_id is not None
            source, target = (here, INVESTED) if buying else (INVESTED, _node_id(counter_id))
            query = {"type": "transfer", "account": account_id or "none", "to": counter_id or "none"}
            kind = "investment"
        elif investment == "fee":  # the commission of a trade goes with the investment
            source, target, query, kind = here, INVESTED, {"type": "expense", "account": account_id or "none"}, "investment"
        elif giroconto and kind in ("income", "expense"):
            # a giroconto read from one bank only (its other half on an account not in the app, or not imported
            # yet): drawn as a transfer, in or out
            source, target = (OUTSIDE, here) if kind == "income" else (here, OUTSIDE)
            query = {"type": kind, "account": account_id or "none", "category": GIROCONTO}
            kind = "transfer"
        elif kind == "income":
            source, target, query = OUTSIDE, here, {"type": "income", "account": account_id or "none"}
        elif kind == "expense":
            source, target, query = here, OUTSIDE, {"type": "expense", "account": account_id or "none"}
        else:  # a transfer: from its account to the counter account (or out, to an account that is not the user's)
            target = _node_id(counter_id) if counter_id else OUTSIDE
            source, query = here, {"type": "transfer", "account": account_id or "none", "to": counter_id or "none"}
        key = (source, target, kind)
        edge = edges.setdefault(key, {"source": source, "target": target, "kind": kind, "value": 0.0, "count": 0,
                                      "filter": query})
        edge["value"] += value
        edge["count"] += count
        through[source] += value
        through[target] += value
    accounts = {a.id: a for a in Account.query.all()}
    nodes = []
    for node_id in sorted(through, key=lambda n: -through[n]):
        if node_id == INVESTED:
            nodes.append({"id": INVESTED, "label": _("Investimenti"), "kind": INVESTED,
                          "value": round(through[node_id], 2), "filter": {}})
        elif node_id == OUTSIDE:
            nodes.append({"id": OUTSIDE, "label": _("Esterno"), "kind": OUTSIDE, "value": round(through[node_id], 2),
                          "filter": {}})
        elif node_id == NOWHERE:
            nodes.append({"id": NOWHERE, "label": _("Senza conto"), "kind": NOWHERE, "value": round(through[node_id], 2),
                          "filter": {"account": "none"}})
        else:
            account = accounts.get(int(node_id[1:]))
            if account is None:
                continue
            nodes.append({"id": node_id, "label": account.name, "kind": account.kind, "value": round(through[node_id], 2),
                          "filter": {"account": account.id}})
    shown = {n["id"] for n in nodes}
    return {"nodes": nodes,
            "edges": [{**e, "value": round(e["value"], 2)} for e in edges.values()
                      if e["source"] in shown and e["target"] in shown]}
