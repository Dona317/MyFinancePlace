"""Subcategories: a category can belong to a main category (Bollette → Luce); totals roll up where the overview matters."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.category import Category
from app.services import analytics, budgets, categories, reports, transfer
from tests.conftest import make_tx
from tests.test_ai_classification import items, ollama  # noqa: F401 - fixture

JUNE = date(2026, 6, 10)


def test_starting_subcategories_are_added_once(db):
    categories.ensure_defaults()
    assert categories.parents()["Luce"] == "Bollette" and categories.top("Luce") == "Bollette"
    assert categories.children("Bollette") == ["Acqua", "Gas", "Internet e telefono", "Luce"]
    assert categories.label("Luce") == "Bollette › Luce" and categories.label("Casa") == "Casa"
    categories.delete("Luce", None)
    categories.ensure_defaults()
    assert "Luce" not in {c.name for c in categories.all_categories()}  # deleted stays deleted


def test_one_level_only(db):
    categories.ensure_defaults()
    bollette = Category.query.filter_by(name="Bollette").one()
    luce = Category.query.filter_by(name="Luce").one()
    with pytest.raises(ValueError, match="già una sottocategoria"):
        categories.set_parent(Category.query.filter_by(name="Svago").one(), "Luce")
    with pytest.raises(ValueError, match="ha delle sottocategorie"):
        categories.set_parent(bollette, "Casa")
    with pytest.raises(ValueError, match="sé stessa"):
        categories.set_parent(bollette, "Bollette")
    with pytest.raises(ValueError, match="inesistente"):
        categories.set_parent(luce, "Nessuna")
    categories.set_parent(luce, None)
    assert luce.parent_id is None


def test_deleting_or_merging_a_main_category_keeps_its_subcategories(db):
    categories.ensure_defaults()
    categories.delete("Bollette", None)
    assert "Luce" not in categories.parents()  # now a main category
    categories.ensure_defaults()
    categories.rename("Ristoranti", "Svago")  # merged: its subcategories move under Svago
    assert categories.parents()["Delivery"] == "Svago"


def test_settings_page_sets_the_main_category(client, db):
    client.post("/settings/categories/save", data={"name": "Palestra", "kind": "expense", "parent": "Salute"})
    assert categories.parents()["Palestra"] == "Salute"
    html = client.get("/settings/categories").get_data(as_text=True)
    assert "Sottocategoria di" in html and 'class="subcategory-row"' in html
    page = client.post("/settings/categories/save", data={"name": "Salute", "old_name": "Salute", "kind": "expense",
                                                          "parent": "Casa"}, follow_redirects=True)
    assert "ha delle sottocategorie" in page.get_data(as_text=True)


def test_lists_filters_and_totals(client, db):
    categories.ensure_defaults()
    db.session.add_all([make_tx(date=JUNE, category="Luce", amount=60), make_tx(date=JUNE, category="Gas", amount=40),
                        make_tx(date=JUNE, category="Bollette", amount=10), make_tx(date=JUNE, category="Svago", amount=5)])
    db.session.commit()
    form = client.get("/transactions/new").get_data(as_text=True)
    assert '<optgroup label="Bollette">' in form and ">Bollette › Luce</option>" in form
    listing = client.get("/transactions/?category=Bollette").get_data(as_text=True)
    assert listing.count('class="bulk-select') == 3  # the main category and its subcategories
    assert '<span class="category-main">Bollette ›</span> Luce' in listing
    assert client.get("/transactions/?category=Luce").get_data(as_text=True).count('class="bulk-select') == 1
    # dashboard: one slice for the main category
    split = {i["category"]: i["amount"] for i in analytics.category_breakdown(date(2026, 1, 1), date(2027, 1, 1))}
    assert split == {"Bollette": 110.0, "Svago": 5.0}
    trend = analytics.monthly_category_trend(2026, top_n=1)
    assert trend["datasets"][0] == {"label": "Bollette", "data": [0.0] * 5 + [110.0] + [0.0] * 6}


def test_report_drills_into_subcategories(client, db):
    categories.ensure_defaults()
    db.session.add_all([make_tx(date=JUNE, category="Luce", amount=60), make_tx(date=JUNE, category="Gas", amount=40),
                        make_tx(date=JUNE, category="Svago", amount=5)])
    db.session.commit()
    query = reports.base_query(date(2026, 6, 1), date(2026, 7, 1))
    assert [i["category"] for i in reports.breakdown(query, "expense")] == ["Bollette", "Svago"]
    assert [i["category"] for i in reports.breakdown(query, "expense", within="Bollette")] == ["Luce", "Gas"]
    html = client.get("/reports/?period=custom&start=2026-06-01&end=2026-06-30&category=Bollette").get_data(as_text=True)
    legend = html.split('<ul class="report-legend">')[1].split("</ul>")[0]
    assert "Luce" in legend and "Gas" in legend and "Svago" not in legend
    child = client.get("/reports/?period=custom&start=2026-06-01&end=2026-06-30&category=Luce").get_data(as_text=True)
    assert "Bollette › Luce" in child and 'class="selected"' in child.split('<ul class="report-legend">')[1]


def test_budget_on_a_main_category_counts_its_subcategories(db):
    categories.ensure_defaults()
    budgets.save("Bollette", Decimal("100"), None)
    budgets.save("Luce", Decimal("50"), None)
    db.session.add_all([make_tx(date=JUNE, category="Luce", amount=60), make_tx(date=JUNE, category="Gas", amount=30)])
    db.session.commit()
    spent = {row["category"]: row["spent"] for row in budgets.status(date(2026, 6, 1), JUNE)}
    assert spent == {"Bollette": 90.0, "Luce": 60.0}


def test_export_has_the_main_category(db):
    categories.ensure_defaults()
    tx = make_tx(category="Luce")
    db.session.add(tx)
    db.session.commit()
    assert transfer.tx_to_dict(tx)["main_category"] == "Bollette"
    assert "main_category" in transfer.to_csv([tx]).splitlines()[0]


def test_ai_prompt_shows_the_hierarchy(ollama):  # noqa: F811
    categories.ensure_defaults()
    from app.services import ai_classification
    ai_classification.classify(items("ENEL ENERGIA bolletta luce"), ["Bollette", "Luce", "Gas"])
    prompt = ollama.calls[0]["messages"][1]["content"]
    assert "- Bollette › Luce: energia elettrica" in prompt
    enum = ollama.calls[0]["format"]["properties"]["items"]["items"]["properties"]["category"]["enum"]
    assert enum == ["Bollette", "Luce", "Gas", "Altro"]  # plain names: the answer is one name
    assert "Principale › Sottocategoria" in ollama.calls[0]["messages"][0]["content"]
