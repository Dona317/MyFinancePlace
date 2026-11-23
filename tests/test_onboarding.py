"""F109: the first set-up — welcome, «new or with an archive», preferences, accounts, end."""
from decimal import Decimal

import pytest

from app.models.account import Account
from app.services import onboarding, owners, settings_store
from app.services.ui_settings import current_settings
from tests.conftest import make_tx


@pytest.fixture()
def on(app):
    app.config["ONBOARDING"] = True
    yield
    app.config["ONBOARDING"] = False


def test_an_empty_archive_starts_with_the_tutorial_and_skip_leads_to_the_choice(client, db, on):
    assert client.get("/dashboard").headers["Location"].endswith("/benvenuto/")
    page = client.get("/benvenuto/benvenuto").get_data(as_text=True)
    assert "Benvenuto in MyFinancePlace" in page and 'class="sidebar"' not in page  # full page, no menu
    skip = client.post("/benvenuto/benvenuto/salta")
    assert skip.headers["Location"].endswith("/benvenuto/scelta")
    assert "Hai già usato MyFinancePlace?" in client.get("/benvenuto/scelta").get_data(as_text=True)
    # left there: the next visit starts again from the choice
    assert client.get("/benvenuto/").headers["Location"].endswith("/benvenuto/scelta")


def test_an_archive_in_use_is_never_interrupted(client, db, on):
    db.session.add(make_tx())
    db.session.commit()
    assert client.get("/dashboard").status_code == 200


def test_the_new_users_path(client, db, on):
    assert client.post("/benvenuto/scelta", data={"path": "new"}).headers["Location"].endswith("/benvenuto/preferenze")
    client.post("/benvenuto/preferenze", data={"language": "it", "currency": "EUR", "locale": "de-DE"})
    assert current_settings()["locale"] == "de-DE" and current_settings()["date_format"] == "DD.MM.YYYY"
    client.post("/benvenuto/aspetto", data={"font": "plex"})
    assert current_settings()["font"] == "plex"
    bad = client.post("/benvenuto/persone", data={"first": ["Marco"], "last": [""]}, follow_redirects=True)
    assert "sia il nome sia il cognome" in bad.get_data(as_text=True)
    client.post("/benvenuto/persone", data={"first": ["Marco", "Giulia", ""], "last": ["Rossi", "Rossi", ""],
                                            "modules": ["module_portfolio", "module_debt"]})
    assert owners.holders() == ["Marco Rossi", "Giulia Rossi"]
    page = client.get("/benvenuto/persone").get_data(as_text=True)
    assert 'value="Giulia"' in page and 'value="Rossi"' in page and 'data-max="10"' in page
    many = {"first": [f"P{i}" for i in range(12)], "last": ["Rossi"] * 12}
    client.post("/benvenuto/persone", data=many)
    assert len(owners.holders()) == 10  # at most ten people
    client.post("/benvenuto/persone", data={"first": ["Marco", "Giulia"], "last": ["Rossi", "Rossi"],
                                            "modules": ["module_portfolio", "module_debt"]})
    assert current_settings()["module_debt"] and not current_settings()["module_insurance"]
    page = client.get("/benvenuto/conti").get_data(as_text=True)
    assert "Saldo di oggi" in page and "Passo 4 di 6" in page
    done = client.post("/benvenuto/conti", data={
        "kind": ["current", "card", "current"], "name": ["Fineco", "Visa", ""], "bank": ["Fineco", "", ""],
        "balance": ["1.234,56", "", ""], "owner": ["Marco Rossi", "", ""], "cash": "50"})
    assert done.headers["Location"].endswith("/benvenuto/movimenti")
    fineco = Account.query.filter_by(name="Fineco").one()
    assert fineco.opening_balance == Decimal("1234.56") and fineco.owner == "Marco Rossi" and fineco.reconciled_on
    assert Account.query.filter_by(name="Visa").one().kind == "card"
    assert Account.query.filter_by(fixed="cash").one().opening_balance == 50
    page = client.get("/benvenuto/movimenti").get_data(as_text=True)
    assert "Collega la banca" in page and "Fineco" in page and "Visa" in page
    # a wrong amount: shown again with the message, nothing made
    bad = client.post("/benvenuto/conti", data={"kind": ["current"], "name": ["X"], "bank": [""], "balance": ["abc"]},
                      follow_redirects=True)
    assert "non è un importo" in bad.get_data(as_text=True) and not Account.query.filter_by(name="X").first()
    # a step skipped goes to the list of the end; the end opens the dashboard, and it does not come back
    client.post("/benvenuto/movimenti/salta")
    end = client.get("/benvenuto/fine").get_data(as_text=True)
    assert "Tutto pronto" in end and "Porta i movimenti" in end
    assert client.post("/benvenuto/chiudi").headers["Location"].endswith("/dashboard")
    assert onboarding.state()["done"] and not onboarding.needed()


def test_the_archive_path_restores_a_backup_and_comes_back(client, db, on):
    assert client.post("/benvenuto/scelta", data={"path": "existing"}).headers["Location"].endswith("/benvenuto/importa")
    page = client.get("/benvenuto/importa").get_data(as_text=True)
    assert 'action="/export/restore"' in page and 'name="next" value="/benvenuto/fine"' in page
    # no file: back to the step that sent it
    assert client.post("/export/restore", data={"next": "/benvenuto/fine"}).headers["Location"].endswith("/benvenuto/fine")


def test_later_and_again(client, db, on):
    response = client.post("/benvenuto/chiudi", data={"later": "1"}, follow_redirects=True)
    assert "Configurazione rimandata" in response.get_data(as_text=True)
    assert not onboarding.needed()
    client.post("/benvenuto/ricomincia")
    assert onboarding.needed() and onboarding.current_step() == "benvenuto"
    assert client.get("/benvenuto/nope").status_code == 404 and client.post("/benvenuto/nope/salta").status_code == 404


def test_names_already_taken_get_a_number(app, db):
    db.session.add(Account(name="Conto corrente", kind="current"))
    db.session.commit()
    made = onboarding.add_accounts([{"kind": "current", "name": "Conto corrente"}, {"kind": "weird", "name": "Altro"}])
    assert [a.name for a in made] == ["Conto corrente 2", "Altro"] and made[1].kind == "current"
    settings_store.set_json(onboarding.STATE, {})
    assert onboarding.made_accounts()  # none made in the tutorial: every account of the user's


def test_primi_passi_lists_what_to_prepare_and_comes_back_to_it(client, db):
    page = client.get("/benvenuto/primi-passi").get_data(as_text=True)
    assert "Prepara l'app" in page and "0 di 6" in page and "I tuoi conti" in page and "Investimenti" in page
    menu = client.get("/transactions/").get_data(as_text=True)
    assert 'href="/benvenuto/primi-passi"' in menu.split('class="sidebar-nav"')[1] and "0/6" in menu
    # a step opened from the list goes back to it, marked done
    back = client.post("/benvenuto/conti?da=lista", data={"kind": ["current"], "name": ["Fineco"], "bank": [""],
                                                         "balance": ["100"]})
    assert back.headers["Location"].endswith("/benvenuto/primi-passi")
    client.post("/benvenuto/preferenze?da=lista", data={"language": "it", "currency": "EUR", "locale": "it-IT"})
    items = {item["key"]: item for item in onboarding.checklist()}
    assert items["conti"]["done"] and items["preferenze"]["done"] and not items["movimenti"]["done"]
    assert onboarding.progress() == (2, 6)
    # all done: the menu entry goes away
    db.session.add(make_tx())
    db.session.commit()
    for step in ("aspetto", "persone"):
        onboarding.mark(step)
    from app.models.wealth import Holding
    db.session.add(Holding(name="ETF", asset_class="ETF", quantity=1, avg_price=1))
    db.session.commit()
    assert onboarding.progress() == (6, 6)
    assert 'href="/benvenuto/primi-passi"' not in client.get("/transactions/").get_data(as_text=True).split('class="sidebar-nav"')[1]


def test_primi_passi_can_be_skipped_item_by_item_or_all(client, db):
    client.post("/benvenuto/primi-passi/salta", data={"key": "aspetto"})
    aspetto = next(i for i in onboarding.checklist() if i["key"] == "aspetto")
    assert aspetto["skipped"] and onboarding.progress()[0] == 1  # skipped counts as done
    page = client.get("/benvenuto/primi-passi").get_data(as_text=True)
    assert "Saltato · apri" in page and "Salta i primi passi" in page
    assert onboarding.in_menu()
    done = client.post("/benvenuto/primi-passi/salta", data={"all": "1"}, follow_redirects=True).get_data(as_text=True)
    assert "tolto dal menu" in done and not onboarding.in_menu()
    assert 'href="/benvenuto/primi-passi"' not in client.get("/transactions/").get_data(as_text=True).split('class="sidebar-nav"')[1]
    assert "Rimetti nel menu" in client.get("/benvenuto/primi-passi").get_data(as_text=True)  # still reachable
    client.post("/benvenuto/primi-passi/salta", data={"show": "1"})
    assert onboarding.in_menu()
