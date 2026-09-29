from datetime import datetime

from app.extensions import db


class Category(db.Model):
    """A transaction category the user can rename, merge, add or remove (Settings → Categorie)."""
    __tablename__ = "categories"

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.Text, nullable=False, unique=True)
    kind          = db.Column(db.String(10), nullable=False, default="expense")  # "expense" | "income" | "both"
    hint          = db.Column(db.Text)       # what it covers: shown to the user and given to the AI classifier
    discretionary = db.Column(db.Boolean, nullable=False, default=False)  # non-essential spending (Lifestyle)
    position      = db.Column(db.Integer, nullable=False, default=0)


class CategoryRule(db.Model):
    """
    "Transactions whose description or counterparty contains this word go to this category".
    Written by the user, or learned when the user corrects a category; they win over the built-in rules.
    """
    __tablename__ = "category_rules"

    id         = db.Column(db.Integer, primary_key=True)
    keyword    = db.Column(db.Text, nullable=False, unique=True)   # normalized: lowercase words and numbers
    category   = db.Column(db.Text, nullable=False)
    source     = db.Column(db.String(10), nullable=False, default="manual")  # "manual" | "learned"
    hits       = db.Column(db.Integer, nullable=False, default=0)            # transactions categorized by it
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
