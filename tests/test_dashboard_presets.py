"""The three presets of the dashboard: blocks, cards and period, each saved on request and renamable."""
from datetime import date

from app.services import dashboard_prefs


def _active(html: str) -> str:
    start = html.index("preset-btn is-active")
    return html[html.index(">", start) + 1:html.index("</button>", start)].strip()


def test_first_preset_keeps_the_page_as_it_was_and_the_others_start_from_the_default(client, db):
    client.post("/dashboard/layout", json={"widgets": [{"id": "health", "span": 3}]})
    data = dashboard_prefs.presets()
    assert data["active"] == 1
    assert data["items"][0]["layout"][0] == {"id": "health", "span": 3, "height": 0, "visible": True}
    assert data["items"][1]["layout"] == dashboard_prefs.default_layout()
    assert [p["name"] for p in data["items"]] == ["Preset 1", "Preset 2", "Preset 3"]
    html = client.get("/dashboard").get_data(as_text=True)
    assert _active(html) == "Preset 1" and 'id="preset-save" hidden' in html


def test_a_preset_saves_blocks_cards_and_period_and_brings_them_back(client, db):
    year = date.today().year
    # another period on the page: «Salva preset» appears
    html = client.get(f"/dashboard?year={year - 1}&year_to={year - 1}&part=Q2").get_data(as_text=True)
    assert 'id="preset-save" hidden' not in html
    client.post("/dashboard/layout", json={"widgets": [{"id": "recent", "span": 3, "visible": False}],
                                           "kpis": [{"id": "debt", "span": 2}]})
    saved = client.post("/dashboard/presets/2/save", json={"period": {"year": year - 1, "year_to": year - 1, "part": "Q2"}}).get_json()
    assert saved["period"] == {"year": year - 1, "year_to": year - 1, "part": "Q2"}
    # preset 1: the default arrangement and the current year
    assert client.post("/dashboard/presets/1/use").get_json() == {"url": "/dashboard"}
    html = client.get("/dashboard").get_data(as_text=True)
    assert _active(html) == "Preset 1" and f'<option value="{year}" selected' in html
    assert dashboard_prefs.layout()[0]["id"] == "cashflow"
    # back to preset 2: its blocks, cards and period, nothing to save
    client.post("/dashboard/presets/2/use")
    html = client.get("/dashboard").get_data(as_text=True)
    assert _active(html) == "Preset 2" and f'<option value="{year - 1}" selected' in html
    assert '<option value="Q2" selected' in html and 'id="preset-save" hidden' in html
    assert dashboard_prefs.layout()[0] == {"id": "recent", "span": 3, "height": 0, "visible": False}
    assert dashboard_prefs.kpi_layout()[0] == {"id": "debt", "span": 2, "visible": True}
    # a block moved in Modifica: the page differs from the preset
    client.post("/dashboard/layout", json={"widgets": [{"id": "health"}]})
    assert 'id="preset-save" hidden' not in client.get("/dashboard").get_data(as_text=True)


def test_presets_are_renamed_and_a_blank_name_goes_back_to_the_default(client, db):
    assert client.post("/dashboard/presets/3/rename", json={"name": "  Investimenti  "}).get_json() == {"name": "Investimenti"}
    assert client.post("/dashboard/presets/1/rename", json={"name": "x" * 50}).get_json() == {"name": "x" * 30}
    assert "Investimenti" in client.get("/dashboard").get_data(as_text=True)
    assert client.post("/dashboard/presets/3/rename", json={"name": " "}).get_json() == {"name": "Preset 3"}


def test_wrong_requests_are_refused(client, db):
    assert client.post("/dashboard/presets/4/use").status_code == 400
    assert client.post("/dashboard/presets/0/save", json={}).status_code == 400
    assert client.post("/dashboard/presets/1/save", data="x").status_code == 400
    assert client.post("/dashboard/presets/1/rename", data="x").status_code == 400
    assert client.post("/dashboard/presets/9/rename", json={"name": "a"}).status_code == 400


def test_saved_periods_and_presets_are_cleaned(app, db):
    clean = dashboard_prefs._clean_period
    assert clean({"year": 2026, "year_to": 2024, "part": "Q1"}) == {"year": 2024, "year_to": 2026, "part": "year"}
    assert clean({"year": 2025, "part": "H2"}) == {"year": 2025, "year_to": 2025, "part": "H2"}
    assert clean({"year": "x"}) is None and clean({"year": 10}) is None and clean("2026") is None
    dashboard_prefs.settings_store.set_json(dashboard_prefs.PRESETS_SETTING, {"active": 7, "items": "nope"})
    data = dashboard_prefs.presets()
    assert data["active"] == 1 and len(data["items"]) == 3 and data["items"][2]["period"] is None
    assert dashboard_prefs.preset_period(data["items"][0], date(2030, 5, 1)) == {"year": 2030, "year_to": 2030, "part": "year"}
