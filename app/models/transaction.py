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
    # When the transaction's currency is not the account's: what the bank actually charged (or credited, on the
    # counter account of a transfer) in the account's currency. Empty = estimated with the day's exchange rate.
    account_amount     = db.Column(db.Numeric(38, 2))
    counter_amount     = db.Column(db.Numeric(38, 2))

    # What the money is for, when it matters to the cash-flow statement: buying/selling an investment
    # (investing) or receiving/repaying a loan (financing)
    holding_id = db.Column(db.Integer, db.ForeignKey("holdings.id", ondelete="SET NULL"), index=True)
    # An investment trade entered in units (F17): units bought (negative: sold) at a price per unit
    units      = db.Column(db.Numeric(38, 8))
    unit_price = db.Column(db.Numeric(38, 6))
    # A broker commission: the trade it was charged for (deleted with it)
    fee_for_id = db.Column(db.Integer, db.ForeignKey("transactions.id", ondelete="CASCADE"), index=True)
    debt_id    = db.Column(db.Integer, db.ForeignKey("debts.id", ondelete="SET NULL"), index=True)

    # loaded on first use (only the account page shows them): joining them on every query slowed down
    # the pages that read the whole history
    account         = db.relationship("Account", foreign_keys=[account_id])
    counter_account = db.relationship("Account", foreign_keys=[counter_account_id])
    # A split transaction: its amount divided across categories (70 Spesa + 30 Casa); `category` is then the
    # category of the largest part, so lists and filters keep working
    fee_for = db.relationship("Transaction", remote_side=[id], foreign_keys=[fee_for_id])
    splits = db.relationship("TransactionSplit", back_populates="transaction", cascade="all, delete-orphan",
                             passive_deletes=True, order_by="TransactionSplit.id")

    def parts(self) -> list[tuple[str | None, float]]:
        """(category, value in euro) of each part: the splits, or the whole transaction under its category."""
        if not self.splits:
            return [(self.category, self.magnitude)]
        whole = abs(float(self.amount or 0))
        return [(s.category, self.magnitude * abs(float(s.amount)) / whole if whole else 0.0) for s in self.splits]

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


class TransactionSplit(db.Model):
    """One part of a split transaction: a category and its amount (positive, in the transaction's currency)."""
    __tablename__ = "transaction_splits"

    id             = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True)
    category       = db.Column(db.Text)
    amount         = db.Column(db.Numeric(38, 2), nullable=False)

    transaction = db.relationship("Transaction", back_populates="splits")
