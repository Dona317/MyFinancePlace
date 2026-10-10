"""
Sections of the app per user: an administrator blocks sections for a user (not in the menu, pages and API answer
403), each user hides sections from their own menu; the switches of Settings → Moduli still apply to everybody.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.user import User
from app.models.wealth import InsurancePolicy
from app.services import sections, users


@pytest.fixture()
def people(app, db):
    """Sign-in on, an administrator and a user; returns a function that signs one of them in."""
    app.config["LOGIN_DISABLED"] = False
    users.create("admin", "password-admin", is_admin=True)
    users.create("mario", "password-mario")

    def sign_in(client, name):
        client.post("/auth/logout")
        assert client.post("/auth/login", data={"username": name, "password": f"password-{name}"}).status_code == 302
        return client
    return sign_in


def _mario():
    return User.query.filter_by(username="mario").one()


def test_every_page_belongs_to_one_section_or_none():
    assert sections.section_of("portfolio.index") == "portfolio"
    assert sections.section_of("lifestyle.budget_save") == "budget"
    assert sections.section_of("lifestyle.goal_new") == "goals"
    assert sections.section_of("lifestyle.index") == "lifestyle"
    assert sections.section_of("transactions.api_list") == "transactions"
    assert sections.section_of("dashboard.dashboard") is None and sections.section_of("settings.index") is None
    assert sections.section_of(None) is None
    assert sections.clean(["debt", "nope", "portfolio", "debt"]) == ["portfolio", "debt"]


def test_an_administrator_blocks_sections_for_a_user(people, client, db):
    people(client, "admin")
    page = client.get(f"/settings/users/{_mario().id}/sections").get_data(as_text=True)
    assert 'name="portfolio" checked' in page and 'name="transactions" checked' in page
    form = {s.key: "on" for s in sections.SECTIONS if s.key not in ("portfolio", "transactions")}
    client.post(f"/settings/users/{_mario().id}/sections", data=form)
    assert _mario().blocked_sections == ["transactions", "portfolio"]
    assert "2 bloccate" in client.get("/settings/account").get_data(as_text=True)

    people(client, "mario")
    menu = client.get("/dashboard").get_data(as_text=True)
    assert "/portfolio/" not in menu and "/transactions/" not in menu and "/reports/" in menu  # menu and dashboard
    assert "Investimenti" not in menu  # its card on the dashboard goes too
    blocked = client.get("/portfolio/")
    assert blocked.status_code == 403 and "Non hai accesso" in blocked.get_data(as_text=True)
    assert client.get("/transactions/api").status_code == 403  # the API too
    assert client.get("/transactions/api").get_json()["message"] == "Non hai accesso a questa sezione."
    assert client.get("/reports/").status_code == 200

    people(client, "admin")  # administrators always see everything
    assert client.get("/portfolio/").status_code == 200


def test_administrators_cannot_be_blocked(people, client, db):
    people(client, "admin")
    admin = User.query.filter_by(username="admin").one()
    page = client.post(f"/settings/users/{admin.id}/sections", data={}, follow_redirects=True).get_data(as_text=True)
    assert "vedono sempre tutte le sezioni" in page and admin.blocked_sections == []


def test_only_administrators_change_others_sections(people, client, db):
    people(client, "mario")
    assert client.get(f"/settings/users/{_mario().id}/sections").status_code == 403
    assert client.post(f"/settings/users/{_mario().id}/sections", data={}).status_code == 403


def test_each_user_hides_sections_from_their_own_menu(people, client, db):
    sections.set_blocked(_mario(), ["debt"])
    people(client, "mario")
    page = client.get("/settings/menu").get_data(as_text=True)
    assert 'name="debt"  disabled' in page or ('name="debt"' in page and "Bloccata da un amministratore" in page)
    form = {s.key: "on" for s in sections.SECTIONS if s.key not in ("budget", "goals", "lifestyle", "debt")}
    client.post("/settings/menu", data=form)
    assert _mario().hidden_sections == ["lifestyle", "budget", "goals", "debt"]
    menu = client.get("/dashboard").get_data(as_text=True)
    assert "/lifestyle/budget" not in menu and 'data-section="stiledivita"' not in menu  # a whole empty group goes
    assert client.get("/lifestyle/budget").status_code == 200  # hidden only from the menu: still reachable
    people(client, "admin")
    assert "/lifestyle/budget" in client.get("/dashboard").get_data(as_text=True)  # the others' menus are theirs


def test_reminders_of_blocked_sections_are_not_shown(people, client, db):
    db.session.add(InsurancePolicy(type="Auto", company="Unipol", premium=Decimal("300"),
                                   expiry_date=date.today() + timedelta(days=5)))
    db.session.commit()
    people(client, "mario")
    assert "Unipol" in client.get("/notifications/").get_data(as_text=True)
    sections.set_blocked(_mario(), ["insurance", "notifications"])
    page = client.get("/dashboard").get_data(as_text=True)
    assert "topbar-bell" not in page
    sections.set_blocked(_mario(), ["insurance"])
    assert "Unipol" not in client.get("/notifications/").get_data(as_text=True)


def test_switched_off_for_everybody_still_wins(people, client, db):
    people(client, "admin")
    client.post("/settings/save", data={k: "on" for k in ("module_debt", "module_insurance", "module_documents",
                                                           "module_snapshots", "module_export", "module_tax",
                                                           "lifestyle_goals")})  # portfolio off
    assert "/portfolio/" not in client.get("/dashboard").get_data(as_text=True)
    assert client.get("/portfolio/").status_code == 404
    assert "Disattivata per tutti" in client.get("/settings/menu").get_data(as_text=True)


def test_without_sign_in_there_is_one_shared_menu(client):
    assert client.get("/settings/menu").status_code == 404
    assert "/portfolio/" in client.get("/dashboard").get_data(as_text=True)
