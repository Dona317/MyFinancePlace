"""
The cards of an account (F41): a debit, credit or prepaid card charged on it — one account can have several. The
card is told by its name and last digits; its movements are the account's.
"""
from app.extensions import db


class Card(db.Model):
    __tablename__ = "cards"

    id         = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    name       = db.Column(db.Text, nullable=False)                     # «Visa Fineco», «Bancomat»
    kind       = db.Column(db.String(10), nullable=False, default="debit")  # see services.accounts.CARD_KINDS
    last4      = db.Column(db.String(4))                                 # the last digits, to recognise it
    position   = db.Column(db.Integer, nullable=False, default=0)

    account = db.relationship("Account", backref=db.backref("cards", order_by="Card.position", cascade="all, delete-orphan"))
