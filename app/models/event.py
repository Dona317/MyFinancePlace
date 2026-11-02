"""
Spending events (F20): a trip, a wedding, a renovation — movements of different categories gathered under one name,
with their own budget, so the extraordinary spending is seen as a whole and apart from the ordinary one.
"""
from app.extensions import db


class SpendingEvent(db.Model):
    __tablename__ = "spending_events"

    id     = db.Column(db.Integer, primary_key=True)
    name   = db.Column(db.Text, nullable=False)
    start  = db.Column(db.Date, nullable=False)
    end    = db.Column(db.Date)                       # empty = a single day
    budget = db.Column(db.Numeric(38, 2))
    notes  = db.Column(db.Text)
