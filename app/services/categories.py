"""
Transaction categories, in one place: the table `categories` (seeded with the defaults the first time),
plus any category already used by transactions (e.g. from an import). Renaming or merging a category
updates everything that refers to it.
"""
from sqlalchemy import func
from sqlalchemy.orm import aliased

from app.extensions import db
from app.models.budget import Budget
from app.models.category import Category, CategoryRule
from app.models.transaction import Transaction, TransactionSplit
from app.models.wealth import Document
from app.services import request_cache, settings_store
from app.services.i18n import _l
from flask_babel import gettext as _

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

# A few subcategories to start with (added once, removable): main category → [(name, what it covers)]
SUBCATEGORY_DEFAULTS = {
    "Casa": [("Affitto", "canone di affitto"), ("Mutuo", "rata del mutuo casa"),
             ("Condominio", "spese condominiali"), ("Manutenzione", "riparazioni, idraulico, elettricista")],
    "Bollette": [("Luce", "energia elettrica"), ("Gas", "gas e riscaldamento"), ("Acqua", "servizio idrico"),
                 ("Internet e telefono", "fibra, ADSL, cellulare")],
    "Trasporto": [("Carburante", "benzina, gasolio, ricariche auto elettrica"),
                  ("Mezzi pubblici", "treni, metro, bus, abbonamenti"), ("Taxi", "taxi, NCC, car sharing"),
                  ("Pedaggi e parcheggi", "autostrade, Telepass, parcheggi")],
    "Ristoranti": [("Bar e caffè", "bar, caffè, colazioni"), ("Delivery", "Glovo, Deliveroo, Just Eat")],
    "Salute": [("Farmacia", "medicinali, parafarmacia"), ("Visite mediche", "visite, esami, dentista, ticket")],
    "Abbonamenti": [("Streaming", "Netflix, Spotify, Disney+, DAZN"), ("Software", "app, cloud, programmi")],
}
SEEDED_V3_SETTING = "categories.seeded_v3"

# The owner's own list (ROADMAP.md, "Categorie di base"): added once, skipping any already there under the same
# or almost the same name (Ristorante ~ Ristoranti, Trasporti ~ Trasporto). (name, kind, hint, discretionary)
PERSONAL_DEFAULTS = [
    ("Lavoro ISolutions", "income", "stipendio e compensi da ISolutions", False),
    ("Lavoro lezioni private", "income", "lezioni private, ripetizioni", False),
    ("Vendita tra privati", "income", "vendite di oggetti usati (Vinted, Subito…)", False),
    ("Regali", "income", "regali e contributi ricevuti", False),
    ("Lavoro da freelancer", "income", "compensi e fatture da lavoro autonomo", False),
    ("Trovati", "income", "soldi trovati, entrate occasionali", False),
    ("Altro", "both", "quando nessuna categoria è adatta", False),
    ("Salute", "expense", "farmacia, visite mediche, dentista", False),
    ("Ristorante", "expense", "ristoranti, pizzerie, cene fuori", True),
    ("Piccole consumazioni", "expense", "caffè, bar, snack, distributori", True),
    ("Spesa", "expense", "supermercato e alimentari", False),
    ("Cultura", "expense", "libri, musei, mostre, teatro, corsi", True),
    ("Shopping", "expense", "vestiti, cosmetici, accessori", True),
    ("Trasporti", "expense", "mezzi pubblici, treni, carburante, parcheggi", False),
    ("Giochi / svago", "expense", "giochi, videogiochi, uscite, tempo libero", True),
    ("Viaggi", "expense", "voli, hotel, vacanze", True),
    ("Gift", "expense", "regali fatti ad altri", True),
    ("Calcetto", "expense", "campo, quote, attrezzatura", True),
    ("Abbonamenti", "expense", "streaming, musica, software", True),
    ("Elettronica", "expense", "computer, telefoni, accessori elettronici", True),
    ("Macchina", "expense", "assicurazione, bollo, manutenzione, tagliando dell'auto", False),
    ("Palestra", "expense", "abbonamento e corsi in palestra", True),
]
SEEDED_PERSONAL_SETTING = "categories.seeded_personal"

# How the spending of a category recurs (F8): a fixed cost every month, a cost that comes a few times a year,
# or variable spending — the part that can be cut. Unlisted categories are variable.
NATURES = {"fixed": _l("Fissa"), "periodic": _l("Non mensile"), "variable": _l("Variabile")}
NATURE_DEFAULTS = {
    **dict.fromkeys(("Casa", "Affitto", "Mutuo", "Condominio", "Bollette", "Luce", "Gas", "Acqua", "Internet e telefono",
                     "Prestiti", "Abbonamenti", "Streaming", "Software", "Palestra", "Commissioni"), "fixed"),
    **dict.fromkeys(("Manutenzione", "Auto", "Macchina", "Assicurazioni", "Tasse e imposte", "Istruzione", "Viaggi",
                     "Regali e donazioni", "Gift"), "periodic"),
}


def default_nature(name: str, kind: str) -> str | None:
    return None if kind == "income" else NATURE_DEFAULTS.get(name)


def _stem(name: str) -> str:
    """ "Ristoranti" and "Ristorante", "Trasporto" and "Trasporti" are the same category."""
    word = " ".join(name.casefold().split())
    return word[:-1] if len(word) > 4 and word[-1] in "aeio" else word
SEPARATOR = " › "  # how a subcategory is shown: "Bollette › Luce"


def ensure_defaults() -> None:
    """
    Create the default categories once; after that the list is the user's (deleted ones stay deleted).
    A database seeded with the first, shorter list gets the categories added later, once.
    """
    if not settings_store.get(SEEDED_V2_SETTING):
        _seed_v2()
    if not settings_store.get(SEEDED_V3_SETTING):
        _seed_subcategories()
    if not settings_store.get(SEEDED_PERSONAL_SETTING):
        _seed_personal()


def _seed_personal() -> None:
    """The owner's list, once; names already there (or nearly the same) are not duplicated."""
    rows = Category.query.all()
    known = {_stem(c.name) for c in rows}
    position = max((c.position for c in rows), default=-1) + 1
    for name, kind, hint, discretionary in PERSONAL_DEFAULTS:
        if _stem(name) in known:
            continue
        db.session.add(Category(name=name, kind=kind, hint=hint, discretionary=discretionary, position=position,
                                nature=default_nature(name, kind)))
        known.add(_stem(name))
        position += 1
    settings_store.set(SEEDED_PERSONAL_SETTING, "1")  # commits the categories too
    forget()


def _seed_v2() -> None:
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
                                nature=default_nature(name, kind), position=index if first_time else position))
        position += 1
    settings_store.set(SEEDED_SETTING, "1")
    settings_store.set(SEEDED_V2_SETTING, "1")  # commits the categories too


def _seed_subcategories() -> None:
    """The starting subcategories, once, under main categories that still exist (renamed or deleted ones are skipped)."""
    rows = {c.name: c for c in Category.query.all()}
    position = max((c.position for c in rows.values()), default=-1) + 1
    for parent_name, subcategories in SUBCATEGORY_DEFAULTS.items():
        parent = rows.get(parent_name)
        if parent is None or parent.parent_id is not None:
            continue
        for name, hint in subcategories:
            if name not in rows:
                db.session.add(Category(name=name, kind=parent.kind, hint=hint, parent_id=parent.id,
                                        discretionary=parent.discretionary, nature=NATURE_DEFAULTS.get(name),
                                        position=position))
                position += 1
    settings_store.set(SEEDED_V3_SETTING, "1")
    forget()


# ── Main categories and subcategories ──────────────────────────────────────────

def forget() -> None:
    request_cache.cache().pop("category_parents", None)


def parents() -> dict[str, str]:
    """{subcategory: its main category}, read once per request."""
    store = request_cache.cache()
    if "category_parents" not in store:
        parent = aliased(Category)
        rows = db.session.query(Category.name, parent.name).join(parent, Category.parent_id == parent.id).all()
        store["category_parents"] = dict(rows)
    return store["category_parents"]


def top(name: str | None) -> str | None:
    """The main category of `name` (itself when it is one)."""
    return parents().get(name, name) if name else name


def main_or(name: str | None, fallback: str) -> str:
    """The main category of `name`, or `fallback` when it has none (an uncategorized transaction)."""
    return top(name) or fallback


def label(name: str | None) -> str:
    """ "Bollette › Luce" for a subcategory, the name itself otherwise."""
    main = parents().get(name) if name else None
    return f"{main}{SEPARATOR}{name}" if main else (name or "")


def children(name: str) -> list[str]:
    return sorted((child for child, main in parents().items() if main == name), key=str.casefold)


def with_children(name: str) -> list[str]:
    """A category and its subcategories: what a filter or a budget on it covers."""
    return [name, *children(name)]


def grouped(names: list[str]) -> list[tuple[str, list[str]]]:
    """`names` as (main category, [its subcategories among `names`]), for grouped lists; a subcategory whose main
    category is not in `names` still appears under it."""
    links = parents()
    groups: dict[str, list[str]] = {}
    for name in sorted(names, key=str.casefold):
        main = links.get(name)
        if main:
            groups.setdefault(main, []).append(name)
        else:
            groups.setdefault(name, [])
    return sorted(groups.items(), key=lambda item: item[0].casefold())


def set_parent(category: Category, parent_name: str | None) -> None:
    """Make `category` a subcategory of `parent_name` (None: a main category). One level only."""
    if not parent_name:
        category.parent_id = None
        return
    parent = Category.query.filter_by(name=parent_name).first()
    if parent is None:
        raise ValueError(_("Categoria principale «%(name)s» inesistente.", name=parent_name))
    if parent.id == category.id:
        raise ValueError(_("Una categoria non può essere sottocategoria di sé stessa."))
    if parent.parent_id is not None:
        raise ValueError(_("«%(name)s» è già una sottocategoria: scegli una categoria principale.", name=parent_name))
    if category.id is not None and Category.query.filter_by(parent_id=category.id).first():
        raise ValueError(_("«%(name)s» ha delle sottocategorie: non può diventarlo a sua volta.", name=category.name))
    category.parent_id = parent.id


def all_categories() -> list[Category]:
    ensure_defaults()
    return Category.query.order_by(Category.position, func.lower(Category.name)).all()


def used_names() -> set[str]:
    names = {c for (c,) in db.session.query(Transaction.category).filter(Transaction.category.isnot(None)).distinct()}
    return names | {c for (c,) in db.session.query(TransactionSplit.category).filter(TransactionSplit.category.isnot(None)).distinct()}


def known_categories(*extra: str | None) -> list[str]:
    """Every category to offer in a list: the managed ones, those already used, and `extra`."""
    names = {c.name for c in all_categories()} | used_names() | {e for e in extra if e}
    return sorted(names, key=str.casefold)


def hints() -> dict[str, str]:
    return {c.name: c.hint for c in all_categories() if c.hint}


def discretionary() -> set[str]:
    return {c.name for c in all_categories() if c.discretionary}


def natures() -> dict[str, str]:
    """{category: "fixed" | "periodic" | "variable"}; a subcategory without its own takes its main category's."""
    rows = all_categories()
    own = {c.id: c.nature for c in rows}
    return {c.name: c.nature or own.get(c.parent_id) or "variable" for c in rows}


def usage() -> dict[str, int]:
    """How many transactions use each category (a split transaction counts for each of its categories)."""
    from app.services.totals import LINE_CATEGORY, lines_query

    rows = (lines_query(LINE_CATEGORY, func.count(func.distinct(Transaction.id)))
            .filter(LINE_CATEGORY.isnot(None)).group_by(LINE_CATEGORY))
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
    if merged and source is not None:  # the merged category's subcategories go under the target (if it can have any)
        Category.query.filter_by(parent_id=source.id).update(
            {"parent_id": target.id if target.parent_id is None else None}, synchronize_session=False)
    Transaction.query.filter_by(category=old).update({"category": new}, synchronize_session=False)
    TransactionSplit.query.filter_by(category=old).update({"category": new}, synchronize_session=False)
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
    forget()
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
    TransactionSplit.query.filter_by(category=name).update({"category": replacement or None}, synchronize_session=False)
    Document.query.filter_by(category=name).update({"category": replacement or None}, synchronize_session=False)
    CategoryRule.query.filter_by(category=name).delete(synchronize_session=False)
    Budget.query.filter_by(category=name).delete(synchronize_session=False)
    category = Category.query.filter_by(name=name).first()
    if category is not None:  # its subcategories become main categories
        Category.query.filter_by(parent_id=category.id).update({"parent_id": None}, synchronize_session=False)
        db.session.delete(category)
    db.session.commit()
    forget()
    return moved


def expense_categories() -> list[str]:
    """Categories that can have a spending budget."""
    return [c.name for c in all_categories() if c.kind in ("expense", "both")]
