"""
Bank connections through PSD2 (F107): the consent the user gave a bank through the Enable Banking aggregator, and the
bank's accounts it covers, each tied to an account of the app. The movements they bring are ordinary transactions
(tag «psd2»); what still waits for the user's look is kept on the account link (`pending`).
"""
from datetime import datetime

from app.extensions import db


class BankConnection(db.Model):
    """One consent at one bank (ASPSP): valid until `valid_until` (90–180 days, set by the bank), then renewed."""
    __tablename__ = "bank_connections"

    id           = db.Column(db.Integer, primary_key=True)
    provider     = db.Column(db.String(20), nullable=False, default="enablebanking")
    aspsp_name   = db.Column(db.String(120), nullable=False)    # the bank as the aggregator names it («Fineco»)
    aspsp_country = db.Column(db.String(2), nullable=False, default="IT")
    session_enc  = db.Column(db.Text)                           # the aggregator's session id, encrypted (field_crypto)
    valid_until  = db.Column(db.DateTime)                       # end of the consent (UTC)
    status       = db.Column(db.String(12), nullable=False, default="active")  # active | expired | revoked | error
    last_error   = db.Column(db.Text)                           # what went wrong on the last download, for the page
    auto_sync    = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    # True: new movements that look like nothing saved are saved by the automatic download; the others wait for
    # a look. False: everything waits in the preview
    auto_save    = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    links = db.relationship("BankAccountLink", back_populates="connection", cascade="all, delete-orphan",
                            passive_deletes=True, order_by="BankAccountLink.id")


class BankAccountLink(db.Model):
    """An account of the bank inside a consent, and the account of the app its movements go to."""
    __tablename__ = "bank_account_links"

    id            = db.Column(db.Integer, primary_key=True)
    connection_id = db.Column(db.Integer, db.ForeignKey("bank_connections.id", ondelete="CASCADE"), nullable=False,
                              index=True)
    uid           = db.Column(db.String(120), nullable=False)    # the aggregator's id of the account
    iban          = db.Column(db.String(34))
    name          = db.Column(db.Text)                           # as the bank calls it
    currency      = db.Column(db.String(3), nullable=False, default="EUR")
    account_id    = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"), index=True)
    active        = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    last_sync_at  = db.Column(db.DateTime)                       # last download that worked (UTC)
    last_booked   = db.Column(db.Date)                           # newest booking date downloaded
    balance       = db.Column(db.Numeric(38, 2))                 # the bank's balance at the last download
    balance_date  = db.Column(db.Date)
    pending       = db.Column(db.JSON)                           # rows waiting for the preview (sync._stored)
    skipped       = db.Column(db.JSON)                           # import_refs left out in the preview: not brought back
    # the movements not booked yet at the bank, as the last download saw them: shown, never saved (they come back
    # booked, often with another id and sometimes another amount — a card hold, a hotel, a fuel station)
    at_bank       = db.Column(db.JSON)

    connection = db.relationship("BankConnection", back_populates="links")
    account    = db.relationship("Account")


class BankAccessLog(db.Model):
    """Every access to the bank through the aggregator (a consent given, a download by hand or by itself), in the
    archive it was made for: the page Gestione PSD2 shows them, and how many unattended reads a day were used."""
    __tablename__ = "bank_access_log"

    id            = db.Column(db.Integer, primary_key=True)
    connection_id = db.Column(db.Integer, db.ForeignKey("bank_connections.id", ondelete="SET NULL"), index=True)
    bank          = db.Column(db.String(120), nullable=False)   # kept: the log outlives an unlinked connection
    at            = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)  # UTC
    kind          = db.Column(db.String(10), nullable=False)    # consent | manual | auto
    ok            = db.Column(db.Boolean, nullable=False, default=True)
    saved         = db.Column(db.Integer, nullable=False, default=0)
    waiting       = db.Column(db.Integer, nullable=False, default=0)
    at_bank       = db.Column(db.Integer, nullable=False, default=0)  # not booked yet at the bank
    message       = db.Column(db.Text)
