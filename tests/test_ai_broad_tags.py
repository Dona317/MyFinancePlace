"""
The AI classification with the broad categories (F32): the model picks a broad category and, as its detail, one of
the tags that category suggests; old category names are offered as the broad ones they went to.
"""
import json

import pytest

from app.models.transaction import Transaction
from app.services import ai_classification, categories, category_rules
from app.services.bank_import.build import build_transaction
from tests.conftest import make_tx
from tests.test_ai_classification import items, ollama  # noqa: F401 - fixture


@pytest.fixture()
def broad(db):
    categories._seed_broad()


def _reply(category, tag, counterparty="Enel"):
    return lambda movements: {"items": [{"id": m["id"], "category": category, "tag": tag,
                                         "counterparty": counterparty, "confidence": "alta"} for m in movements]}


def test_the_model_is_asked_for_a_tag_of_the_category(broad, ollama):  # noqa: F811
    ollama.override = _reply("Casa", "Bollette")
    result = ai_classification.classify(items("ENEL ENERGIA bolletta luce"), ["Casa", "Alimentari", "Bollette"])
    body = ollama.calls[0]
    schema = body["format"]["properties"]["items"]["items"]
    assert "tag" in schema["required"] and "Bollette" in schema["properties"]["tag"]["enum"]
    assert "" in schema["properties"]["tag"]["enum"]
    prompt = body["messages"][1]["content"]
    assert "[tag: Abitazione, Bollette" in prompt and "«tag»" in prompt
    # «Bollette», an old category, is offered as the broad «Casa» it went to: not as a category of its own
    assert "Bollette" not in body["format"]["properties"]["items"]["items"]["properties"]["category"]["enum"]
    assert result[1].tag == "Bollette" and result[1].to_dict()["tag"] == "Bollette"


def test_a_tag_of_another_category_is_dropped(broad, ollama):  # noqa: F811
    ollama.override = _reply("Alimentari", "Bollette")
    result = ai_classification.classify(items("ESSELUNGA"), ["Casa", "Alimentari"])
    assert result[1].category == "Alimentari" and result[1].tag == "" and "tag" not in result[1].to_dict()


def test_the_earlier_list_asks_no_tag(earlier_archive, ollama):  # noqa: F811
    ai_classification.classify(items("ESSELUNGA"), ["Alimentari"])
    schema = ollama.calls[0]["format"]["properties"]["items"]["items"]
    assert "tag" not in schema["properties"] and ai_classification.tags_for(["Casa"]) == {}


def test_old_rules_and_history_point_to_the_broad_category(broad, ollama, db):  # noqa: F811
    category_rules.save("enel", "Luce")
    db.session.add_all([make_tx(description=f"POS ESSELUNGA {n}", bank_description=f"POS ESSELUNGA {n}",
                                category="Spesa", amount=20) for n in range(3)])
    db.session.commit()
    ollama.override = _reply("Casa", "")
    result = ai_classification.classify(items("POS ESSELUNGA 9", "ENEL bolletta"), categories.known_categories())
    assert result[1].category == "Alimentari" and result[1].from_history
    assert "- enel → Casa" in ollama.calls[0]["messages"][1]["content"]


def test_the_classify_page_offers_and_saves_the_tag(broad, client, ollama, db):  # noqa: F811
    tx = make_tx(description="ENEL ENERGIA", bank_description="ENEL ENERGIA bolletta", category=None, amount=60)
    db.session.add(tx)
    db.session.commit()
    ollama.override = _reply("Casa", "Bollette")
    page = client.post("/transactions/classify", data={"ids": [str(tx.id)]}).get_data(as_text=True)
    assert f'name="tag-{tx.id}" value="Bollette"' in page and 'id="tag-options"' in page
    client.post("/transactions/classify/apply", data={"apply": [str(tx.id)], f"category-{tx.id}": "Casa",
                                                       f"counterparty-{tx.id}": "Enel", f"suggested-{tx.id}": "Casa",
                                                       f"tag-{tx.id}": "Bollette"})
    saved = db.session.get(Transaction, tx.id)
    assert saved.category == "Casa" and saved.tags[:2] == ["Enel", "Bollette"] and ai_classification.AI_TAG in saved.tags


def test_the_classify_page_without_tags_has_no_column(client, ollama, db):  # noqa: F811
    tx = make_tx(description="ESSELUNGA", bank_description="ESSELUNGA", category=None, amount=10)
    db.session.add(tx)
    db.session.commit()
    page = client.post("/transactions/classify", data={"ids": [str(tx.id)]}).get_data(as_text=True)
    assert 'name="tag-' not in page


def test_the_bank_import_keeps_the_ai_tag_with_the_category(broad):
    fields = {"date": "2026-11-02", "description": "ENEL", "amount": "60", "type": "expense", "category": "Casa",
              "counterparty": "Enel", "aicat": "1", "aitag": "Bollette"}
    tx = build_transaction({}, "fineco", fields)
    assert "Bollette" in tx.tags and ai_classification.AI_TAG in tx.tags
    # a category changed by hand drops the tag (the page sends it only with the AI's category)
    tx = build_transaction({}, "fineco", fields | {"aicat": "", "aitag": "Bollette"})
    assert "Bollette" not in tx.tags
    assert build_transaction({}, "fineco", fields | {"category": ""}).category == "Imprevisti o altro"


def test_the_bank_classify_answer_carries_the_tag(broad, client, ollama):  # noqa: F811
    ollama.override = _reply("Casa", "Bollette")
    response = client.post("/export/bank/classify", json={"rows": [{"index": 0, "text": "ENEL", "amount": -60}]})
    assert json.loads(response.data)["suggestions"]["0"]["tag"] == "Bollette"
