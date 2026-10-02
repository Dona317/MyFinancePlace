"""Categories managed in one place (Settings → Categorie) and categorization rules written or learned by the user."""
from app.models.category import Category, CategoryRule
from app.models.transaction import Transaction
from app.models.wealth import Document
from app.services import ai_classification, bank_import, categories, category_rules
from tests.conftest import make_tx


def test_defaults_are_created_once_and_deletions_stick(db):
    names = categories.known_categories()
    assert "Alimentari" in names and "Altro" in names
    categories.delete("Freelance", None)
    assert "Freelance" not in categories.known_categories()  # not recreated
    subcategories = sum(len(subs) for subs in categories.SUBCATEGORY_DEFAULTS.values())
    personal = 15  # the owner's 22, without the 7 already there (Altro, Salute, Ristorante~Ristoranti, …)
    assert Category.query.count() == len(categories.DEFAULTS) - 1 + subcategories + personal


def test_a_database_seeded_with_the_first_list_gets_the_new_categories_once(db):
    """Before v2 only the first 13 were created: the new ones are added, the ones the user deleted stay deleted."""
    from app.services import settings_store
    for name, kind, hint, discretionary in categories.DEFAULTS:
        if name in categories.FIRST_DEFAULTS and name != "Freelance":  # the user had deleted Freelance
            db.session.add(Category(name=name, kind=kind, hint=categories.OLD_HINTS.get(name, hint)))
    settings_store.set(categories.SEEDED_SETTING, "1")
    names = {c.name for c in categories.all_categories()}
    assert {"Bollette", "Ristoranti", "Pensione", "Dividendi e cedole", "Tasse e imposte"} <= names
    assert "Freelance" not in names
    assert "bollette" not in Category.query.filter_by(name="Casa").one().hint  # narrowed, it was never edited
    categories.delete("Bollette", None)
    assert "Bollette" not in {c.name for c in categories.all_categories()}  # seeded once only


def test_used_categories_are_offered_too(db):
    db.session.add(make_tx(category="Hobby modellismo"))
    db.session.commit()
    assert "Hobby modellismo" in categories.known_categories()


def test_rename_updates_everything_and_merge(client, db):
    db.session.add_all([make_tx(category="Svago"), make_tx(category="Svago"), make_tx(category="Casa")])
    db.session.add(Document(filename="a.pdf", stored_name="x" * 32, size=1, category="Svago"))
    db.session.commit()
    category_rules.save("cinema", "Svago")

    client.post("/settings/categories/save", data={"old_name": "Svago", "name": "Tempo libero", "kind": "expense"})
    assert Transaction.query.filter_by(category="Tempo libero").count() == 2
    assert Document.query.one().category == "Tempo libero"
    assert CategoryRule.query.one().category == "Tempo libero"
    assert Category.query.filter_by(name="Svago").count() == 0

    response = client.post("/settings/categories/save", data={"old_name": "Tempo libero", "name": "Casa", "kind": "expense"},
                           follow_redirects=True)
    assert "unita a «Casa»" in response.get_data(as_text=True)
    assert Transaction.query.filter_by(category="Casa").count() == 3
    assert Category.query.filter_by(name="Tempo libero").count() == 0


def test_add_and_delete_with_replacement(client, db):
    client.post("/settings/categories/save", data={"name": "Animali", "kind": "expense", "hint": "veterinario",
                                                   "discretionary": "on"})
    animali = Category.query.filter_by(name="Animali").one()
    assert animali.hint == "veterinario" and animali.discretionary
    db.session.add(make_tx(category="Animali"))
    db.session.commit()
    client.post("/settings/categories/delete", data={"name": "Animali", "replacement": "Altro"})
    assert Transaction.query.one().category == "Altro"
    assert "Animali" not in categories.known_categories()


def test_discretionary_share_follows_the_settings(client, db):
    db.session.add_all([make_tx(category="Casa", amount=100), make_tx(category="Svago", amount=100)])
    db.session.commit()
    from app.services import analytics
    assert analytics.lifestyle_report(2026)["discretionary_share"] == 50
    client.post("/settings/categories/save", data={"old_name": "Casa", "name": "Casa", "kind": "expense", "discretionary": "on"})
    assert analytics.lifestyle_report(2026)["discretionary_share"] == 100


def test_pages_render(client, db):
    db.session.add(make_tx(category="Da import"))
    db.session.commit()
    html = client.get("/settings/categories").get_data(as_text=True)
    assert "Alimentari" in html and "+ Da import" in html
    assert "Regole predefinite" in client.get("/settings/rules").get_data(as_text=True)


# ── Rules ──────────────────────────────────────────────────────────────────────

def test_user_rules_win_over_builtin_ones(db):
    assert bank_import.categorize("PAGAMENTO POS DECATHLON MILANO") == "Altro"
    assert bank_import.categorize("Esselunga via Roma") == "Alimentari"
    category_rules.save("Decathlon", "Sport")
    category_rules.save("esselunga via roma", "Casa")  # more specific than the built-in "esselunga"
    assert bank_import.categorize("PAGAMENTO POS DECATHLON MILANO") == "Sport"
    assert bank_import.categorize("Esselunga via Roma") == "Casa"


def test_rules_outside_the_app_fall_back_to_builtin():
    assert bank_import.categorize("Esselunga") == "Alimentari"


def test_rule_validation_and_apply(client, db):
    response = client.post("/settings/rules/save", data={"keyword": "ab", "category": "Svago"}, follow_redirects=True)
    assert "almeno 3 caratteri" in response.get_data(as_text=True)
    db.session.add_all([make_tx(description="Decathlon Milano", category=None),
                        make_tx(description="Decathlon Roma", category="Altro"),
                        make_tx(description="Decathlon regalo", category="Regali")])
    db.session.commit()
    response = client.post("/settings/rules/save", data={"keyword": "decathlon", "category": "Sport", "apply": "1"},
                           follow_redirects=True)
    assert "Ricategorizzate 2 transazioni" in response.get_data(as_text=True)
    assert sorted(t.category for t in Transaction.query.all()) == ["Regali", "Sport", "Sport"]
    assert CategoryRule.query.one().hits == 2


def test_correcting_a_category_teaches_a_rule(client, db):
    tx = make_tx(description="POS 1234 BOTTEGA VERDE", counterparty="Bottega Verde", category="Altro")
    db.session.add(tx)
    db.session.commit()
    client.post(f"/transactions/{tx.id}/edit", data={"date": "2026-06-01", "amount": "-10",
                                                     "description": "POS 1234 BOTTEGA VERDE", "tags": "Bottega Verde, cura",
                                                     "category": "Salute", "learn_rule": "1"})
    rule = CategoryRule.query.one()
    assert (rule.keyword, rule.category, rule.source) == ("bottega verde", "Salute", "learned")
    assert bank_import.categorize("PAGAMENTO BOTTEGA VERDE TORINO") == "Salute"
    # without the tick nothing is learned
    client.post(f"/transactions/{tx.id}/edit", data={"type": "expense", "date": "2026-06-01", "amount": "10",
                                                     "description": "x", "counterparty": "Farmacia", "category": "Salute"})
    assert CategoryRule.query.count() == 1


def test_manual_rule_is_not_downgraded(db):
    category_rules.save("netflix", "Svago")
    category_rules.learn("Netflix", "Abbonamenti")
    rule = CategoryRule.query.one()
    assert (rule.category, rule.source) == ("Abbonamenti", "manual")


def test_ai_prompt_uses_hints_and_learned_examples(db):
    category_rules.save("bottega verde", "Salute")
    prompt = ai_classification._prompt([{"id": 1, "amount": -10, "text": "x"}], ["Salute", "Altro"])
    assert "Salute: farmacia" in prompt and "bottega verde → Salute" in prompt


def test_personal_list_is_added_once_without_duplicates(db):
    names = {c.name for c in categories.all_categories()}
    assert {"Lavoro ISolutions", "Lavoro lezioni private", "Calcetto", "Piccole consumazioni", "Palestra", "Gift"} <= names
    assert "Ristorante" not in names and "Trasporti" not in names  # Ristoranti and Trasporto were already there
    assert Category.query.filter_by(name="Lavoro ISolutions").one().kind == "income"
    categories.delete("Calcetto", None)
    categories.ensure_defaults()
    assert "Calcetto" not in {c.name for c in categories.all_categories()}  # deleted stays deleted
    assert categories._stem("Ristoranti") == categories._stem("ristorante")
