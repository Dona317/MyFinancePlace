from app.extensions import db
from sqlalchemy.dialects.postgresql import ARRAY


class Transaction(db.Model):
    __tablename__ = "transactions"

    id             = db.Column(db.Integer,        primary_key=True)
    date           = db.Column(db.Date,           nullable=False)
    description    = db.Column(db.Text,           nullable=False)
    amount         = db.Column(db.Numeric(38, 2), nullable=False)  # 36 integer digits: no practical limit
    currency       = db.Column(db.String(3),      default="EUR")
    amount_base    = db.Column(db.Numeric(38, 2))  # value in euro on its date (services.currency fills it)
    type           = db.Column(db.String(20))     # "income" | "expense" | "transfer"
    category       = db.Column(db.Text)
    counterparty   = db.Column(db.Text)
    tags           = db.Column(ARRAY(db.String),  default=list)
    is_recurring   = db.Column(db.Boolean,        default=False)
    recurrence     = db.Column(db.String(20))     # "weekly" | "monthly" | "quarterly" | "yearly"
    recurrence_end = db.Column(db.Date)
    notes          = db.Column(db.Text)
    bank_description = db.Column(db.Text)       # the bank's original causale, kept as imported (never edited)
    import_ref     = db.Column(db.String(64), unique=True, index=True)  # fingerprint of a bank-statement row
    # The account the money leaves (expense, outgoing transfer) or reaches (income); for a transfer between
    # two own accounts, counter_account is where it arrives
    account_id         = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"), index=True)
    counter_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"), index=True)

    account         = db.relationship("Account", foreign_keys=[account_id], lazy="joined")
    counter_account = db.relationship("Account", foreign_keys=[counter_account_id], lazy="joined")

    @property
    def magnitude(self) -> float:
        """Value in euro as a positive number (the direction comes from `type`): what totals add up."""
        return abs(float(self.amount_base if self.amount_base is not None else self.amount or 0))

    @property
    def signed_amount(self) -> float:
        """Negative for expenses, positive otherwise: how the amount is shown and summed in a balance."""
        return -self.magnitude if self.type == "expense" else self.magnitude

    def __repr__(self):
        return f"<Transaction {self.id} {self.description}>"
