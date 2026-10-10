"""
F14: the desktop app starts with the computer (in the background) and shows the reminders as system notifications,
also the unread ones of the days it was closed. The parts that run anywhere; the window, the tray icon and the
Windows toast itself are checked by hand on Windows (docs/DESKTOP.md).
"""
import json
import sys
import types
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.client import Client
from app.models.wealth import Goal, InsurancePolicy
from app.services import autostart, desktop, notifications, settings_store, studio, system_notifications
from desktop import main, notify, tray, windows

TODAY = date.today()


@pytest.fixture()
def desktop_app(app, tmp_path, monkeypatch):
    """The app as the launcher configures it; starting with the computer goes to a fake."""
    calls = []
    monkeypatch.setattr(autostart, "enable", lambda command: calls.append(("on", command)))
    monkeypatch.setattr(autostart, "disable", lambda: calls.append(("off",)))
    monkeypatch.setattr(autostart, "is_enabled", lambda: bool(calls) and calls[-1][0] == "on")
    shown = []
    app.config.update(DESKTOP_DIR=str(tmp_path), DESKTOP_COMMAND=["C:/MFP/MyFinancePlace.exe"],
                      DESKTOP_TOKEN="secret-token", DESKTOP_SHOW=shown.append)
    app.autostart_calls, app.shown = calls, shown
    return app


def _policy(db, days, company="Unipol"):
    db.session.add(InsurancePolicy(type="Auto", company=company, premium=Decimal("300"),
                                   expiry_date=TODAY + timedelta(days=days)))
    db.session.commit()


def _run(app, today=TODAY):
    sent = []
    with app.test_request_context("/"):
        count = system_notifications.run(lambda m: sent.append(m) or True, today)
    assert count == len(sent)
    return sent


# ── Reminders as notifications ────────────────────────────────────────────────

def test_unread_reminders_are_sent_once_a_day_until_read(app, db):
    _policy(db, 5)
    first = _run(app)
    assert [m.title for m in first] == ["Polizza Auto · Unipol"] and "5 giorni" in first[0].body
    assert _run(app) == []  # already shown today
    assert len(_run(app, TODAY + timedelta(days=1))) == 1  # still unread the next day: shown again
    with app.test_request_context("/"):
        notifications.dismiss([n.key for n in notifications.collect()])
    assert _run(app, TODAY + timedelta(days=2)) == []  # read: no more


def test_reminders_of_the_days_the_app_was_closed_arrive_at_start(app, db):
    """A policy expired three days ago and never read: the first round after the start shows it."""
    _policy(db, -3)
    [message] = _run(app)
    assert "Scaduta" in message.body


def test_many_reminders_become_a_few_plus_a_count(app, db):
    for n in range(5):
        _policy(db, 3 + n, company=f"Compagnia {n}")
    sent = _run(app)
    assert len(sent) == system_notifications.MAX_SEPARATE
    assert sent[-1].title == "Altri 3 promemoria"
    with app.test_request_context("/"):
        shown = settings_store.get_json(system_notifications.SHOWN_SETTING, {})
    assert len(shown) == 5  # all of them count as shown, the summary covered the rest


def test_nothing_is_remembered_when_the_system_refuses(app, db):
    _policy(db, 5)
    with app.test_request_context("/"):
        assert system_notifications.run(lambda m: False, TODAY) == 0
    assert len(_run(app)) == 1  # tried again next round


def test_the_notification_opens_its_archive_on_its_page(desktop_app, client, db):
    _policy(db, 5)
    [message] = _run(desktop_app)
    with desktop_app.test_request_context("/"):
        client_id, path = desktop.read_link(message.link)
    assert client_id == studio.primary().id and path.startswith("/insurance/")
    response = client.get(f"/desktop/open/{message.link}")
    assert response.status_code == 302 and response.headers["Location"].endswith(path)
    assert client.get("/desktop/open/forged").headers["Location"].endswith("/notifications/")


def test_every_client_archive_is_checked_and_named(app, db, tmp_path):
    app.instance_path = str(tmp_path)
    with app.test_request_context("/"):
        rossi = studio.create("Mario Rossi")
    try:
        with app.test_request_context("/"), studio.using(rossi):
            db.session.add(Goal(name="Auto nuova", target_amount=Decimal("1000"), saved_amount=Decimal("10"),
                                target_date=TODAY + timedelta(days=10)))
        _policy(db, 5)
        titles = sorted(m.title for m in _run(app))
        assert titles == ["Archivio principale · Polizza Auto · Unipol", "Mario Rossi · Obiettivo «Auto nuova» tra 10 giorni"]
        rossi = db.session.get(Client, rossi.id)
        rossi.archived = True
        db.session.commit()
        assert [m.title for m in _run(app, TODAY + timedelta(days=1))] == ["Polizza Auto · Unipol"]  # one archive left
    finally:
        db.session.rollback()
        studio._drop(db.session.get(Client, rossi.id))


# ── Settings → App desktop ─────────────────────────────────────────────────────

def test_desktop_settings_only_in_the_desktop_app(client):
    assert client.get("/desktop/settings").status_code == 404
    assert "App desktop" not in client.get("/settings/").get_data(as_text=True)


def test_start_with_the_computer_and_notifications_switches(desktop_app, client, tmp_path):
    assert "App desktop" in client.get("/settings/").get_data(as_text=True)
    page = client.get("/desktop/settings").get_data(as_text=True)
    assert 'name="autostart"' in page and 'name="notify" checked' in page
    client.post("/desktop/settings", data={"autostart": "on"})
    assert desktop_app.autostart_calls[-1] == ("on", ["C:/MFP/MyFinancePlace.exe", "--background"])
    assert json.loads((tmp_path / "desktop.json").read_text()) == {"notify": False}
    assert 'name="autostart" checked' in client.get("/desktop/settings").get_data(as_text=True)
    client.post("/desktop/settings", data={"notify": "on"})
    assert desktop_app.autostart_calls[-1] == ("off",)
    assert desktop.read_prefs(tmp_path) == {"notify": True}


def test_autostart_failure_is_reported(desktop_app, client, monkeypatch):
    def denied(command):
        raise PermissionError("accesso negato")
    monkeypatch.setattr(autostart, "enable", denied)
    page = client.post("/desktop/settings", data={"autostart": "on"}, follow_redirects=True).get_data(as_text=True)
    assert "Avvio automatico non modificato" in page


def test_prefs_file_unreadable_or_odd(tmp_path):
    assert desktop.read_prefs(tmp_path) == {"notify": True}
    (tmp_path / "desktop.json").write_text("[1, 2]")
    assert desktop.read_prefs(tmp_path) == {"notify": True}
    (tmp_path / "desktop.json").write_text('{"notify": "no", "other": false}')
    assert desktop.read_prefs(tmp_path) == {"notify": True}


# ── Bringing the window up ─────────────────────────────────────────────────────

def test_quit_needs_the_launchers_token(desktop_app, client, monkeypatch):
    quits = []
    desktop_app.config["DESKTOP_QUIT"] = lambda: quits.append(True)
    monkeypatch.setattr("app.routes.desktop.threading.Timer",
                        lambda delay, hook: type("Now", (), {"start": staticmethod(hook)}))
    assert client.post("/desktop/quit", data={"token": "wrong"}).status_code == 404 and quits == []
    assert client.post("/desktop/quit", data={"token": "secret-token"}).status_code == 204 and quits == [True]


def test_show_needs_the_launchers_token(desktop_app, client, db):
    assert client.post("/desktop/show", data={"token": "wrong"}).status_code == 404
    assert client.post("/desktop/show", data={"token": "secret-token"}).status_code == 204
    assert desktop_app.shown == [""]
    with desktop_app.test_request_context("/"):
        link = desktop.open_link(studio.primary().id, "/budget/")
    client.post("/desktop/show", data={"token": "secret-token", "to": link})
    assert desktop_app.shown[-1] == f"/desktop/open/{link}"
    desktop_app.config["DESKTOP_TOKEN"] = ""
    assert client.post("/desktop/show", data={"token": ""}).status_code == 404


def test_links_must_be_signed_and_local(app):
    with app.test_request_context("/"):
        assert desktop.read_link(desktop.open_link(3, "/notifications/")) == (3, "/notifications/")
        assert desktop.read_link(desktop.open_link(3, "//evil.example")) is None
        assert desktop.read_link("garbage") is None


# ── The launcher's pieces ──────────────────────────────────────────────────────

def test_launcher_links_and_commands(app, monkeypatch, tmp_path):
    assert main.link_target("myfinanceplace://open/?to=abc.def") == "abc.def"
    assert main.link_target("https://example.com/?to=x") == "" and main.link_target(None) == ""
    assert main._arguments(["myfinanceplace://open/?to=x", "--background"]).background
    assert main.launch_command(None)[-2:] == ["-m", "desktop.main"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert main.launch_command("D:/dati") == [sys.executable, "--data-dir", "D:/dati"]
    assert main._ask_running({"url": "http://127.0.0.1:9/", "token": "t"}, "show", to="") is False
    assert main._stop(tmp_path, {"url": "http://127.0.0.1:9/", "token": "t"}) is False
    assert main.main(["--data-dir", str(tmp_path), "--stop"]) == 0  # nothing running: nothing to stop
    assert main._page(app, "") == ""
    assert main._page(app, "abc").endswith("/desktop/open/abc")


def test_reminders_follow_the_switch(app, db, tmp_path, monkeypatch):
    _policy(db, 5)
    shown = []
    monkeypatch.setattr(notify, "show", lambda title, body, link: shown.append(title) or True)
    (tmp_path / "desktop.json").write_text('{"notify": false}')
    assert main.send_reminders(app, tmp_path) == 0
    (tmp_path / "desktop.json").write_text('{"notify": true}')
    assert main.send_reminders(app, tmp_path) == 1 and shown == ["Polizza Auto · Unipol"]


def test_toast_text_is_escaped_and_clickable():
    xml = notify.toast_xml('Rata <Mutuo> & "casa"', "tra 3 giorni", "a.b-c")
    assert "&lt;Mutuo&gt; &amp;" in xml and 'launch="myfinanceplace://open/?to=a.b-c"' in xml
    assert 'activationType="protocol"' in xml


def test_notification_commands(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs.get("env") or {}))
        return types.SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(notify.subprocess, "run", fake_run)
    monkeypatch.setattr(notify.shutil, "which", lambda name: "/usr/bin/notify-send")
    monkeypatch.setattr(sys, "platform", "linux")
    assert notify.show("Titolo", "Testo", "x")
    assert calls[-1][0] == ["notify-send", "--app-name=MyFinancePlace", "Titolo", "Testo"]
    monkeypatch.setattr(sys, "platform", "darwin")
    assert notify.show("Titolo", "Testo", "x") and calls[-1][0][0] == "osascript"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(notify.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    assert notify.show("Titolo", "Testo", "x")
    command, env = calls[-1]
    assert command[0] == "powershell.exe" and "Titolo" in env["MFP_TOAST_XML"] and env["MFP_TOAST_APP"] == windows.APP_ID
    assert "Titolo" not in " ".join(command)  # the text never reaches the command line

    monkeypatch.setattr(notify.subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=1, stderr=b"no"))
    assert not notify.show("Titolo", "Testo", "x")

    def broken(*args, **kwargs):
        raise OSError("powershell missing")
    monkeypatch.setattr(notify.subprocess, "run", broken)
    assert not notify.show("Titolo", "Testo", "x")
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(notify.shutil, "which", lambda name: None)
    assert not notify.show("Titolo", "Testo", "x")


# ── Start with the computer, per system ───────────────────────────────────────

class FakeRegistry(types.SimpleNamespace):
    """Enough of winreg for the code above: keys are dicts in self.keys."""

    HKEY_CURRENT_USER, KEY_SET_VALUE, REG_SZ = "HKCU", 2, 1

    def __init__(self):
        super().__init__(keys={})

    class _Key:
        def __init__(self, store):
            self.store = store

        def __enter__(self):
            return self.store

        def __exit__(self, *exc):
            return False

    def CreateKey(self, root, path):  # noqa: N802 - winreg's names
        return self._Key(self.keys.setdefault(path, {}))

    def OpenKey(self, root, path, *args):  # noqa: N802
        if path not in self.keys:
            raise FileNotFoundError(path)
        return self._Key(self.keys[path])

    def SetValueEx(self, key, name, reserved, kind, value):  # noqa: N802
        key[name] = value

    def QueryValueEx(self, key, name):  # noqa: N802
        if name not in key:
            raise FileNotFoundError(name)
        return key[name], 1

    def DeleteValue(self, key, name):  # noqa: N802
        if name not in key:
            raise FileNotFoundError(name)
        del key[name]


def test_autostart_on_windows(monkeypatch):
    registry = FakeRegistry()
    monkeypatch.setitem(sys.modules, "winreg", registry)
    monkeypatch.setattr(sys, "platform", "win32")
    assert not autostart.is_enabled()
    autostart.enable([r"C:\Program Files\MFP\MyFinancePlace.exe", "--background"])
    assert registry.keys[autostart.RUN_KEY]["MyFinancePlace"] == r'"C:\Program Files\MFP\MyFinancePlace.exe" --background'
    assert autostart.is_enabled()
    autostart.disable()
    autostart.disable()  # already off: nothing to do
    assert not autostart.is_enabled()


def test_autostart_on_macos_and_linux(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    for platform in ("darwin", "linux"):
        monkeypatch.setattr(sys, "platform", platform)
        assert not autostart.is_enabled()
        autostart.enable(["/opt/MyFinancePlace", "--background"])
        assert autostart.is_enabled()
        autostart.disable()
        assert not autostart.is_enabled()
    autostart.enable(["/opt/My Finance", "--background"])
    assert "Exec='/opt/My Finance' --background" in (tmp_path / "config" / "autostart" / "myfinanceplace.desktop").read_text()


def test_windows_registration(monkeypatch, tmp_path):
    windows.register(tmp_path / "MyFinancePlace.exe", None)  # not Windows: nothing
    registry = FakeRegistry()
    ids = []
    shell32 = types.SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=ids.append)
    monkeypatch.setitem(sys.modules, "winreg", registry)
    monkeypatch.setattr(sys, "platform", "win32")
    import ctypes
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(shell32=shell32), raising=False)
    icon = tmp_path / "icon.ico"
    icon.write_bytes(b"ico")
    windows.register(tmp_path / "MyFinancePlace.exe", icon)
    assert ids == [windows.APP_ID]
    assert registry.keys[rf"Software\Classes\AppUserModelId\{windows.APP_ID}"] == {"DisplayName": "MyFinancePlace",
                                                                                     "IconUri": str(icon)}
    command = registry.keys[r"Software\Classes\myfinanceplace\shell\open\command"][""]
    assert command == f'"{tmp_path / "MyFinancePlace.exe"}" "%1"'

    def denied(*args):
        raise PermissionError("no")
    monkeypatch.setattr(registry, "CreateKey", denied)
    windows.register(tmp_path / "MyFinancePlace.exe", icon)  # logged, not raised


def test_tray_only_on_windows(monkeypatch):
    assert not tray.supported()  # these tests run on Linux
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "pystray", None)  # not installed
    assert not tray.supported()
