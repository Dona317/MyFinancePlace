"""
The closing of a year: the three statements (balance sheet at 31 December, income statement, cash flow) saved as
they were, made by itself on the first visit of the new year. Changing a transaction of a closed year afterwards is
seen (the fingerprint of the transactions differs) and the statements can be saved again: a new version, the older
ones kept.
"""
from datetime import datetime

from app.extensions import db


class YearClose(db.Model):
    __tablename__ = "year_closes"
    __table_args__ = (db.UniqueConstraint("year", "version", name="uq_year_closes_year_version"),)

    id          = db.Column(db.Integer, primary_key=True)
    year        = db.Column(db.Integer, nullable=False, index=True)
    version     = db.Column(db.Integer, nullable=False, default=1)
    closed_at   = db.Column(db.DateTime, nullable=False, default=datetime.now)
    automatic   = db.Column(db.Boolean, nullable=False, default=True)  # made on 1 January, or asked by the user
    fingerprint = db.Column(db.String(32), nullable=False)  # of the transactions up to 31 December when saved
    data        = db.Column(db.JSON, nullable=False)        # {"balance_sheet": …, "income_statement": …, "cash_flow": …}
