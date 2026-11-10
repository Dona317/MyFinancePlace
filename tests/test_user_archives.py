"""F24: each user has an archive of their own; an administrator exports the archives of the users chosen."""
import io
import zipfile

from app.models.client import Client
from app.models.user import User
from app.services import studio, users
from tests.test_auth import admin, login_on, sign_in  # noqa: F401 - the fixtures


def test_a_new_user_gets_an_archive_of_their_own_and_stays_on_it(admin, client, db):  # noqa: F811 - the fixture
    sign_in(client)
    client.post("/settings/users/add", data={"username": "Bruno", "password": "password-2"})
    bruno = User.query.filter_by(username="Bruno").one()
    archive = db.session.get(Client, bruno.default_client_id)
    assert archive is not None and archive.name == "Bruno" and archive.database
    page = client.get("/settings/account").get_data(as_text=True)
    assert "Esporta gli archivi degli utenti" in page and "archivio suo" in page
    client.post("/auth/logout")
    # Bruno signs in: his archive, and no way to another one
    sign_in(client, "Bruno", "password-2")
    client.get("/dashboard")
    with client.session_transaction() as session:
        assert session.get(studio.SESSION_KEY) == archive.id
    with client.session_transaction() as session:
        session[studio.SESSION_KEY] = studio.primary().id  # tries the primary archive
    client.get("/dashboard")
    with client.session_transaction() as session:
        assert session.get(studio.SESSION_KEY) == archive.id
    assert client.get("/clients/").status_code == 403


def test_the_administrator_exports_the_chosen_users_and_gives_an_archive_to_an_old_user(admin, client, db):  # noqa: F811
    old = users.create("carla", "password-3")  # made before: no archive of her own
    sign_in(client)
    assert "Crea il suo archivio" in client.get("/settings/account").get_data(as_text=True)
    client.post(f"/settings/users/{old.id}/archive")
    db.session.refresh(old)
    assert old.default_client_id is not None
    response = client.post("/settings/users/export", data={"user_id": [str(old.id), str(admin.id)]})
    assert response.mimetype == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(response.data)).namelist()
    assert sorted(names) == sorted([f"{studio.slugify_file(admin.username)}.zip", "carla.zip"])
    assert "Scegli almeno un utente" in client.post("/settings/users/export", data={}, follow_redirects=True).get_data(as_text=True)
    client.post("/auth/logout")
    sign_in(client, "carla", "password-3")
    assert client.post("/settings/users/export", data={"user_id": [str(old.id)]}).status_code == 403
