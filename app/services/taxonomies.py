"""
Classifications of the user's own for the holdings (F22): a name, its categories, and for each holding the category
it is in — or, when the classification allows it, how it is split among several (percentages adding up to at most 100;
the rest is «Non indicato»). Each one gets its exposure chart in Portafoglio → Composizione, next to region and sector.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from flask_babel import gettext as _

from app.extensions import db
from app.models.taxonomy import HoldingCategory, Taxonomy, TaxonomyCategory
from app.models.wealth import Holding
from app.services.composition import UNSET

MAX_NAME = 80


def _name(text: str | None, what: str) -> str:
    name = " ".join((text or "").split())[:MAX_NAME]
    if not name:
        raise ValueError(_("Scrivi il nome %(what)s.", what=what))
    return name


def all_taxonomies() -> list[Taxonomy]:
    return Taxonomy.query.order_by(Taxonomy.position, Taxonomy.id).all()


def create(name: str, multiple: bool, category_names: str = "") -> Taxonomy:
    """A classification, with its first categories (one per line)."""
    name = _name(name, _("della classificazione"))
    if Taxonomy.query.filter(db.func.lower(Taxonomy.name) == name.lower()).first():
        raise ValueError(_("Esiste già una classificazione «%(name)s».", name=name))
    taxonomy = Taxonomy(name=name, multiple=multiple, position=Taxonomy.query.count())
    db.session.add(taxonomy)
    for line in (category_names or "").splitlines():
        if line.strip():
            add_category(taxonomy, line)
    return taxonomy


def update(taxonomy: Taxonomy, name: str, multiple: bool) -> None:
    name = _name(name, _("della classificazione"))
    other = Taxonomy.query.filter(db.func.lower(Taxonomy.name) == name.lower(), Taxonomy.id != taxonomy.id).first()
    if other is not None:
        raise ValueError(_("Esiste già una classificazione «%(name)s».", name=name))
    if taxonomy.multiple and not multiple:  # back to one category each: the biggest share wins
        for holding_id, weights in _weights(taxonomy).items():
            biggest = max(weights, key=weights.get)
            assign(db.session.get(Holding, holding_id), taxonomy, {biggest: Decimal(100)})
    taxonomy.name, taxonomy.multiple = name, multiple


def add_category(taxonomy: Taxonomy, name: str) -> TaxonomyCategory:
    name = _name(name, _("della categoria"))
    if any(c.name.lower() == name.lower() for c in taxonomy.categories):
        raise ValueError(_("«%(name)s» c'è già.", name=name))
    category = TaxonomyCategory(name=name, position=len(taxonomy.categories))
    taxonomy.categories.append(category)
    return category


def rename_category(category: TaxonomyCategory, name: str) -> None:
    name = _name(name, _("della categoria"))
    if any(c.name.lower() == name.lower() and c.id != category.id for c in category.taxonomy.categories):
        raise ValueError(_("«%(name)s» c'è già.", name=name))
    category.name = name


def _weights(taxonomy: Taxonomy) -> dict[int, dict[int, Decimal]]:
    """{holding id: {category id: weight}} in one classification."""
    ids = [c.id for c in taxonomy.categories]
    found = defaultdict(dict)
    if ids:
        for row in HoldingCategory.query.filter(HoldingCategory.category_id.in_(ids)):
            found[row.holding_id][row.category_id] = Decimal(row.weight)
    return found


def of_holding(holding: Holding) -> dict[int, dict[int, Decimal]]:
    """{taxonomy id: {category id: weight}} of a holding."""
    found = defaultdict(dict)
    rows = (db.session.query(HoldingCategory, TaxonomyCategory.taxonomy_id)
            .join(TaxonomyCategory, TaxonomyCategory.id == HoldingCategory.category_id)
            .filter(HoldingCategory.holding_id == holding.id))
    for row, taxonomy_id in rows:
        found[taxonomy_id][row.category_id] = Decimal(row.weight)
    return found


def assign(holding: Holding, taxonomy: Taxonomy, weights: dict[int, Decimal | None]) -> None:
    """Put a holding in the classification: {category id: percentage}; zero or empty removes it from a category."""
    own = {c.id for c in taxonomy.categories}
    clean = {cid: w for cid, w in weights.items() if cid in own and w}
    if any(w < 0 or w > 100 for w in clean.values()):
        raise ValueError(_("«%(name)s»: le percentuali vanno da 0 a 100.", name=taxonomy.name))
    if not taxonomy.multiple and len(clean) > 1:
        raise ValueError(_("«%(name)s»: un titolo sta in una sola categoria.", name=taxonomy.name))
    if not taxonomy.multiple:
        clean = {cid: Decimal(100) for cid in clean}
    if sum(clean.values(), Decimal(0)) > 100:
        raise ValueError(_("«%(name)s»: le percentuali superano 100.", name=taxonomy.name))
    HoldingCategory.query.filter(HoldingCategory.holding_id == holding.id,
                                 HoldingCategory.category_id.in_(own)).delete(synchronize_session=False)
    for cid, weight in clean.items():
        db.session.add(HoldingCategory(holding_id=holding.id, category_id=cid, weight=weight))


def exposure(taxonomy: Taxonomy, holdings: list[Holding]) -> list[tuple[str, float, float]]:
    """[(category, value, %)] of the holdings, biggest first; the part not classified is «Non indicato»."""
    weights, names = _weights(taxonomy), {c.id: c.name for c in taxonomy.categories}
    total = sum(h.value for h in holdings)
    sums = defaultdict(float)
    for h in holdings:
        given = weights.get(h.id, {})
        for cid, weight in given.items():
            sums[names[cid]] += h.value * float(weight) / 100
        rest = 100 - float(sum(given.values(), Decimal(0)))
        if rest > 0:
            sums[UNSET] += h.value * rest / 100
    return sorted(((name, round(value, 2), round(value / total * 100, 1) if total else 0.0)
                   for name, value in sums.items() if round(value, 2)), key=lambda row: -row[1])
