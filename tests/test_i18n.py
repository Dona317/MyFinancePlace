"""Interface language: Italian by default, English when chosen in Settings; the English catalog is complete."""
import json
import re
from datetime import date, timedelta
from pathlib import Path

from babel.messages.mofile import read_mo
from babel.messages.pofile import read_po

from app.models.wealth import InsurancePolicy
from app.routes.settings import DEFAULT_SETTINGS, SETTINGS_KEY
from app.services import settings_store
from tests.conftest import make_tx

TRANSLATIONS = Path(__file__).resolve().parents[1] / "app" / "translations"
PLACEHOLDER = re.compile(r"%\(\w+\)[sd]|%%")


def use_english(db):
    settings_store.set(SETTINGS_KEY, json.dumps({**DEFAULT_SETTINGS, "language": "en"}))
    db.session.commit()


def test_italian_is_the_default(client, db):
    html = client.get("/dashboard").get_data(as_text=True)
    assert '<html lang="it"' in html and "Transazioni Recenti" in html and "Recent Transactions" not in html


def test_english_everywhere_once_chosen(client, db):
    db.session.add(make_tx(date=date.today(), category="Casa", amount=50))
    db.session.commit()
    response = client.post("/settings/save", data={**{k: v for k, v in DEFAULT_SETTINGS.items() if not isinstance(v, bool)},
                                                    **{k: "on" for k, v in DEFAULT_SETTINGS.items() if v is True},
                                                    "language": "en"}, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert "Settings saved successfully." in html  # the flash message, too
    assert '<html lang="en"' in html and 'value="en" lang="en" selected' in html
    dashboard = client.get("/dashboard").get_data(as_text=True)
    assert "Recent Transactions" in dashboard and "Income by category" in dashboard
    assert "Transazioni Recenti" not in dashboard
    # texts used by the scripts, and the theme button
    assert '"to_dark": "Switch to dark mode"' in dashboard and 'aria-label="Switch to dark mode"' in dashboard
    # chart month labels
    assert '"Jan"' in client.get("/lifestyle/").get_data(as_text=True)


def test_english_validation_messages_and_stored_words(client, db):
    use_english(db)
    html = client.post("/transactions/new", data={"date": "2026-06-01", "description": "x", "amount": "abc",
                                                  "type": "expense"}).get_data(as_text=True)
    assert "is not a valid number" in html
    # a word stored in Italian is shown in English, the database keeps it as it is
    db.session.add(InsurancePolicy(type="Auto", company="Generali", premium=100, frequency="annual",
                                   expiry_date=date.today() + timedelta(days=10)))
    db.session.commit()
    page = client.get("/insurance/").get_data(as_text=True)
    assert "Car (Generali)" in page and "1 policy expires within" in page
    assert InsurancePolicy.query.one().type == "Auto"


def test_plural_forms(client, db):
    use_english(db)
    db.session.add(InsurancePolicy(type="Casa", company="A", premium=10, frequency="annual", expiry_date=date.today() + timedelta(days=5)))
    db.session.add(InsurancePolicy(type="Vita", company="B", premium=10, frequency="annual", expiry_date=date.today() + timedelta(days=6)))
    db.session.commit()
    assert "2 policies expire within" in client.get("/insurance/").get_data(as_text=True)


def test_english_catalog_is_complete_and_compiled():
    po = read_po(open(TRANSLATIONS / "en" / "LC_MESSAGES" / "messages.po", "rb"))
    for message in po:
        if not message.id:
            continue
        ids = [message.id] if isinstance(message.id, str) else list(message.id)
        strings = [message.string] if isinstance(message.string, str) else list(message.string)
        assert all(strings), f"not translated: {message.id!r}"
        for source, text in zip(ids, strings):  # same placeholders, or the page would crash
            assert sorted(PLACEHOLDER.findall(source)) == sorted(PLACEHOLDER.findall(text)) or len(ids) > 1, message.id
    mo = read_mo(open(TRANSLATIONS / "en" / "LC_MESSAGES" / "messages.mo", "rb"))
    key = lambda m: tuple(m.id) if isinstance(m.id, (list, tuple)) else m.id  # noqa: E731
    assert {key(m) for m in mo if m.id} == {key(m) for m in po if m.id}, "run: python scripts/translations.py compile"
