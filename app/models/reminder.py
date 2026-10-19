"""
Deadlines written by hand (F23): the car tax, the MOT, the service, a yearly subscription paid by cash — anything the
app cannot read from the movements. Once, every month or every year from the first date.
"""
from datetime import datetime

from app.extensions import db


class Reminder(db.Model):
    __tablename__ = "reminders"

    id         = db.Column(db.Integer, primary_key=True)
    title      = db.Column(db.Text, nullable=False)
    due        = db.Column(db.Date, nullable=False)             # the first (or only) date
    repeat     = db.Column(db.String(10), nullable=False, default="none")  # none | monthly | yearly
    amount     = db.Column(db.Numeric(38, 2))
    notes      = db.Column(db.Text)
    done       = db.Column(db.Boolean, nullable=False, default=False)  # a one-off already dealt with
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
