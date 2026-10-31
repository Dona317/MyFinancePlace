"""
Clusters: the group above a category, to read the spending model on two levels (cluster → category):
Necessità, Scelte e svago, Risparmio e investimenti.

A transaction's cluster comes from, in order: the cluster the user set on it; a memory rule (the user chose a
cluster for a similar counterparty or description before); the deterministic rule (a discretionary category
is «Scelte e svago», a savings/investment category is «Risparmio», anything else «Necessità»). Income and
transfers have no cluster. Only expenses count in the spending model.
"""
import re

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.cluster import ClusterRule
from app.models.transaction import Transaction
from app.services import request_cache
from app.services.categories import all_categories
from app.services.i18n import N_, tr
from app.services.parsing import normalize

NECESSARY, LIFESTYLE, SAVING = "necessary", "lifestyle", "saving"
CLUSTERS = {NECESSARY: N_("Necessità"), LIFESTYLE: N_("Scelte e svago"), SAVING: N_("Risparmio e investimenti")}
MIN_KEYWORD = 3  # as for the category rules: shorter words would match too much
SAVING_WORDS = ("invest", "risparm", "pension", "titoli", "etf", "fondi")


def label(cluster: str | None) -> str:
    return tr(CLUSTERS[cluster]) if cluster in CLUSTERS else ""


def _clean(text: str | None) -> str:
    return normalize(text)


def _compiled() -> list[tuple[ClusterRule, re.Pattern]]:
    """The memory rules as patterns, longest (most specific) first; loaded once per request."""
    store = request_cache.cache()
    if "cluster_rules" not in store:
        rules = ClusterRule.query.all()
        rules.sort(key=lambda r: (r.source != "manual", -len(r.keyword)))
        store["cluster_rules"] = [(r, re.compile(r"\b" + re.escape(r.keyword) + r"\b")) for r in rules]
    return store["cluster_rules"]


def forget_cache() -> None:
    request_cache.cache().pop("cluster_rules", None)


def _from_category(category: str | None) -> str:
    """The deterministic rule: discretionary categories are lifestyle, savings ones saving, the rest necessary."""
    if not category:
        return NECESSARY
    found = next((c for c in all_categories() if c.name == category), None)
    if found and found.discretionary:
        return LIFESTYLE
    name = _clean(category)
    if any(word in name for word in SAVING_WORDS):
        return SAVING
    return NECESSARY


def suggest(tx: Transaction) -> str | None:
    """The cluster a transaction should have when the user has not set one; None for income and transfers."""
    if tx.type != "expense":
        return None
    text = f" {_clean(' '.join(t for t in (tx.description, tx.counterparty, tx.bank_description) if t))} "
    try:
        for rule, pattern in _compiled():
            if pattern.search(text):
                return rule.cluster
    except SQLAlchemyError:
        db.session.rollback()
    return _from_category(tx.category)


def resolve(tx: Transaction) -> str | None:
    """Fill the cluster of a transaction that has none, from the rules; a cluster already set stays."""
    if tx.cluster in CLUSTERS and tx.type == "expense":
        return tx.cluster
    tx.cluster = suggest(tx)
    return tx.cluster


def learn(tx: Transaction) -> ClusterRule | None:
    """Remember the cluster the user chose for this counterparty (or description), for the similar ones later."""
    if tx.cluster not in CLUSTERS or tx.type != "expense":
        return None
    keyword = _clean(tx.counterparty or tx.description)
    if len(keyword) < MIN_KEYWORD:
        return None
    rule = ClusterRule.query.filter_by(keyword=keyword).first()
    if rule is None:
        rule = ClusterRule(keyword=keyword, cluster=tx.cluster, source="learned")
        db.session.add(rule)
    else:
        rule.cluster = tx.cluster
    db.session.commit()
    forget_cache()
    return rule


def valid(cluster: str | None) -> bool:
    return cluster in CLUSTERS

