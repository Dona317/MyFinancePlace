from datetime import datetime

from app.extensions import db


class UtilityReading(db.Model):
    """One bill (F23): which utility, the period it covers, how much was used and what it cost."""
    __tablename__ = "utility_readings"

    id             = db.Column(db.Integer, primary_key=True)
    utility        = db.Column(db.String(20), nullable=False)    # power | gas | water | internet | waste
    supplier       = db.Column(db.Text)
    period_start   = db.Column(db.Date, nullable=False)
    period_end     = db.Column(db.Date, nullable=False)
    consumption    = db.Column(db.Numeric(14, 3))                # in the utility's unit; empty for a flat fee
    amount         = db.Column(db.Numeric(38, 2), nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id", ondelete="SET NULL"), index=True)
    document_id    = db.Column(db.Integer, db.ForeignKey("documents.id", ondelete="SET NULL"))
    notes          = db.Column(db.Text)
    created_at     = db.Column(db.DateTime, nullable=False, default=datetime.now)

    transaction = db.relationship("Transaction")
    document = db.relationship("Document")
