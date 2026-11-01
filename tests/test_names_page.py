"""One page for the names of the register: categories (with the car ones), spending groups and tags. Renaming
any of them reaches every transaction, the past ones too."""
import pathlib
import re

from app.models.category import Category
from app.models.transaction import Transaction
from app.services import categories, clusters, tags
from tests.conftest import make_tx


def add(db, **values):
    tx = make_tx(**values)
    db.session.add(tx)
    db.session.commit()
    return tx


def test_the_car_categories_come_under_auto(db):
    categories.ensure_defaults()
    auto = Category.query.filter_by(name="Auto").one()
    for name in ("Assicurazione auto", "Benzina e petroli"):
        assert Category.query.filter_by(name=name).one().parent_id == auto.id


def test_the_car_categories_are_main_ones_without_a_car_category(db):
    categories._seed_car()
    assert Category.query.filter_by(name="Benzina e petroli").one().parent_id is None


def test_a_renamed_group_shows_its_new_name_everywhere(client, db):
    tx = add(db, description="Cena", category="Ristoranti", amount=40, cluster=clusters.LIFESTYLE)
    response = client.post("/settings/clusters/save", data={"name-lifestyle": "Ferrari SF400"})
    assert response.status_code == 302
    assert clusters.label(clusters.LIFESTYLE) == "Ferrari SF400"
    assert db.session.get(Transaction, tx.id).cluster == clusters.LIFESTYLE  # the transaction keeps its group
    assert "Ferrari SF400" in client.get("/transactions/").get_data(as_text=True)
    client.post("/settings/clusters/save", data={"name-lifestyle": ""})
    assert clusters.label(clusters.LIFESTYLE) == "Scelte e svago"  # empty: back to the default


def test_the_register_filters_by_group(client, db):
    add(db, description="Cena fuori", amount=40, cluster=clusters.LIFESTYLE)
    add(db, description="Affitto casa", amount=700, cluster=clusters.NECESSARY)
    page = client.get("/transactions/?cluster=lifestyle").get_data(as_text=True)
    assert "Cena fuori" in page and "Affitto casa" not in page


def test_renaming_a_tag_changes_every_transaction_and_merges(client, db):
    first = add(db, description="Pieno", amount=60, tags=["auto", "viaggio"])
    second = add(db, description="Gomme", amount=300, tags=["auto", "Ferrari"])
    response = client.post("/settings/tags/save", data={"old_name": "auto", "name": "Ferrari"})
    assert response.status_code == 302
    assert db.session.get(Transaction, first.id).tags == ["Ferrari", "viaggio"]
    assert db.session.get(Transaction, second.id).tags == ["Ferrari"]  # merged, once
    assert tags.rename("Ferrari", "  ") == 0


def test_deleting_a_tag_keeps_the_transactions(client, db):
    tx = add(db, description="Pieno", amount=60, tags=["auto", "viaggio"])
    client.post("/settings/tags/delete", data={"name": "auto"})
    assert db.session.get(Transaction, tx.id).tags == ["viaggio"]


def test_the_page_lists_categories_groups_and_tags(client, db):
    add(db, description="Pieno", amount=60, tags=["benzina"], cluster=clusters.NECESSARY)
    page = client.get("/settings/categories").get_data(as_text=True)
    assert "Gruppi di spesa" in page and "benzina" in page and "Benzina e petroli" in page
    assert dict(tags.usage()) == {"benzina": 1}


def test_every_info_tip_sits_inside_its_title():
    """An «i» placed after a closed title wraps to a line of its own: it goes inside the title, by its text."""
    for path in pathlib.Path("app/templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"(?<!\*)</(span|div|label|h\d)>\s*\{\{ info\(", text), path
