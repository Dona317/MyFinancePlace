from datetime import datetime

from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import ARRAY
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db

MIN_PASSWORD = 8


class User(UserMixin, db.Model):
    """Someone who can open the app. The data is shared; an administrator can block sections of the app for a user."""
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin      = db.Column(db.Boolean, nullable=False, default=False)  # can add and remove users
    created_at    = db.Column(db.DateTime, nullable=False, default=datetime.now)
    last_login    = db.Column(db.DateTime)
    # sections of the menu (services/sections.py): blocked by an administrator, hidden by the user from their menu
    blocked_sections = db.Column(ARRAY(db.String(40)), nullable=False, default=list, server_default="{}")
    hidden_sections  = db.Column(ARRAY(db.String(40)), nullable=False, default=list, server_default="{}")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password or "")

    def __repr__(self):
        return f"<User {self.username}>"
