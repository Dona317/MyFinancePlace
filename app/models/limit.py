"""
Contribution limits (F22): how much can go into something each year — the deductible 5.164,57 € of a pension fund,
the 40.000 € a year (200.000 € in all) of a PIR — and how much has gone in so far.
"""
from sqlalchemy.dialects.postgresql import ARRAY

from app.extensions import db


class ContributionLimit(db.Model):
    __tablename__ = "contribution_limits"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.Text, nullable=False)
    kind        = db.Column(db.String(20), nullable=False, default="custom")  # see services.contribution_limits.PRESETS
    yearly      = db.Column(db.Numeric(38, 2), nullable=False)                # the limit of each calendar year
    total       = db.Column(db.Numeric(38, 2))                                 # a lifetime limit, when there is one
    since_year  = db.Column(db.Integer)                                       # first year counted in the total
    # what the money goes into: accounts it arrives on, holdings it buys, or a category of expenses
    account_ids = db.Column(ARRAY(db.Integer), nullable=False, default=list, server_default="{}")
    holding_ids = db.Column(ARRAY(db.Integer), nullable=False, default=list, server_default="{}")
    category    = db.Column(db.Text)
    notes       = db.Column(db.Text)
