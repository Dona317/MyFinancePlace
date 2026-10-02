from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db

MIN_PASSWORD = 8


class User(UserMixin, db.Model):
    """Someone who can open the app. The data is shared: every user sees the same accounts and transactions."""
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin      = db.Column(db.Boolean, nullable=False, default=False)  # can add and remove users
    created_at    = db.Column(db.DateTime, nullable=False, default=datetime.now)
    last_login    = db.Column(db.DateTime)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password or "")

    def __repr__(self):
        return f"<User {self.username}>"
