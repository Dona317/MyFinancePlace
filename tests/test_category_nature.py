"""F8: the nature of a category's spending — fixed every month, not monthly, variable."""
from datetime import date
from decimal import Decimal

from app.models.category import Category
from app.models.transaction import TransactionSplit
from app.services import analytics, categories
from tests.conftest import make_tx


def _nature(name):
    return Category.query.filter_by(name=name).one().nature


def test_defaults_are_seeded_with_their_nature(db):
    categories.ensure_defaults()
    assert _nature("Casa") == "fixed" and _nature("Bollette") == "fixed"
    assert _nature("Tasse e imposte") == "periodic" and _nature("Assicurazioni") == "periodic"
    assert _nature("Alimentari") is None and _nature("Stipendio") is None
    assert _nature("Luce") == "fixed" and _nature("Manutenzione") == "periodic"  # subcategories
    assert categories.default_nature("Casa", "income") is None


def test_a_subcategory_without_its_own_takes_the_main_one(db):
    categories.ensure_defaults()
    categories.set_parent(sub := Category(name="Box auto", kind="expense"), "Casa")
    db.session.add(sub)
    db.session.commit()
    natures = categories.natures()
    assert natures["Box auto"] == "fixed" and natures["Alimentari"] == "variable" and natures["Manutenzione"] == "periodic"


def test_settings_save_the_nature(client, db):
    categories.ensure_defaults()
    client.post("/settings/categories/save", data={"name": "Palestra", "kind": "expense", "nature": "periodic"})
    assert _nature("Palestra") == "periodic"
    client.post("/settings/categories/save", data={"old_name": "Casa", "name": "Casa", "kind": "expense", "nature": ""})
    assert _nature("Casa") is None
    client.post("/settings/categories/save", data={"old_name": "Svago", "name": "Svago", "kind": "expense", "nature": "boh"})
    assert _nature("Svago") is None
    html = client.get("/settings/categories").get_data(as_text=True)
    assert 'name="nature"' in html and "Non mensile" in html


def test_nature_split_counts_the_parts_of_a_split_transaction(app, db):
    categories.ensure_defaults()
    june = date(2026, 6, 10)
    tx = make_tx(date=june, amount=100, category="Casa")
    tx.splits = [TransactionSplit(category="Casa", amount=Decimal(60)), TransactionSplit(category="Alimentari", amount=Decimal(40))]
    db.session.add_all([tx, make_tx(date=june, amount=50, category="Tasse e imposte"),
                        make_tx(date=june, amount=10, category=None), make_tx(date=june, amount=999, type="income", category="Stipendio")])
    db.session.commit()
    with app.test_request_context():
        split = analytics.nature_split(date(2026, 6, 1), date(2026, 7, 1))
    assert split["amounts"] == {"fixed": 60.0, "periodic": 50.0, "variable": 50.0} and split["total"] == 160.0
    assert [p["share"] for p in split["parts"]] == [37.5, 31.2, 31.2]


def test_pages_show_the_nature(client, db):
    categories.ensure_defaults()
    db.session.add_all([make_tx(date=date(2026, 3, 5), amount=800, category="Affitto"),
                        make_tx(date=date(2026, 3, 9), amount=200, category="Alimentari")])
    db.session.commit()
    html = client.get("/lifestyle/?year=2026").get_data(as_text=True)
    assert "Natura delle spese" in html and "nature-fixed" in html and "Comprimibile" in html
    summary = client.get("/reports/summary?year=2026").get_data(as_text=True)
    assert 'class="nature-dot nature-fixed summary-nature"' in summary
    assert "Nessuna spesa registrata" in client.get("/lifestyle/?year=2025").get_data(as_text=True)
