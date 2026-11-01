"""F32: few broad categories, the details as the tags each one suggests; an archive of the earlier list is brought
to them with «Riordina», each transaction keeping its old category as a tag."""
from app.models.category import Category
from app.models.transaction import Transaction
from app.services import categories, settings_store
from app.services.bank_import.categorize import categorize
from tests.conftest import make_tx


def add(db, **values):
    tx = make_tx(**values)
    db.session.add(tx)
    db.session.commit()
    return tx


def test_a_new_archive_starts_with_the_broad_categories(db):
    names = [c.name for c in categories.all_categories()]
    assert names[:3] == ["Casa", "Alimentari", "Veicoli"] and "Imprevisti o altro" in names and "Abitazione" not in names
    assert "Leasing" in Category.query.filter_by(name="Veicoli").one().tags
    assert categories.broad() and categories.fallback() == "Imprevisti o altro"
    assert categories.suggested_tags()["Shopping"][0] == "Abbigliamento e scarpe"


def test_the_built_in_rules_follow_the_broad_categories(db):
    categories.ensure_defaults()
    assert categorize("Netflix abbonamento mensile") == "Abbonamenti"
    assert categorize("Ristorante Da Mario") in {"Alimentari", "Svago e intrattenimento"}
    assert categorize("Bonifico senza indizi") == "Imprevisti o altro"


def _earlier_archive(db):
    """An archive seeded before F32: the earlier list, not yet reordered."""
    db.session.add_all([Category(name="Svago", kind="expense"), Category(name="Leasing", kind="expense"),
                        Category(name="Investimenti", kind="both")])
    for key in (categories.SEEDED_SETTING, categories.SEEDED_V2_SETTING, categories.SEEDED_V3_SETTING,
                categories.SEEDED_PERSONAL_SETTING, categories.SEEDED_CAR_SETTING):
        settings_store.set(key, "1")


def test_reorder_moves_every_transaction_and_keeps_the_old_name_as_a_tag(client, db):
    _earlier_archive(db)
    leasing = add(db, description="Rata leasing", amount=-300, category="Leasing", tags=["auto"])
    fun = add(db, description="Cinema", amount=-12, category="Svago")
    etf = add(db, description="Acquisto ETF", amount=-500, category="Investimenti", type="expense")
    assert not categories.broad() and "Riordina" in client.get("/settings/categories").get_data(as_text=True)
    client.post("/settings/categories/reorder")
    assert (db.session.get(Transaction, leasing.id).category, db.session.get(Transaction, leasing.id).tags) == ("Veicoli", ["auto", "Leasing"])
    assert db.session.get(Transaction, fun.id).category == "Svago e intrattenimento"
    assert db.session.get(Transaction, etf.id).type == "transfer"  # an investment is not an expense
    assert not Category.query.filter_by(name="Leasing").first() and categories.broad()
    assert "Riordina" not in client.get("/settings/categories").get_data(as_text=True)


def test_the_suggested_tags_are_edited_with_the_category(client, db):
    categories.ensure_defaults()
    client.post("/settings/categories/save", data={"old_name": "Hobby", "name": "Hobby", "kind": "expense",
                                                   "tags": "Fotografia, modellismo, Fotografia"})
    assert Category.query.filter_by(name="Hobby").one().tags == ["Fotografia", "modellismo"]
    assert 'data-category-tags=' in client.get("/transactions/new").get_data(as_text=True)
