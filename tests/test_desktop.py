"""F16: the desktop launcher's pieces that run anywhere (the full start is checked by the Desktop app workflow)."""
import json
import sys
from pathlib import Path

import pytest

from app import create_app
from desktop import database, main, paths


def test_health(client):
    assert client.get("/health").get_json() == {"ok": True}


def test_health_reports_a_broken_database(client, monkeypatch):
    from app.extensions import db

    def broken(*args, **kwargs):
        raise RuntimeError("gone")

    monkeypatch.setattr(db.session, "execute", broken)
    r = client.get("/health")
    assert r.status_code == 503 and r.get_json() == {"ok": False}


def test_desktop_config_and_instance_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("MFP_INSTANCE_PATH", str(tmp_path / "instance"))
    app = create_app("desktop")
    assert app.instance_path == str(tmp_path / "instance")
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax" and not app.config.get("LOGIN_DISABLED")
    assert Path(app.extensions["migrate"].directory).name == "migrations"


@pytest.mark.parametrize("platform, expected", [("win32", "Roaming"), ("darwin", "Application Support"),
                                                ("linux", ".local/share")])
def test_data_dir_per_system(monkeypatch, tmp_path, platform, expected):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for name in ("APPDATA", "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)
    path = paths.data_dir()
    assert expected in path.as_posix() and path.name == "MyFinancePlace" and path.is_dir()
    assert paths.data_dir(str(tmp_path / "altro")) == (tmp_path / "altro").resolve()


def test_postgres_binaries_are_found(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "bundle_dir", lambda: tmp_path / "none")
    monkeypatch.setattr(paths, "__file__", str(tmp_path / "desktop" / "paths.py"))
    monkeypatch.delenv("MFP_PG_BIN", raising=False)
    assert paths.postgres_bin() is None
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / ("pg_ctl.exe" if sys.platform.startswith("win") else "pg_ctl")).write_text("")
    monkeypatch.setenv("MFP_PG_BIN", str(tmp_path / "bin"))
    assert paths.postgres_bin() == tmp_path / "bin"
    assert paths.bundle_dir().name  # the repository when not frozen


def test_database_helpers(tmp_path):
    db = database.EmbeddedPostgres(tmp_path / "bin", tmp_path)
    assert not db.initialised()
    password = db.password
    assert len(password) > 20 and db.password == password  # made once, then kept
    db.port = 5555
    assert db.url() == f"postgresql://mfp:{password}@127.0.0.1:5555/myfinanceplace"
    assert 0 < database.free_port() < 65536


def test_launcher_helpers(tmp_path):
    assert main._already_open(tmp_path) is None
    (tmp_path / "running.json").write_text(json.dumps({"url": "http://127.0.0.1:9/"}))
    assert main._already_open(tmp_path) is None  # nothing answers there
    key = main._secret_key(tmp_path)
    assert len(key) > 40 and main._secret_key(tmp_path) == key
    args = main._arguments(["--headless", "--port", "8123"])
    assert args.headless and args.port == 8123 and not args.smoke


def test_missing_postgres_stops_early(monkeypatch, tmp_path):
    monkeypatch.setattr(main.paths, "postgres_bin", lambda: None)
    assert main.main(["--data-dir", str(tmp_path)]) == 2
