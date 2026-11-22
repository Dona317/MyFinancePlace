"""`python run.py` brings the databases up to date before serving (22 Nov 2026): after a git pull, a restart is enough."""
import runpy
from pathlib import Path

import run

ROOT = Path(__file__).resolve().parents[1]


def test_the_development_server_upgrades_every_database_first(monkeypatch):
    calls = []
    monkeypatch.setattr("flask_migrate.upgrade", lambda directory: calls.append(("studio", directory)))
    monkeypatch.setattr("app.services.studio.migrate_all", lambda: calls.append(("archives",)) or ["rossi"])
    assert run.upgrade_databases(run.app) == ["rossi"]
    assert calls[0][0] == "studio" and calls[0][1].endswith("migrations") and calls[1] == ("archives",)


def test_run_py_upgrades_once_then_serves(monkeypatch, capsys):
    steps = []
    monkeypatch.setattr("flask_migrate.upgrade", lambda directory: steps.append("upgrade"))
    monkeypatch.setattr("app.services.studio.migrate_all", lambda: [])
    monkeypatch.setattr("flask.Flask.run", lambda self, **kw: steps.append("serve"))
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    runpy.run_path(str(ROOT / "run.py"), run_name="__main__")
    assert steps == ["upgrade", "serve"] and "archivi dei clienti aggiornati: nessuno" in capsys.readouterr().out
    steps.clear()
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")  # the reloader's server process: already done by the watcher
    runpy.run_path(str(ROOT / "run.py"), run_name="__main__")
    assert steps == ["serve"]
