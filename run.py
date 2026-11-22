"""Development server: `python run.py` (http://localhost:5000).

At start the databases are brought up to date, like the desktop app does: the studio database (the primary archive)
and every client's archive. After a `git pull` that adds a migration, restarting is enough.
"""
import os

from app import create_app

app = create_app()


def upgrade_databases(application) -> list[str]:
    """Apply the migrations not yet applied to the studio database and to every client archive; returns the archives
    migrated (their slugs)."""
    from flask_migrate import upgrade

    from app.services import studio

    with application.app_context():
        upgrade(directory=application.extensions["migrate"].directory)
        return studio.migrate_all()


if __name__ == "__main__":
    # with the reloader the file runs twice (the watcher, then the server): the databases are upgraded once, first
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        archives = upgrade_databases(app)
        print(f" * Database aggiornato; archivi dei clienti aggiornati: {', '.join(archives) or 'nessuno'}")
    app.run(debug=True)
