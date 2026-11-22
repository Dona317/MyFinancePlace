"""Income categories only for income, expense ones only for expenses, and a new category typed in the form."""
import re

from app.models.category import Category
from app.models.transaction import Transaction
from app.services import categories
from app.services.request_cache import cache


def test_kinds_say_what_each_category_is_for(db):
    db.session.add_all([Category(name="Paghetta", kind="income", position=900),
                        Category(name="Ombrelli", kind="expense", position=901)])
    db.session.commit()
    categories.forget()
    kinds = categories.kinds()
    assert kinds["Paghetta"] == "income" and kinds["Ombrelli"] == "expense"
    assert all(value in ("income", "expense", "both") for value in kinds.values())


def test_ensure_makes_a_typed_category_once_for_its_direction(db):
    assert categories.ensure("Regali ricevuti", "income")
    assert not categories.ensure("regali ricevuti", "income")  # already there, whatever the case
    assert not categories.ensure("  ", "expense") and not categories.ensure(None, "expense")
    assert categories.ensure("Spostamenti", "transfer")
    made = {c.name: c.kind for c in Category.query.filter(Category.name.in_(["Regali ricevuti", "Spostamenti"]))}
    assert made == {"Regali ricevuti": "income", "Spostamenti": "both"}
    assert "category_kinds" not in cache()


def test_the_form_marks_each_category_and_takes_a_new_one(client, db):
    page = client.get("/transactions/new").get_data(as_text=True)
    select = re.search(r'<select id="f-category"[^>]*>', page).group(0)
    assert "data-allow-new" in select
    assert re.search(r'<option value="[^"]+" data-kind="(income|expense|both)"', page)
    client.post("/transactions/new", data={"date": "2026-06-01", "amount": "-12", "type": "expense", "currency": "EUR",
                                           "description": "Ombrello", "category": "Ombrelli rotti"})
    assert Transaction.query.filter_by(description="Ombrello").one().category == "Ombrelli rotti"
    assert Category.query.filter_by(name="Ombrelli rotti").one().kind == "expense"
    assert '<option value="Ombrelli rotti" data-kind="expense"' in client.get("/transactions/new").get_data(as_text=True)
