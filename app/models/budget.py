from app.extensions import db


class Budget(db.Model):
    """How much the user wants to spend on a category: every month (month empty) or in one specific month."""
    __tablename__ = "budgets"

    id       = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.Text, nullable=False, index=True)
    month    = db.Column(db.Date)                              # first day of the month; empty = every month
    amount   = db.Column(db.Numeric(38, 2), nullable=False)
