"""Transaction categories: the default list plus every category already used (e.g. by imports)."""
from app.extensions import db
from app.models.transaction import Transaction

DEFAULT_CATEGORIES = [
    "Casa", "Alimentari", "Trasporto", "Salute", "Svago", "Abbonamenti", "Stipendio",
    "Freelance", "Investimenti", "Rimborsi", "Commissioni", "Giroconto", "Altro",
]


def known_categories(*extra: str | None) -> list[str]:
    stored = {c for (c,) in db.session.query(Transaction.category).filter(Transaction.category.isnot(None)).distinct()}
    return sorted(set(DEFAULT_CATEGORIES) | stored | {e for e in extra if e}, key=str.casefold)
