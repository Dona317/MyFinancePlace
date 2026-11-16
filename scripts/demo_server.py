"""
The app on the demo data, with a user of its own, to look at the pages after a change without touching the real
archive or asking for the real password.

    python scripts/demo_server.py            # http://127.0.0.1:5055, user and password below
    python scripts/demo_server.py --reset    # the demo database made again from the 3-year backup

It works on a database of its own — the name of DATABASE_URL with «_demo» added (myfinanceplace → myfinanceplace_demo),
or DEMO_DATABASE_URL — and on a data folder of its own (instance_demo/, not in the repository). The first time it
creates the database, brings it to the current schema, restores docs/Transaction samples/dati_fittizi/
backup_completo_3anni.zip and adds the user. It never runs on a database whose name does not end with «_demo», and
it listens on this machine only.

The user exists only in the demo database and its data are invented: the password is here on purpose.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

DEMO_USER = "demo"
DEMO_PASSWORD = "demo-solo-dati-finti-2026"  # noqa: S105 - a local demo database of invented data
PORT = int(os.environ.get("DEMO_PORT") or 5055)
BACKUP = ROOT / "docs" / "Transaction samples" / "dati_fittizi" / "backup_completo_3anni.zip"


def demo_url():
    load_dotenv(ROOT / ".env")
    if os.environ.get("DEMO_DATABASE_URL"):
        url = make_url(os.environ["DEMO_DATABASE_URL"])
    else:
        real = make_url(os.environ.get("DATABASE_URL") or "postgresql://sa:Pa55w0rd@localhost:5332/myfinanceplace")
        url = real.set(database=f"{real.database}_demo")
    if not (url.database or "").endswith("_demo"):
        raise SystemExit(f"Refusing to use «{url.database}»: the demo database must have a name ending with _demo.")
    return url


def ensure_database(url, reset: bool) -> None:
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}).scalar()
        if exists and reset:
            connection.execute(text(f'DROP DATABASE "{url.database}" WITH (FORCE)'))
            exists = False
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


def main() -> None:
    url = demo_url()
    ensure_database(url, reset="--reset" in sys.argv)
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    os.environ["MFP_INSTANCE_PATH"] = str(ROOT / "instance_demo")
    os.environ.setdefault("SECRET_KEY", "demo-server-not-a-secret")

    from flask_migrate import upgrade

    from app import create_app
    from app.extensions import db
    from app.models.transaction import Transaction
    from app.services import backup, users

    app = create_app()
    with app.app_context():
        upgrade()
        if not db.session.query(Transaction.id).first():
            data, files = backup.read_upload(BACKUP.read_bytes())
            backup.restore(data, files)
        if users.find(DEMO_USER) is None:
            users.create(DEMO_USER, DEMO_PASSWORD, is_admin=True)
        db.session.remove()
    print(f"Demo: http://127.0.0.1:{PORT}  ·  user «{DEMO_USER}»  ·  database «{url.database}»", flush=True)
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
