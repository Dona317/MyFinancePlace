"""
Money between people (F22): lent, advanced for someone, borrowed, given back. Each entry is signed — positive when the
other person owes more (I lent or paid for them), negative when they owe less or I owe them (they gave back, they lent
to me) — so a person's balance is the sum of their entries.
"""
from datetime import datetime

from app.extensions import db


class PersonalLoan(db.Model):
    __tablename__ = "personal_loans"

    id             = db.Column(db.Integer, primary_key=True)
    person         = db.Column(db.Text, nullable=False, index=True)
    date           = db.Column(db.Date, nullable=False)
    amount         = db.Column(db.Numeric(38, 2), nullable=False)   # + they owe me more, − they owe me less / I owe
    description    = db.Column(db.Text)
    due            = db.Column(db.Date)                             # when it should be settled
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id", ondelete="SET NULL"))
    created_at     = db.Column(db.DateTime, nullable=False, default=datetime.now)

    transaction = db.relationship("Transaction")
