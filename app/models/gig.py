"""
Odd jobs and occasional work (F22): who it was for, when, the hours, the gross fee and the 20 % withholding tax when
the client is a withholding agent, how it is paid and whether it has been. They are «redditi diversi» on the tax
return; above 5.000 € a year from occasional work the INPS gestione separata applies.
"""
from datetime import datetime

from app.extensions import db


class Gig(db.Model):
    __tablename__ = "gigs"

    id              = db.Column(db.Integer, primary_key=True)
    client          = db.Column(db.Text, nullable=False)           # who it was for
    description     = db.Column(db.Text, nullable=False)
    owner           = db.Column(db.String(80))                     # who did it (a holder), empty = the family
    date            = db.Column(db.Date, nullable=False)
    hours           = db.Column(db.Numeric(9, 2))
    gross           = db.Column(db.Numeric(38, 2), nullable=False)
    withholding_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)  # 20 with a withholding agent
    expenses        = db.Column(db.Numeric(38, 2), nullable=False, default=0)  # costs of the job (deductible)
    method          = db.Column(db.String(20), nullable=False, default="transfer")  # cash | transfer | other
    paid_on         = db.Column(db.Date)
    transaction_id  = db.Column(db.Integer, db.ForeignKey("transactions.id", ondelete="SET NULL"))
    notes           = db.Column(db.Text)
    created_at      = db.Column(db.DateTime, nullable=False, default=datetime.now)

    transaction = db.relationship("Transaction")
