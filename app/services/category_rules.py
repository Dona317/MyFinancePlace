"""
The user's categorization rules: "a transaction whose description or counterparty contains <keyword>
goes to <category>". Written by hand (Settings → Regole) or learned when the user corrects a category.
They are checked before the built-in rules of the bank import (bank_import.CATEGORY_RULES).
"""
import re

from flask import g, has_app_context
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.category import CategoryRule
from app.models.transaction import Transaction
from app.services.parsing import normalize

MIN_KEYWORD = 3  # shorter words would match too much ("bar" is the shortest useful one)


def clean_keyword(keyword: str | None) -> str:
    return normalize(keyword)


def _compiled() -> list[tuple[CategoryRule, re.Pattern]]:
    """The rules as patterns, longest (most specific) first; loaded once per request."""
    if "category_rules" not in g:
        rules = CategoryRule.query.all()
        rules.sort(key=lambda r: (r.source != "manual", -len(r.keyword)))
        g.category_rules = [(r, re.compile(r"\b" + re.escape(r.keyword) + r"\b")) for r in rules]
    return g.category_rules


def forget_cache() -> None:
    g.pop("category_rules", None)


def match(*texts: str | None) -> str | None:
    """The category of the first user rule matching the texts; None (also outside the app, or on DB errors)."""
    if not has_app_context():
        return None
    text = f" {normalize(' '.join(t for t in texts if t))} "
    try:
        for rule, pattern in _compiled():
            if pattern.search(text):
                return rule.category
    except SQLAlchemyError:
        db.session.rollback()
    return None


def save(keyword: str, category: str, source: str = "manual") -> CategoryRule:
    """Create or update the rule for a keyword (a manual rule is never downgraded to learned)."""
    keyword = clean_keyword(keyword)
    if len(keyword) < MIN_KEYWORD:
        raise ValueError(f"Parola chiave: almeno {MIN_KEYWORD} caratteri.")
    if not category:
        raise ValueError("Categoria: scegline una.")
    rule = CategoryRule.query.filter_by(keyword=keyword).first()
    if rule is None:
        rule = CategoryRule(keyword=keyword, category=category, source=source, hits=0)
        db.session.add(rule)
    else:
        rule.category = category
        if source == "manual":
            rule.source = "manual"
    db.session.commit()
    forget_cache()
    return rule


def learn(counterparty: str | None, category: str | None) -> CategoryRule | None:
    """Remember the category chosen for a counterparty, so the next ones are categorized the same way."""
    if not counterparty or not category or len(clean_keyword(counterparty)) < MIN_KEYWORD:
        return None
    return save(counterparty, category, source="learned")


def apply(only_uncategorized: bool = True) -> int:
    """Categorize existing transactions with the rules (by default only those without a category or in "Altro")."""
    query = Transaction.query
    if only_uncategorized:
        query = query.filter((Transaction.category.is_(None)) | (Transaction.category == "Altro"))
    changed = 0
    hits: dict[int, int] = {}
    forget_cache()
    rules = _compiled()
    for tx in query.all():
        text = f" {normalize(' '.join(t for t in (tx.description, tx.counterparty, tx.bank_description) if t))} "
        for rule, pattern in rules:
            if pattern.search(text):
                if tx.category != rule.category:
                    tx.category = rule.category
                    changed += 1
                    hits[rule.id] = hits.get(rule.id, 0) + 1
                break
    for rule, _ in rules:
        rule.hits = (rule.hits or 0) + hits.get(rule.id, 0)
    db.session.commit()
    return changed


def examples(limit: int = 30) -> list[tuple[str, str]]:
    """(keyword, category) pairs chosen by the user, as hints for the AI classifier."""
    rules = CategoryRule.query.order_by(CategoryRule.hits.desc(), CategoryRule.id.desc()).limit(limit).all()
    return [(r.keyword, r.category) for r in rules]
