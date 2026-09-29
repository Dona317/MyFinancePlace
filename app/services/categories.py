"""
Transaction categories, in one place: the table `categories` (seeded with the defaults the first time),
plus any category already used by transactions (e.g. from an import). Renaming or merging a category
updates everything that refers to it.
"""
from sqlalchemy import func

from app.extensions import db
from app.models.category import Category, CategoryRule
from app.models.transaction import Transaction
from app.models.wealth import Document
from app.services import settings_store

KINDS = {"expense": "Uscite", "income": "Entrate", "both": "Entrambe"}
SEEDED_SETTING = "categories.seeded"
FALLBACK = "Altro"

# (name, kind, what it covers — also guides the AI classifier, discretionary spending?)
DEFAULTS = [
    ("Casa", "expense", "affitto, mutuo, condominio, bollette luce/gas/acqua, TARI, arredamento, manutenzione", False),
    ("Alimentari", "expense", "supermercati, alimentari, spesa (Esselunga, Coop, Conad, Lidl, Carrefour…)", False),
    ("Trasporto", "expense", "carburante, treni, mezzi pubblici, autostrade, taxi, parcheggi, voli", False),
    ("Salute", "expense", "farmacia, visite mediche, dentista, ticket sanitari", False),
    ("Svago", "expense", "ristoranti, bar, cinema, delivery, viaggi e tempo libero", True),
    ("Abbonamenti", "expense", "streaming, musica, telefonia, internet, software, palestra", True),
    ("Stipendio", "income", "stipendio, emolumenti, pensione", False),
    ("Freelance", "income", "compensi e fatture per lavoro autonomo", False),
    ("Investimenti", "both", "acquisto/vendita titoli, ETF, fondi, PAC, versamenti su conti investimento", False),
    ("Rimborsi", "income", "rimborsi, storni, resi", False),
    ("Commissioni", "expense", "commissioni bancarie, canoni, imposta di bollo, interessi passivi", False),
    ("Giroconto", "both", "trasferimenti tra conti propri, ricariche carte proprie", False),
    ("Altro", "both", "quando nessuna categoria è adatta", False),
]
DEFAULT_CATEGORIES = [name for name, *_ in DEFAULTS]


def ensure_defaults() -> None:
    """Create the default categories once; after that the list is the user's (deleted ones stay deleted)."""
    if settings_store.get(SEEDED_SETTING):
        return
    existing = {name for (name,) in db.session.query(Category.name)}
    for position, (name, kind, hint, discretionary) in enumerate(DEFAULTS):
        if name not in existing:
            db.session.add(Category(name=name, kind=kind, hint=hint, discretionary=discretionary, position=position))
    settings_store.set(SEEDED_SETTING, "1")  # commits the categories too


def all_categories() -> list[Category]:
    ensure_defaults()
    return Category.query.order_by(Category.position, func.lower(Category.name)).all()


def used_names() -> set[str]:
    return {c for (c,) in db.session.query(Transaction.category).filter(Transaction.category.isnot(None)).distinct()}


def known_categories(*extra: str | None) -> list[str]:
    """Every category to offer in a list: the managed ones, those already used, and `extra`."""
    names = {c.name for c in all_categories()} | used_names() | {e for e in extra if e}
    return sorted(names, key=str.casefold)


def hints() -> dict[str, str]:
    return {c.name: c.hint for c in all_categories() if c.hint}


def discretionary() -> set[str]:
    return {c.name for c in all_categories() if c.discretionary}


def usage() -> dict[str, int]:
    rows = db.session.query(Transaction.category, func.count()).filter(Transaction.category.isnot(None)).group_by(Transaction.category)
    return dict(rows.all())


def rename(old: str, new: str) -> bool:
    """Rename `old` to `new` everywhere; if `new` already exists the two are merged. True when merged."""
    new = new.strip()
    if not new or new == old:
        return False
    ensure_defaults()
    target = Category.query.filter_by(name=new).first()
    source = Category.query.filter_by(name=old).first()
    merged = target is not None
    Transaction.query.filter_by(category=old).update({"category": new}, synchronize_session=False)
    Document.query.filter_by(category=old).update({"category": new}, synchronize_session=False)
    CategoryRule.query.filter_by(category=old).update({"category": new}, synchronize_session=False)
    if source is not None:
        if merged:
            db.session.delete(source)
        else:
            source.name = new
    elif not merged:
        db.session.add(Category(name=new, position=len(DEFAULTS)))
    db.session.commit()
    return merged


def delete(name: str, replacement: str | None) -> int:
    """Remove a category; its transactions move to `replacement` (or become uncategorized). Returns how many."""
    ensure_defaults()
    moved = Transaction.query.filter_by(category=name).update({"category": replacement or None}, synchronize_session=False)
    Document.query.filter_by(category=name).update({"category": replacement or None}, synchronize_session=False)
    CategoryRule.query.filter_by(category=name).delete(synchronize_session=False)
    Category.query.filter_by(name=name).delete(synchronize_session=False)
    db.session.commit()
    return moved
