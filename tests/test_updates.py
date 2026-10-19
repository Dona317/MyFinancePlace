"""F23: the version of the app and the notice of a newer release (GitHub's answer is faked)."""
import io
import json
import urllib.error
from datetime import date, timedelta

from app.services import notifications, updates
from app.version import __version__
from desktop import main


def test_versions_compare():
    assert updates.parse("v1.2.10") == (1, 2, 10) > updates.parse("1.2.9")
    assert updates.parse("2.0.0-beta") == (2, 0, 0) and updates.parse("nonsense") == ()
    assert updates.parse(__version__) >= (1, 0, 0)


def test_check_once_a_day(tmp_path):
    calls = []

    def fetch():
        calls.append(1)
        return {"tag_name": "v99.0.0", "html_url": "https://github.com/x/releases/tag/v99.0.0"}
    today = date(2026, 10, 19)
    found = updates.check(tmp_path, today, fetch)
    assert found["version"] == "99.0.0" and calls == [1]
    assert updates.check(tmp_path, today, fetch)["checked"] == "2026-10-19" and calls == [1]  # asked once a day
    assert updates.newer(tmp_path)["url"].endswith("v99.0.0")
    assert updates.check(tmp_path, today + timedelta(days=1), lambda: None)["checked"] == "2026-10-19"  # offline
    updates.check(tmp_path, today + timedelta(days=1), lambda: {})  # no release published
    assert updates.newer(tmp_path) is None and updates.stored(tmp_path)["url"] == updates.RELEASES_PAGE
    updates.check(tmp_path, today + timedelta(days=2), lambda: {"tag_name": f"v{__version__}"})
    assert updates.newer(tmp_path) is None
    (tmp_path / updates.FILE).write_text("[1, 2]")
    assert updates.stored(tmp_path) == {}


def test_fetch(monkeypatch):
    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False
    seen = {}

    def opened(request, timeout):
        seen.update(url=request.full_url, agent=request.get_header("User-agent"))
        return Answer(json.dumps({"tag_name": "v2.0.0"}).encode())
    monkeypatch.setattr(updates.urllib.request, "urlopen", opened)
    assert updates._fetch() == {"tag_name": "v2.0.0"} and seen["url"] == updates.LATEST_URL
    assert seen["agent"] == f"MyFinancePlace/{__version__}"

    def failing(code):
        def raise_(request, timeout):
            if code:
                raise urllib.error.HTTPError(updates.LATEST_URL, code, "x", {}, None)
            raise urllib.error.URLError("offline")
        return raise_
    monkeypatch.setattr(updates.urllib.request, "urlopen", failing(404))
    assert updates._fetch() == {}
    monkeypatch.setattr(updates.urllib.request, "urlopen", failing(500))
    assert updates._fetch() is None
    monkeypatch.setattr(updates.urllib.request, "urlopen", failing(0))
    assert updates._fetch() is None


def test_desktop_round_settings_and_notice(app, client, tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "_fetch", lambda: {"tag_name": "v99.1.0", "html_url": "https://example.org/r"})
    assert main.check_updates(tmp_path)["version"] == "99.1.0"
    (tmp_path / "desktop.json").write_text(json.dumps({"updates": False}))
    assert main.check_updates(tmp_path) is None
    with app.test_request_context("/"):
        assert not [n for n in notifications.collect() if n.key.startswith("update-")]  # not the desktop app
    app.config.update(DESKTOP_DIR=str(tmp_path), DESKTOP_COMMAND=["MyFinancePlace"])
    with app.test_request_context("/"):
        assert not [n for n in notifications.collect() if n.key.startswith("update-")]  # switched off
    (tmp_path / "desktop.json").write_text(json.dumps({"updates": True}))
    with app.test_request_context("/"):
        found = [n for n in notifications.collect() if n.key.startswith("update-")]
    assert found[0].title == "Disponibile la versione 99.1.0" and found[0].url.endswith("#version")
    page = client.get("/desktop/settings").get_data(as_text=True)
    assert f"versione {__version__}" in page and "versione 99.1.0" in page and "https://example.org/r" in page
    assert 'name="updates" checked' in page
    (tmp_path / updates.FILE).write_text(json.dumps({"checked": "2026-10-19", "version": __version__}))
    page = client.get("/desktop/settings").get_data(as_text=True)
    assert "È la più recente" in page
