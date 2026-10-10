"""
Icons and charts are served by the app itself (no CDN: the desktop app works offline), and the icon font keeps only
the icons the app uses (scripts/icons.py): every icon named in the templates must be in it.
"""
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
ICONS_CSS = (APP / "static" / "vendor" / "icons" / "icons.css").read_text()


def _sources():
    yield from (APP / "templates").rglob("*.html")
    yield from (APP / "static" / "js").glob("*.js")


def test_every_icon_used_is_in_the_icon_subset():
    named = set()
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        named |= set(re.findall(r"\bbi-([a-z0-9]+(?:-[a-z0-9]+)*)\b(?!-)", text))
        named |= set(re.findall(r"kpi\('([a-z0-9]+(?:-[a-z0-9]+)*)'", text))  # the kpi macro adds the "bi-"
    missing = sorted(name for name in named if f".bi-{name}::before" not in ICONS_CSS)
    assert not missing, f"run scripts/icons.py again: {missing}"


def test_no_script_icon_or_font_from_a_cdn():
    for path in (APP / "templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert "cdn.jsdelivr" not in text and "fonts.googleapis" not in text, path


def test_the_font_is_chosen_in_settings(client):
    page = client.get("/settings/").get_data(as_text=True)
    assert 'data-font="inter"' in page and "vendor/fonts/fonts.css" in page
    assert 'name="font"' in page and "IBM Plex Sans" in page and "Atkinson Hyperlegible" in page
    client.post("/settings/save", data={"font": "plex"})
    assert 'data-font="plex"' in client.get("/dashboard").get_data(as_text=True)
    client.post("/settings/save", data={"font": "comic-sans"})  # not one of them: the default
    assert 'data-font="inter"' in client.get("/dashboard").get_data(as_text=True)
    for name in ("inter", "ibm-plex-sans", "atkinson-hyperlegible-next"):
        assert (APP / "static" / "vendor" / "fonts" / f"{name}.woff2").stat().st_size > 20_000
        assert "Open Font License" in (APP / "static" / "vendor" / "fonts" / f"LICENSE-{name}.txt").read_text()


def test_charts_load_only_on_pages_with_charts(client, sample_data):
    assert "chart.umd.min.js" not in client.get("/transactions/").get_data(as_text=True)
    page = client.get("/dashboard").get_data(as_text=True)
    assert "vendor/chart.umd.min.js" in page and "js/charts.js" in page
