"""F98–F105: saved views and «Gestisci» of the register, the flows between the accounts, the bell's window, the
blocks of Entrate/Uscite, the archive's icon and owner, the value and use of a securities account."""
from datetime import date
from decimal import Decimal

from app.models.account import Account
from app.models.user import User
from app.models.wealth import Holding
from app.services import account_flows, register_views, securities, studio
from tests.conftest import make_tx


def test_a_view_is_saved_replaced_by_name_and_deleted(app, client, db):
    r = client.post("/transactions/views", data={"view_name": "  Spese   auto ", "type": "expense", "q": "benzina",
                                                 "start": "2026-01-01"})
    assert r.status_code == 302
    with app.test_request_context():
        assert register_views.load() == [{"name": "Spese auto", "query": {"type": "expense", "q": "benzina"}}]
    client.post("/transactions/views", data={"view_name": "spese auto", "type": "income"})  # same name: replaced
    client.post("/transactions/views", data={"view_name": "Vuota"})  # nothing to keep: not saved
    with app.test_request_context():
        assert register_views.load() == [{"name": "spese auto", "query": {"type": "income"}}]
        assert register_views._clean("not a dict") is None and register_views._clean({"name": "x", "query": {}}) is None
    client.post("/transactions/views/delete", data={"view_name": "spese auto"})
    with app.test_request_context():
        assert register_views.load() == []


def test_the_register_prefs_keep_only_known_values(app, client, db):
    client.post("/transactions/prefs", data={"page_size": "50", "show_col": ["category"]})
    with app.test_request_context():
        assert register_views.prefs() == {"page_size": 50, "hide": ["tags"]}
        assert register_views.save_prefs("tanti", ["tags", "boh"]) == {"page_size": 100, "hide": ["tags"]}


def test_the_flows_between_the_accounts(app, client, db):
    bank, broker = Account(name="Banca", kind="checking"), Account(name="Broker", kind="other")
    db.session.add_all([bank, broker])
    db.session.commit()
    db.session.add_all([
        make_tx(amount=1000, type="income", account_id=bank.id, date=date(2026, 6, 1)),
        make_tx(amount=200, type="expense", account_id=bank.id, date=date(2026, 6, 2)),
        make_tx(amount=300, type="transfer", account_id=bank.id, counter_account_id=broker.id, date=date(2026, 6, 3)),
        make_tx(amount=40, type="expense", date=date(2026, 6, 4)),  # on no account
        make_tx(amount=999, type="expense", account_id=bank.id, date=date(2025, 6, 4)),  # out of the period
    ])
    db.session.commit()
    with app.test_request_context():
        data = account_flows.flows(date(2026, 1, 1), date(2027, 1, 1))
    nodes = {n["id"]: n for n in data["nodes"]}
    assert set(nodes) == {f"a{bank.id}", f"a{broker.id}", account_flows.OUTSIDE, account_flows.NOWHERE}
    assert nodes[f"a{bank.id}"]["value"] == 1500 and nodes[account_flows.NOWHERE]["filter"] == {"account": "none"}
    edges = {(e["source"], e["target"], e["kind"]): e for e in data["edges"]}
    transfer = edges[(f"a{bank.id}", f"a{broker.id}", "transfer")]
    assert transfer["value"] == 300 and transfer["filter"] == {"type": "transfer", "account": bank.id, "to": broker.id}
    assert edges[(account_flows.OUTSIDE, f"a{bank.id}", "income")]["value"] == 1000

    page = client.get("/transactions/flows?year=2026&part=year").get_data(as_text=True)
    assert "Banca" in page and "Broker" in page


def test_the_bells_window_and_the_blocks_of_entrate(client, db):
    assert client.get("/notifications/peek?back=//evil.example").status_code == 200
    assert client.post("/reports/income/layout", data="x", content_type="text/plain").status_code == 400
    assert client.post("/reports/income/layout", json={"widgets": "no"}).status_code == 400
    saved = client.post("/reports/spending/layout", json={"widgets": [{"id": "net", "visible": False}]}).get_json()
    assert "layout" in saved
    assert "layout" in client.post("/reports/income/layout", json={"reset": True}).get_json()


def test_the_icon_and_the_owner_of_an_archive(app, client, db):
    with app.test_request_context():
        archive = studio.primary()
        archive_id = archive.id
    client.post(f"/clients/{archive_id}/icon", data={"icon": "house"})
    client.post(f"/clients/{archive_id}/icon", data={"icon": "not-an-icon"})  # unknown: left as it is
    with app.test_request_context():
        archive = studio.primary()
        assert archive.icon == "house"
        owner_of = next(p()["archive_owner"] for p in app.template_context_processors[None] if "archive_owner" in p())
        assert owner_of(None) is None and owner_of(archive) is None
        user = User(username="anna", default_client_id=archive.id)
        user.set_password("x")
        db.session.add(user)
        db.session.commit()
        assert owner_of(archive) == "anna"


def test_the_value_and_the_use_of_a_securities_account(app, db):
    directa = Account(name="Directa", kind="other")
    db.session.add(directa)
    db.session.commit()
    with app.test_request_context():
        dossier = securities.for_settlement(directa)
        db.session.commit()
        assert securities.value(dossier) == 0 and not securities.in_use(dossier)
        db.session.add(Holding(name="All-World", ticker="VWCE.DE", asset_class="ETF", quantity=10, avg_price=100,
                               current_price=Decimal(120), multiplier=Decimal(1), opening_quantity=10,
                               opening_price=100, opening_date=date(2025, 1, 2), opening_account_id=dossier.id))
        db.session.commit()
        assert securities.in_use(dossier)
        assert securities.value(dossier) == sum(p.value for p in securities.positions(securities_account_id=dossier.id))


def test_the_flows_keep_the_giroconti_though_left_out_of_the_analyses(app, db):
    from app.models.category import Category
    from app.services import categories
    bank, saving = Account(name="Banca", kind="checking"), Account(name="Deposito", kind="savings")
    db.session.add_all([bank, saving])
    db.session.commit()
    giroconto = Category.query.filter_by(name="Giroconto").first() or Category(name="Giroconto", kind="both", position=99)
    giroconto.excluded = True
    db.session.add(giroconto)
    db.session.add_all([
        make_tx(amount=500, type="transfer", category="Giroconto", account_id=bank.id, counter_account_id=saving.id,
                date=date(2026, 6, 3)),
        make_tx(amount=7, type="expense", category="Giroconto", account_id=bank.id, date=date(2026, 6, 4)),
        make_tx(amount=3, type="expense", category="Riconciliazione", account_id=bank.id, date=date(2026, 6, 5)),
    ])
    db.session.add(Category(name="Riconciliazione", kind="both", position=98, excluded=True))
    db.session.commit()
    categories.forget()
    with app.test_request_context():
        data = account_flows.flows(date(2026, 1, 1), date(2027, 1, 1))
    edges = {(e["source"], e["target"], e["kind"]): e["value"] for e in data["edges"]}
    assert edges[(f"a{bank.id}", f"a{saving.id}", "transfer")] == 500  # the giroconto is drawn
    # one read from a single bank (an expense «Giroconto»): drawn as a transfer out of the account
    assert edges[(f"a{bank.id}", account_flows.OUTSIDE, "transfer")] == 7
    assert not any(kind == "expense" for _s, _t, kind in edges)
