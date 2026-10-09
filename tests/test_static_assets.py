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


def test_no_script_or_icon_from_a_cdn():
    for path in (APP / "templates").rglob("*.html"):
        assert "cdn.jsdelivr" not in path.read_text(encoding="utf-8"), path


def test_charts_load_only_on_pages_with_charts(client, sample_data):
    assert "chart.umd.min.js" not in client.get("/transactions/").get_data(as_text=True)
    page = client.get("/dashboard").get_data(as_text=True)
    assert "vendor/chart.umd.min.js" in page and "js/charts.js" in page
