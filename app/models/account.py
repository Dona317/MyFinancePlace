from app.extensions import db


class Account(db.Model):
    """A bank account, card, savings account or cash wallet the transactions belong to."""
    __tablename__ = "accounts"

    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.Text, nullable=False, unique=True)
    kind             = db.Column(db.String(20), nullable=False, default="current")  # see services.accounts.KINDS
    currency         = db.Column(db.String(3), nullable=False, default="EUR")
    opening_balance  = db.Column(db.Numeric(38, 2), nullable=False, default=0)    # before its first transaction
    iban_tail        = db.Column(db.String(10))                                     # last digits, to recognize it
    notes            = db.Column(db.Text)
    active           = db.Column(db.Boolean, nullable=False, default=True)
    reconciled_on    = db.Column(db.Date)            # last time the balance was checked against a statement
    reconciled_balance = db.Column(db.Numeric(38, 2))  # the balance the statement showed that day
