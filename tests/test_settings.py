"""The Settings page: choices are saved in the database and shown again (bug: it always showed the defaults)."""
import json

from app.routes.settings import DEFAULT_SETTINGS, SETTINGS_KEY, current_settings
from app.services import settings_store


def checked(html: str, key: str) -> bool:
    tag = html.split(f'name="{key}"')[1].split(">")[0]
    return "checked" in tag


def test_saved_choices_are_shown_and_applied(client, db):
    form = {key: "on" for key, value in DEFAULT_SETTINGS.items() if value is True}
    del form["dashboard_debt"], form["module_portfolio"]
    form.update(currency="USD", locale="it-IT", date_format="YYYY-MM-DD")
    client.post("/settings/save", data=form)

    html = client.get("/settings/").get_data(as_text=True)
    assert not checked(html, "dashboard_debt") and not checked(html, "module_portfolio")
    assert checked(html, "dashboard_income")
    assert '<option value="USD" selected' in html

    # applied everywhere: the dashboard card and the sidebar link disappear
    dashboard = client.get("/dashboard").get_data(as_text=True)
    assert "Debito Totale" not in dashboard and 'href="/portfolio/"' not in dashboard


def test_choices_survive_a_new_browser(app, client, db):
    client.post("/settings/save", data={"dashboard_income": "on"})
    other_browser = app.test_client()  # no cookies: the choices come from the database
    html = other_browser.get("/settings/").get_data(as_text=True)
    assert checked(html, "dashboard_income") and not checked(html, "dashboard_expenses")


def test_reset_restores_defaults(client, db):
    client.post("/settings/save", data={})
    assert current_settings()["dashboard_income"] is False
    client.post("/settings/reset")
    assert current_settings() == DEFAULT_SETTINGS


def test_bad_saved_values_are_ignored(app, db):
    settings_store.set(SETTINGS_KEY, json.dumps({"dashboard_income": "no", "currency": "GBP", "unknown": 1}))
    with app.test_request_context():
        current = current_settings()
    assert current["dashboard_income"] is True and current["currency"] == "GBP" and "unknown" not in current
    settings_store.set(SETTINGS_KEY, "not json")
    with app.test_request_context():
        assert current_settings() == DEFAULT_SETTINGS


def test_old_session_choices_still_apply_until_saved(client, db):
    with client.session_transaction() as session:
        session["settings"] = {**DEFAULT_SETTINGS, "dashboard_debt": False}
    assert "Debito Totale" not in client.get("/dashboard").get_data(as_text=True)
