from datetime import datetime

from app.extensions import db


class Client(db.Model):
    """A client of the studio (F11). Each one has an archive of its own: a separate PostgreSQL database with all the
    accounts, transactions, settings… and a folder for documents and backups. The primary client is the studio's
    own database (the archive that existed before clients did); it cannot be deleted.

    The table lives in the studio database, next to the users (see services/studio.py)."""
    __tablename__ = "clients"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(120), nullable=False)
    slug       = db.Column(db.String(40), nullable=False, unique=True)  # [a-z0-9_]: folder and database name
    database   = db.Column(db.String(63))  # None: the studio database itself (the primary client)
    color      = db.Column(db.String(7), nullable=False, default="#2563eb")
    notes      = db.Column(db.Text)
    archived   = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    @property
    def is_primary(self) -> bool:
        return self.database is None

    @property
    def initials(self) -> str:
        words = [w for w in self.name.split() if w[:1].isalnum()]
        return ("".join(w[0] for w in words[:2]) or self.name[:1] or "?").upper()

    def __repr__(self):
        return f"<Client {self.slug}>"
