"""
Payment cards (F41): debit, credit and prepaid cards, each charged on an account: name, circuit, last four digits,
expiry, holder, limit; the full number only encrypted (services.field_crypto), never the CVV or the PIN.
Movements can say which card paid them (Transaction.card_id).
"""
from datetime import datetime

from app.extensions import db


class Card(db.Model):
    __tablename__ = "cards"

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.Text, nullable=False)           # «Visa Fineco», «Bancomat Intesa»
    kind          = db.Column(db.String(10), nullable=False, default="debit")  # debit | credit | prepaid
    network       = db.Column(db.String(12))                     # visa | mastercard | maestro | amex | bancomat | other
    last4         = db.Column(db.String(4))                      # the last four digits, to recognize it
    number_enc    = db.Column(db.Text)                           # the full number, encrypted (AES-256-GCM); may be empty
    expiry_month  = db.Column(db.SmallInteger)
    expiry_year   = db.Column(db.SmallInteger)
    holder        = db.Column(db.String(80))                     # whose name is on it (F20 holders)
    account_id    = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"), index=True)  # charged on
    credit_limit  = db.Column(db.Numeric(14, 2))                 # credit and prepaid: the monthly limit / top-up cap
    statement_day = db.Column(db.SmallInteger)                   # credit: the day the month's total is charged
    contactless   = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    notes         = db.Column(db.Text)
    active        = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    account = db.relationship("Account", backref=db.backref("cards", lazy="select", order_by="Card.name"))
