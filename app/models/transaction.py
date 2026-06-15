from app.extensions import db
from sqlalchemy.dialects.postgresql import ARRAY


class Transaction(db.Model):
    __tablename__ = "transactions"

    id             = db.Column(db.Integer,        primary_key=True)
    date           = db.Column(db.Date,           nullable=False)
    description    = db.Column(db.String(255),    nullable=False)
    amount         = db.Column(db.Numeric(12, 2), nullable=False)
    currency       = db.Column(db.String(3),      default="EUR")
    type           = db.Column(db.String(20))     # "income" | "expense" | "transfer"
    category       = db.Column(db.String(100))
    counterparty   = db.Column(db.String(255))
    tags           = db.Column(ARRAY(db.String),  default=list)
    is_recurring   = db.Column(db.Boolean,        default=False)
    recurrence     = db.Column(db.String(20))     # "weekly" | "monthly" | "quarterly" | "yearly"
    recurrence_end = db.Column(db.Date)
    notes          = db.Column(db.Text)

    def __repr__(self):
        return f"<Transaction {self.id} {self.description}>"
