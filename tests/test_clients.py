"""F11: a studio with several clients, each with a PostgreSQL database and a folder of its own."""
import io
import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.extensions import db as _db
from app.models.client import Client
from app.models.transaction import Transaction
from app.models.user import User
from app.services import studio


@pytest.fixture()
def office(app, tmp_path):
    """The studio with its clients; every client database made by a test is dropped afterwards."""
    app.instance_path = str(tmp_path)
    yield app
    _db.session.rollback()
    for client in Client.query.filter(Client.database.isnot(None)).all():
        studio._drop(client)


def _databases(app) -> set[str]:
    with _db.engine.connect() as connection:
        return {row[0] for row in connection.execute(text("SELECT datname FROM pg_database"))}


def _new(client, name):
    r = client.post("/clients/new", data={"name": name, "color": "#16a34a", "notes": "via test"}, follow_redirects=True)
    assert r.status_code == 200
    return Client.query.filter_by(name=name).one()


def _add(client, description, amount="-10"):
    r = client.post("/transactions/new", data={"date": "2026-10-01", "description": description, "amount": amount,
                                               "type": "expense", "category": "Spesa"})
    assert r.status_code in (200, 302)


def test_new_client_gets_a_migrated_database_of_its_own(office, client):
    rossi = _new(client, "Mario Rossi")
    assert rossi.slug == "mario_rossi" and rossi.database.endswith("_c_mario_rossi")
    assert rossi.database in _databases(office)
    engine = create_engine(_db.engine.url.set(database=rossi.database))
    with engine.connect() as connection:
        head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        categories = connection.execute(text("SELECT count(*) FROM categories")).scalar()
    engine.dispose()
    assert head == "d5f7b9c1e3a6" and categories > 10  # current schema, default categories
    page = client.get("/dashboard").get_data(as_text=True)
    assert 'id="client-chip"' in page and "Mario Rossi" in page  # the open client is always in sight
    assert client.get("/clients/").status_code == 200


def test_archives_are_separate(office, client):
    _add(client, "Spesa dello studio")
    rossi = _new(client, "Mario Rossi")  # creating opens it
    assert "Spesa dello studio" not in client.get("/transactions/").get_data(as_text=True)
    _add(client, "Spesa di Rossi")
    assert "Spesa di Rossi" in client.get("/transactions/").get_data(as_text=True)
    assert [t["description"] for t in client.get("/transactions/api").get_json()["transactions"]] == ["Spesa di Rossi"]
    client.post("/documents/upload", data={"files": (io.BytesIO(b"%PDF-1.4 rossi"), "rossi.pdf"), "doc_type": "Altro"},
                content_type="multipart/form-data")
    assert list((Path(office.instance_path) / "clients" / "mario_rossi" / "documents").iterdir())

    principale = studio.primary()
    client.post(f"/clients/{principale.id}/open")
    page = client.get("/transactions/").get_data(as_text=True)
    assert "Spesa dello studio" in page and "Spesa di Rossi" not in page
    assert "rossi.pdf" not in client.get("/documents/").get_data(as_text=True)
    assert Transaction.query.count() == 1  # outside a request: the studio database

    archive = zipfile.ZipFile(io.BytesIO(client.get(f"/clients/{rossi.id}/backup").data))
    data = json.loads(archive.read("backup.json"))
    assert [t["description"] for t in data["tables"]["transactions"]] == ["Spesa di Rossi"]
    assert any(name.startswith("documents/") for name in archive.namelist())


def test_users_stay_in_the_studio(office, client, app):
    _db.session.add(User(username="anna", password_hash="x"))
    _db.session.commit()
    rossi = _new(client, "Rossi")
    with app.test_request_context():
        studio.activate(rossi)
        assert User.query.count() == 1 and Client.query.count() == 2  # studio tables, whichever client is open
        assert Transaction.query.count() == 0
        assert _db.session.execute(text("SELECT count(*) FROM users")).scalar() == 0  # raw SQL: the client's own table


def test_edit_archive_and_delete(office, client):
    rossi = _new(client, "Rossi")
    bianchi = _new(client, "Bianchi")  # now open
    assert "Non puoi archiviare" in client.post(f"/clients/{bianchi.id}/edit", data={"name": "Bianchi", "archived": "on"},
                                                follow_redirects=True).get_data(as_text=True)
    client.post(f"/clients/{rossi.id}/edit", data={"name": "Rossi Mario", "color": "#dc2626", "notes": "", "archived": "on"})
    _db.session.refresh(rossi)
    assert rossi.name == "Rossi Mario" and rossi.archived and rossi.color == "#dc2626"
    assert "archiviato" in client.post(f"/clients/{rossi.id}/open", follow_redirects=True).get_data(as_text=True)
    assert "Scrivi il nome" in client.post(f"/clients/{rossi.id}/edit", data={"name": " "}, follow_redirects=True).get_data(as_text=True)

    assert "scrivi il suo nome esatto" in client.post(f"/clients/{bianchi.id}/delete", data={"confirm": "bianchi"},
                                                      follow_redirects=True).get_data(as_text=True)
    database = bianchi.database
    html = client.post(f"/clients/{bianchi.id}/delete", data={"confirm": "Bianchi"}, follow_redirects=True).get_data(as_text=True)
    assert "eliminato" in html and database not in _databases(office)
    assert list((Path(office.instance_path) / "clients_deleted").glob("bianchi_*.zip"))
    assert client.get("/dashboard").status_code == 200  # back on the primary archive
    principale = studio.primary()
    assert client.post(f"/clients/{principale.id}/delete", data={"confirm": principale.name}).status_code == 400
    with pytest.raises(studio.StudioError):
        studio.delete(principale)


def test_names_and_failures(office, client, monkeypatch):
    assert "Scrivi il nome" in client.post("/clients/new", data={"name": "   "}, follow_redirects=True).get_data(as_text=True)
    first = _new(client, "Società Àlfa & C.")
    assert first.slug == "societa_alfa_c"
    assert studio.slugify("Società Àlfa & C.") == "societa_alfa_c_2" and studio.slugify("!!!") == "cliente"
    assert Client(name="anna maria rossi").initials == "AM" and Client(name="").initials == "?"
    assert repr(Client(slug="x")) == "<Client x>"

    def broken(statement):
        raise RuntimeError("no rights")

    monkeypatch.setattr(studio, "_admin", broken)
    assert "Impossibile creare" in client.post("/clients/new", data={"name": "Gamma"}, follow_redirects=True).get_data(as_text=True)
    monkeypatch.undo()

    def failing_migration(client_):
        raise RuntimeError("migration failed")

    monkeypatch.setattr(studio, "migrate", failing_migration)
    with pytest.raises(RuntimeError):
        studio.create("Delta")
    assert Client.query.filter_by(name="Delta").first() is None
    assert not any(name.endswith("_c_delta") for name in _databases(office))
    monkeypatch.undo()

    from app.services import categories

    def failing_seed():
        raise RuntimeError("seed failed")

    monkeypatch.setattr(categories, "ensure_defaults", failing_seed)
    with office.test_request_context(), pytest.raises(RuntimeError):
        studio.create("Epsilon")  # fails after the database is ready: neither the client nor its database stay
    assert Client.query.filter_by(name="Epsilon").first() is None
    assert not any(name.endswith("_c_epsilon") for name in _databases(office))


def test_session_points_to_a_deleted_client(office, client):
    rossi = _new(client, "Rossi")
    with client.session_transaction() as s:
        s[studio.SESSION_KEY] = rossi.id + 999
    assert client.get("/dashboard").status_code == 200
    with client.session_transaction() as s:
        assert studio.SESSION_KEY not in s


def test_single_archive_shows_no_chip(office, client):
    assert 'id="client-chip"' not in client.get("/dashboard").get_data(as_text=True)


def test_cli(office):
    runner = office.test_cli_runner()
    assert "Created Verdi" in runner.invoke(args=["clients", "create", "Verdi"]).output
    assert "Migrated 1 client database(s): verdi" in runner.invoke(args=["clients", "migrate"]).output
    out = runner.invoke(args=["clients", "list"]).output
    assert "verdi" in out and "(studio database)" in out
    assert runner.invoke(args=["clients", "create", " "]).exit_code != 0
