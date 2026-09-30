"""
Transaction categories, in one place: the table `categories` (seeded with the defaults the first time),
plus any category already used by transactions (e.g. from an import). Renaming or merging a category
updates everything that refers to it.
"""
from sqlalchemy import func

from app.extensions import db
from app.models.budget import Budget
from app.models.category import Category, CategoryRule
from app.models.transaction import Transaction
from app.models.wealth import Document
from app.services import settings_store
from app.services.i18n import _l

KINDS = {"expense": _l("Uscite"), "income": _l("Entrate"), "both": _l("Entrambe")}
SEEDED_SETTING = "categories.seeded"
FALLBACK = "Altro"

# (name, kind, what it covers — also guides the AI classifier, discretionary spending?)
DEFAULTS = [
    ("Casa", "expense", "affitto, mutuo, condominio, TARI, arredamento, manutenzione", False),
    ("Bollette", "expense", "luce, gas, acqua, internet, telefono (Enel, A2A, Hera, TIM, Fastweb, Iliad…)", False),
    ("Alimentari", "expense", "supermercati, alimentari, spesa (Esselunga, Coop, Conad, Lidl, Carrefour…)", False),
    ("Ristoranti", "expense", "ristoranti, pizzerie, bar, caffè, delivery (Glovo, Deliveroo, Just Eat)", True),
    ("Trasporto", "expense", "carburante, treni, mezzi pubblici, autostrade, taxi, parcheggi", False),
    ("Auto", "expense", "manutenzione, tagliando, gomme, bollo, revisione, lavaggio", False),
    ("Salute", "expense", "farmacia, visite mediche, dentista, ticket sanitari, ottico", False),
    ("Cura personale", "expense", "parrucchiere, estetista, cosmetici, palestra", True),
    ("Istruzione", "expense", "scuola, università, corsi, libri di testo", False),
    ("Figli", "expense", "asilo, baby sitter, abbigliamento e attività dei figli", False),
    ("Animali", "expense", "veterinario, cibo e accessori per animali", False),
    ("Shopping", "expense", "abbigliamento, elettronica, casa e oggetti (Amazon, Zalando, IKEA…)", True),
    ("Svago", "expense", "cinema, concerti, teatro, hobby, libri, giochi, tempo libero", True),
    ("Viaggi", "expense", "voli, hotel, case vacanza, noleggi (Booking, Airbnb, Ryanair…)", True),
    ("Abbonamenti", "expense", "streaming, musica, software, giornali (Netflix, Spotify, Disney+…)", True),
    ("Assicurazioni", "expense", "premi di polizze auto, casa, vita, salute", False),
    ("Tasse e imposte", "expense", "F24, IRPEF, IMU, bollo, multe, tributi", False),
    ("Prestiti", "expense", "rate di mutui, prestiti e finanziamenti", False),
    ("Regali e donazioni", "expense", "regali, beneficenza, donazioni", True),
    ("Commissioni", "expense", "commissioni bancarie, canoni, imposta di bollo, interessi passivi", False),
    ("Stipendio", "income", "stipendio, emolumenti, tredicesima, quattordicesima", False),
    ("Pensione", "income", "pensione INPS o di altri enti", False),
    ("Freelance", "income", "compensi e fatture per lavoro autonomo", False),
    ("Bonus e premi", "income", "bonus aziendali, premi di produzione, welfare", False),
    ("Dividendi e cedole", "income", "dividendi di azioni ed ETF, cedole di obbligazioni", False),
    ("Interessi", "income", "interessi attivi di conti deposito e conti correnti", False),
    ("Affitti percepiti", "income", "canoni di affitto incassati", False),
    ("Vendite", "income", "vendita di oggetti usati, auto, beni (Vinted, Subito…)", False),
    ("Regali ricevuti", "income", "regali e contributi ricevuti", False),
    ("Rimborsi", "income", "rimborsi, storni, resi", False),
    ("Investimenti", "both", "acquisto/vendita titoli, ETF, fondi, PAC, versamenti su conti investimento", False),
    ("Giroconto", "both", "trasferimenti tra conti propri, ricariche carte proprie", False),
    ("Altro", "both", "quando nessuna categoria è adatta", False),
]
FIRST_DEFAULTS = {"Casa", "Alimentari", "Trasporto", "Salute", "Svago", "Abbonamenti", "Stipendio", "Freelance",
                  "Investimenti", "Rimborsi", "Commissioni", "Giroconto", "Altro"}  # the list seeded before v2
# Descriptions of the first list that v2 narrowed, updated only if the user never changed them
OLD_HINTS = {
    "Casa": "affitto, mutuo, condominio, bollette luce/gas/acqua, TARI, arredamento, manutenzione",
    "Trasporto": "carburante, treni, mezzi pubblici, autostrade, taxi, parcheggi, voli",
    "Salute": "farmacia, visite mediche, dentista, ticket sanitari",
    "Svago": "ristoranti, bar, cinema, delivery, viaggi e tempo libero",
    "Abbonamenti": "streaming, musica, telefonia, internet, software, palestra",
    "Stipendio": "stipendio, emolumenti, pensione",
}
SEEDED_V2_SETTING = "categories.seeded_v2"
DEFAULT_CATEGORIES = [name for name, *_ in DEFAULTS]


def ensure_defaults() -> None:
    """
    Create the default categories once; after that the list is the user's (deleted ones stay deleted).
    A database seeded with the first, shorter list gets the categories added later, once.
    """
    if settings_store.get(SEEDED_V2_SETTING):
        return
    first_time = not settings_store.get(SEEDED_SETTING)
    rows = {c.name: c for c in Category.query.all()}
    position = max((c.position for c in rows.values()), default=-1) + 1
    for index, (name, kind, hint, discretionary) in enumerate(DEFAULTS):
        if name in rows:
            if rows[name].hint == OLD_HINTS.get(name):
                rows[name].hint = hint
            continue
        if not first_time and name in FIRST_DEFAULTS:
            continue  # the user deleted it: it stays deleted
        db.session.add(Category(name=name, kind=kind, hint=hint, discretionary=discretionary,
                                position=index if first_time else position))
        position += 1
    settings_store.set(SEEDED_SETTING, "1")
    settings_store.set(SEEDED_V2_SETTING, "1")  # commits the categories too


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
    _move_budgets(old, new)
    if source is not None:
        if merged:
            db.session.delete(source)
        else:
            source.name = new
    elif not merged:
        db.session.add(Category(name=new, position=len(DEFAULTS)))
    db.session.commit()
    return merged


def _move_budgets(old: str, new: str) -> None:
    """Budgets follow a renamed category; when merging, the target's own budget for the same month wins."""
    for budget in Budget.query.filter_by(category=old).all():
        clash = Budget.query.filter(Budget.category == new, Budget.month.is_(None) if budget.month is None
                                    else Budget.month == budget.month).first()
        if clash is not None:
            db.session.delete(budget)
        else:
            budget.category = new


def delete(name: str, replacement: str | None) -> int:
    """Remove a category; its transactions move to `replacement` (or become uncategorized). Returns how many."""
    ensure_defaults()
    moved = Transaction.query.filter_by(category=name).update({"category": replacement or None}, synchronize_session=False)
    Document.query.filter_by(category=name).update({"category": replacement or None}, synchronize_session=False)
    CategoryRule.query.filter_by(category=name).delete(synchronize_session=False)
    Budget.query.filter_by(category=name).delete(synchronize_session=False)
    Category.query.filter_by(name=name).delete(synchronize_session=False)
    db.session.commit()
    return moved


def expense_categories() -> list[str]:
    """Categories that can have a spending budget."""
    return [c.name for c in all_categories() if c.kind in ("expense", "both")]
