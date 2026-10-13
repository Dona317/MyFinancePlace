"""Sign-in: the first user is created on the first visit, then only administrators add users. Data is shared."""
import pytest
from flask import g

from app.models.transaction import Transaction
from app.models.user import User
from app.services import backup, users
from tests.conftest import make_tx


@pytest.fixture()
def login_on(app):
    app.config["LOGIN_DISABLED"] = False  # the other tests run with sign-in off
    # The fixture keeps one app context open for the whole test, so `g` (where Flask-Login caches the user)
    # would survive between requests; forget it first thing, so every request loads the user from its session
    # like a real one does.
    def forget_cached_user():
        g.pop("_login_user", None)

    app.before_request_funcs.setdefault(None, []).insert(0, forget_cached_user)
    return app


def sign_in(client, username="anna", password="password-1", **extra):
    return client.post("/auth/login", data={"username": username, "password": password} | extra)


@pytest.fixture()
def admin(login_on, db):
    return users.create("anna", "password-1", is_admin=True)


def test_first_visit_asks_for_the_first_administrator(login_on, client, db):
    assert client.get("/dashboard").headers["Location"].endswith("/auth/setup")
    assert client.get("/auth/login").headers["Location"].endswith("/auth/setup")
    page = client.post("/auth/setup", data={"username": "anna", "password": "corta", "confirm": "corta"})
    assert "almeno 8 caratteri" in page.get_data(as_text=True) and not users.any_user()
    response = client.post("/auth/setup", data={"username": "anna", "password": "password-1", "confirm": "password-1"})
    assert response.headers["Location"].endswith("/dashboard")
    assert User.query.one().is_admin
    assert client.get("/dashboard").status_code == 200  # signed in straight away
    # once somebody exists the setup page is gone: nobody else can make themselves admin
    client.post("/auth/logout")
    assert client.get("/auth/setup").headers["Location"].endswith("/auth/login")
    client.post("/auth/setup", data={"username": "mallory", "password": "password-2", "confirm": "password-2"})
    assert User.query.count() == 1


def test_pages_and_api_need_sign_in(admin, client):
    response = client.get("/transactions/?tag=casa")
    assert response.status_code == 302 and "/auth/login?next=/transactions/?tag%3Dcasa" in response.headers["Location"]
    api = client.get("/transactions/api")
    assert api.status_code == 401 and api.get_json()["message"]
    assert client.get("/auth/login").status_code == 200
    assert client.get("/static/css/main.css").status_code == 200


def test_login_ok_and_wrong(admin, client):
    wrong = sign_in(client, password="sbagliata")
    assert wrong.status_code == 401 and "Nome utente o password non corretti." in wrong.get_data(as_text=True)
    assert 'value="anna"' in wrong.get_data(as_text=True)
    assert sign_in(client, username="nessuno").status_code == 401
    ok = sign_in(client, username=" ANNA ")  # the name is not case sensitive
    assert ok.status_code == 302 and ok.headers["Location"].endswith("/dashboard")
    assert User.query.one().last_login is not None
    assert client.get("/transactions/api").status_code == 200
    html = client.get("/dashboard").get_data(as_text=True)
    assert "anna" in html and "Amministratore" in html and 'action="/auth/logout"' in html


def test_next_is_followed_only_inside_the_app(admin, client):
    assert client.post("/auth/login?next=/reports/", data={"username": "anna", "password": "password-1"}
                       ).headers["Location"].endswith("/reports/")
    client.post("/auth/logout")
    response = client.post("/auth/login?next=https://evil.example/", data={"username": "anna", "password": "password-1"})
    assert "evil" not in response.headers["Location"]


def test_logout_is_a_post(admin, client):
    sign_in(client, remember="on")
    assert client.get("/auth/logout").status_code == 405
    assert client.post("/auth/logout").headers["Location"].endswith("/auth/login")
    assert client.get("/dashboard").status_code == 302
    # "remember me" is forgotten too
    assert client.get_cookie("remember_token") is None or not client.get_cookie("remember_token").value


def test_everyone_sees_the_same_data(admin, client, db):
    users.create("bruno", "password-2")
    db.session.add(make_tx(description="Spesa comune"))
    db.session.commit()
    sign_in(client, "bruno", "password-2")
    assert "Spesa comune" in client.get("/transactions/").get_data(as_text=True)


def test_only_administrators_manage_users(admin, client, db):
    bruno = users.create("bruno", "password-2")
    sign_in(client, "bruno", "password-2")
    page = client.get("/settings/account").get_data(as_text=True)
    assert "Cambia password" in page and "Aggiungi un utente" not in page
    assert client.post("/settings/users/add", data={"username": "carlo", "password": "password-3"}).status_code == 403
    assert client.post(f"/settings/users/{admin.id}/delete").status_code == 403
    assert client.post(f"/settings/users/{admin.id}/password", data={"password": "presa-io!"}).status_code == 403
    client.post("/auth/logout")

    sign_in(client)
    page = client.get("/settings/account").get_data(as_text=True)
    assert "Aggiungi un utente" in page and "bruno" in page
    client.post("/settings/users/add", data={"username": "carlo", "password": "password-3", "is_admin": "on"})
    assert User.query.filter_by(username="carlo").one().is_admin
    client.post("/settings/users/add", data={"username": "Carlo", "password": "password-3"})
    assert User.query.count() == 3  # same name, any case: refused
    client.post(f"/settings/users/{bruno.id}/password", data={"password": "nuova-password"})
    assert users.authenticate("bruno", "nuova-password")
    client.post(f"/settings/users/{bruno.id}/delete")
    assert db.session.get(User, bruno.id) is None
    client.post(f"/settings/users/{admin.id}/delete")  # not yourself
    assert db.session.get(User, admin.id) is not None


def test_last_administrator_stays(admin, db):
    other = users.create("bruno", "password-2", is_admin=True)
    users.delete(other, by=admin)
    helper = users.create("carlo", "password-3")
    with pytest.raises(ValueError, match="almeno un amministratore"):
        users.delete(admin, by=helper)


def test_change_own_password(admin, client):
    sign_in(client)
    client.post("/settings/account/password", data={"current": "sbagliata", "password": "nuova-pass", "confirm": "nuova-pass"})
    assert users.authenticate("anna", "password-1")
    client.post("/settings/account/password", data={"current": "password-1", "password": "nuova-pass", "confirm": "altra-pass"})
    assert users.authenticate("anna", "password-1")
    client.post("/settings/account/password", data={"current": "password-1", "password": "nuova-pass", "confirm": "nuova-pass"})
    assert users.authenticate("anna", "nuova-pass") and not users.authenticate("anna", "password-1")


def test_restoring_a_backup_keeps_the_users(admin, db):
    db.session.add(make_tx(description="Vecchia"))
    db.session.commit()
    data = backup.export_data()
    assert "users" not in data["tables"]  # passwords never end up in a backup file
    users.create("bruno", "password-2")
    backup.restore(data, {})
    assert {u.username for u in User.query.all()} == {"anna", "bruno"}
    assert Transaction.query.one().description == "Vecchia"


def test_cli(app, db):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["users", "create", "anna", "--admin", "--password", "password-1"])
    assert result.exit_code == 0 and User.query.one().is_admin
    assert runner.invoke(args=["users", "create", "ANNA", "--password", "password-1"]).exit_code != 0
    result = runner.invoke(args=["users", "reset-password", "anna", "--password", "ricomincio"])
    assert result.exit_code == 0 and users.authenticate("anna", "ricomincio")
    assert runner.invoke(args=["users", "reset-password", "nessuno", "--password", "ricomincio"]).exit_code != 0
    assert "anna\tadmin" in runner.invoke(args=["users", "list"]).output
