"""F21: groups of archives (a family) and their consolidated view; the archive each user opens at sign-in."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db as _db
from app.models.account import Account
from app.models.client import Client, ClientGroup
from app.models.user import User
from app.models.wealth import Debt, Goal, Holding
from app.services import consolidation, groups, owners, settings_store, studio, users
from app.services.ui_settings import SETTINGS_KEY
from tests.conftest import make_tx
from tests.test_auth import login_on, sign_in  # noqa: F401 - fixtures

ISIN = "IE00BK5BQT80"
IBAN_MARCO = "IT27X0200801600000102345678"


@pytest.fixture()
def office(app, tmp_path):
    app.instance_path = str(tmp_path)
    yield app
    _db.session.rollback()
    for client in Client.query.filter(Client.database.isnot(None)).all():
        studio._drop(client)


@pytest.fixture()
def family(office):
    """Marco on the primary archive, Giulia on hers, and an uncle who counts in dollars."""
    day = date.today().replace(day=1)
    with office.test_request_context():
        marco = studio.primary()
        giulia, uncle = studio.create("Giulia Rossi"), studio.create("Zio Sam")
        with studio.using(marco):
            owners.set_holders(["Marco Rossi"])
            _db.session.add_all([
                Account(name="Conto Marco", iban=IBAN_MARCO, opening_balance=1000),
                make_tx(date=day, description="Stipendio", amount=3000, type="income", category="Stipendio"),
                make_tx(date=day, description="Bonifico a Giulia Rossi quota affitto", amount=500, category="Casa"),
                make_tx(date=day, description="Supermercato", amount=200, category="Spesa"),
                Holding(name="Vanguard All-World", isin=ISIN, asset_class="ETF", quantity=10, avg_price=100, current_price=120),
                Goal(name="Vacanze", target_amount=2000, saved_amount=500),
            ])
        with studio.using(giulia):
            owners.set_holders(["Giulia Rossi"])
            _db.session.add_all([
                Account(name="Conto Giulia", opening_balance=2000),
                make_tx(date=day, description="Stipendio", amount=2000, type="income", category="Stipendio"),
                make_tx(date=day, description="Bonifico", bank_description="Da Marco Rossi affitto", amount=500,
                        type="income", category="Altro"),
                make_tx(date=day, description="Restituzione", bank_description="SEPA a IT27 X020 0801 6000 0010 2345 678",
                        amount=300, category="Altro"),
                Holding(name="VWCE", ticker="VWCE.MI", isin=ISIN.lower(), asset_class="ETF", quantity=5, avg_price=110,
                        current_price=120),
                Holding(name="BTP 2030", asset_class="Obbligazione", quantity=1000, avg_price=1, current_price=Decimal("0.98")),
                Debt(name="Prestito auto", type="Prestito Auto", principal=10000, balance=8000),
            ])
        with studio.using(uncle):
            settings_store.set_json(SETTINGS_KEY, {"currency": "USD"})
        group = groups.save(None, "Famiglia Rossi", "#16a34a", "noi due", [marco.id, giulia.id, uncle.id])
    return {"marco": marco.id, "giulia": giulia.id, "uncle": uncle.id, "group": group.id}


def _data(office, family):
    with office.test_request_context():
        return consolidation.consolidate(_db.session.get(ClientGroup, family["group"]))


def test_sums_each_archive_and_the_group(office, family):
    data = _data(office, family)
    marco, giulia, uncle = data["members"]
    assert [m.client.name for m in data["members"]] == ["Archivio principale", "Giulia Rossi", "Zio Sam"]
    assert not uncle.included and data["excluded"] == [uncle] and data["currency"] == "EUR"
    for key in ("net_worth", "cash", "investments", "other_assets", "liabilities", "passive_12"):
        assert data[key] == round(getattr(marco, key) + getattr(giulia, key), 2)
    assert marco.cash == 3300 and giulia.cash == 4200 and giulia.liabilities > 0
    assert data["trend"][-1] == round(marco.trend[-1] + giulia.trend[-1], 2) and len(data["labels"]) == 12
    assert data["debts"] == [{"name": "Prestito auto", "type": "Prestito Auto", "balance": giulia.debts[0]["balance"],
                              "member": "Giulia Rossi"}]
    assert data["goals"][0]["member"] == "Archivio principale" and data["goals"][0]["progress"] == 25


def test_internal_moves_do_not_count_twice(office, family):
    data = _data(office, family)
    marco, giulia, _ = data["members"]
    # Marco → Giulia named by holder (both sides), Giulia → Marco named by IBAN
    assert [(m["member"], m["type"], m["amount"], m["other_name"]) for m in data["internal"]] == [
        ("Archivio principale", "expense", 500, "Giulia Rossi"), ("Giulia Rossi", "income", 500, "Archivio principale"),
        ("Giulia Rossi", "expense", 300, "Archivio principale")]
    assert marco.income_12 == 3000 and marco.expenses_12 == 200
    assert giulia.income_12 == 2000 and giulia.expenses_12 == 0
    assert data["income_12"] == 5000 and data["expenses_12"] == 200 and data["internal_total"] == 800
    assert data["spending"] == [("Spesa", 200)]  # the rent share is not spending of the family
    assert sum(data["income"]) == 5000


def test_investments_merged_by_isin(office, family):
    data = _data(office, family)
    etf = next(h for h in data["holdings"] if h["key"] == ISIN)
    assert etf["units"] == 15 and etf["value"] == 1800 and etf["cost"] == 1550 and etf["gain"] == 250
    assert etf["members"] == ["Archivio principale", "Giulia Rossi"] and etf["gain_pct"] == 16.1
    assert len(data["holdings"]) == 2
    assert dict(data["allocation"]) == {"ETF": 1800, "Obbligazione": 980}


def test_pages_and_csv(office, family, client):
    group_id = family["group"]
    page = client.get("/groups/").get_data(as_text=True)
    assert "Famiglia Rossi" in page and "Zio Sam" in page
    page = client.get(f"/groups/{group_id}").get_data(as_text=True)
    assert "Consolidato: Famiglia Rossi" in page and "Passaggi interni" in page and "Vanguard All-World" in page
    assert "non sommato" in page and "Zio Sam" in page
    response = client.get(f"/groups/{group_id}/csv")
    text = response.get_data(as_text=True)
    assert response.mimetype == "text/csv" and "consolidato_famiglia_rossi_" in response.headers["Content-Disposition"]
    assert text.splitlines()[-1].startswith("Famiglia Rossi;EUR;") and "Zio Sam;USD;" in text
    # the menu entry and the group next to the open archive's badge
    dashboard = client.get("/dashboard").get_data(as_text=True)
    assert 'href="/groups/"' in dashboard and f'href="/groups/{group_id}"' in dashboard

    response = client.post(f"/groups/{group_id}/open/{family['giulia']}", follow_redirects=True)
    assert "Ora stai lavorando su «Giulia Rossi»" in response.get_data(as_text=True)
    assert "Conto Giulia" in client.get("/accounts/").get_data(as_text=True)


def test_create_edit_and_delete(office, family, client):
    ids = [family["marco"], family["giulia"]]
    page = client.post("/groups/new", data={"name": " ", "members": ids}, follow_redirects=True).get_data(as_text=True)
    assert "Scrivi il nome del gruppo" in page
    page = client.post("/groups/new", data={"name": "Solo io", "members": [ids[0]]}, follow_redirects=True).get_data(as_text=True)
    assert "almeno due archivi" in page
    response = client.post("/groups/new", data={"name": "Noi due", "members": ids + ["x"], "color": "#nope"})
    couple = ClientGroup.query.filter_by(name="Noi due").one()
    assert response.headers["Location"].endswith(f"/groups/{couple.id}") and couple.color in studio.COLORS
    client.post(f"/groups/{couple.id}/edit", data={"name": "Coppia", "members": ids, "color": "#dc2626", "notes": "  "})
    _db.session.refresh(couple)
    assert couple.name == "Coppia" and couple.color == "#dc2626" and couple.notes is None
    with office.test_request_context():
        marco = _db.session.get(Client, family["marco"])
        assert [g.name for g in groups.of(marco)] == ["Coppia", "Famiglia Rossi"] and groups.of(None) == []
    assert "eliminato" in client.post(f"/groups/{couple.id}/delete", follow_redirects=True).get_data(as_text=True)
    assert ClientGroup.query.filter_by(name="Coppia").first() is None and Client.query.count() == 3
    assert client.get("/groups/999").status_code == 404


def test_deleting_or_archiving_a_member(office, family, client):
    uncle = _db.session.get(Client, family["uncle"])
    client.post(f"/clients/{uncle.id}/delete", data={"confirm": "Zio Sam"})
    group = _db.session.get(ClientGroup, family["group"])
    _db.session.refresh(group)
    assert [c.name for c in group.members] == ["Archivio principale", "Giulia Rossi"]
    assert client.get(f"/groups/{group.id}").status_code == 200
    giulia = _db.session.get(Client, family["giulia"])
    client.post(f"/clients/{giulia.id}/edit", data={"name": "Giulia Rossi", "archived": "on"})
    page = client.post(f"/groups/{group.id}/open/{giulia.id}", follow_redirects=True).get_data(as_text=True)
    assert "archiviato" in page


def test_each_user_starts_on_their_own_archive(office, family, login_on, client):  # noqa: F811
    with office.test_request_context():
        users.create("marco", "password-1", is_admin=True)
        users.create("giulia", "password-2")
    giulia_user = User.query.filter_by(username="giulia").one()
    sign_in(client, "marco", "password-1")
    page = client.get("/settings/account").get_data(as_text=True)
    assert "Archivio di partenza" in page
    client.post(f"/settings/users/{giulia_user.id}/start", data={"client_id": family["giulia"]})
    _db.session.refresh(giulia_user)
    assert giulia_user.default_client_id == family["giulia"]
    client.post("/auth/logout")

    sign_in(client, "giulia", "password-2")
    assert 'title="Stai lavorando su «Giulia Rossi»' in client.get("/dashboard").get_data(as_text=True)
    # everybody sees every group
    assert "Consolidato: Famiglia Rossi" in client.get(f"/groups/{family['group']}").get_data(as_text=True)
    assert client.post(f"/settings/users/{giulia_user.id}/start", data={"client_id": family["marco"]}).status_code == 403


def test_start_archive_rules(office, family):
    with office.test_request_context():
        user = users.create("anna", "password-1")
        uncle = _db.session.get(Client, family["uncle"])
        groups.set_start(user, uncle.id)
        assert user.default_client_id == uncle.id
        groups.set_start(user, family["marco"])  # the primary archive: nothing to remember
        assert user.default_client_id is None
        uncle.archived = True
        with pytest.raises(groups.GroupError):
            groups.set_start(user, uncle.id)
        user.default_client_id = uncle.id
        groups.open_start(user)  # archived: stays on the primary archive
        assert studio.current() is None
    assert repr(ClientGroup(name="X")) == "<ClientGroup X>"


def test_nothing_to_sum(office, client):
    page = client.get("/groups/").get_data(as_text=True)
    assert "Nessun gruppo" in page and "almeno due archivi" in page
    assert 'href="/groups/"' not in client.get("/dashboard").get_data(as_text=True)  # a single archive: no menu entry
    with office.test_request_context():
        empty = ClientGroup(name="Vuoto")
        data = consolidation.consolidate(empty, date.today() - timedelta(days=1))
    assert data["members"] == [] and data["trend"] == [0.0] * 12 and data["labels"] == []
