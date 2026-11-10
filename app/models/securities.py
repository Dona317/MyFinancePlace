"""
Securities accounts and portfolios (F42, decision D8).

A securities account (conto titoli, dossier) is where a broker keeps the securities; its money moves on a settlement
account (a normal Account: Directa, Fineco…). A portfolio is a goal the user invests for («Pensione», «Casa»). The two
are independent: each trade says both where it sits and what it is for, so one portfolio can spread over several
securities accounts and one securities account can hold several portfolios. Positions are always derived from the
trades (services.securities), never stored by hand.
"""
from datetime import datetime

from app.extensions import db


class SecuritiesAccount(db.Model):
    """A broker's dossier: its settlement account, how its gains are taxed and what its commissions are."""
    __tablename__ = "securities_accounts"

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.Text, nullable=False, unique=True)
    broker        = db.Column(db.String(80))   # the intermediary's name: Fineco, Directa, Trade Republic…
    # where the money of its trades, dividends and commissions moves (deleted with it: the dossier stays)
    settlement_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"), index=True)
    owner         = db.Column(db.String(80))   # whose it is (F20): a holder's name, «joint», empty = family
    # Taxes (F15): regime of the capital gains and whether it is held abroad (IVAFE instead of the stamp duty)
    tax_regime    = db.Column(db.String(20), nullable=False, default="amministrato", server_default="amministrato")
    abroad        = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    # Cost of what is sold (D9): the weighted average of this dossier, as the bank computes it
    cost_method   = db.Column(db.String(20), nullable=False, default="average", server_default="average")
    # Commission rules (F17), as on the settlement account: fixed + percent, within a minimum and a maximum
    fee_fixed     = db.Column(db.Numeric(38, 2))
    fee_percent   = db.Column(db.Numeric(9, 4))
    fee_min       = db.Column(db.Numeric(38, 2))
    fee_max       = db.Column(db.Numeric(38, 2))
    notes         = db.Column(db.Text)
    active        = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    settlement_account = db.relationship("Account", foreign_keys=[settlement_account_id])

    @property
    def has_fee_rule(self) -> bool:
        return any(v is not None for v in (self.fee_fixed, self.fee_percent, self.fee_min, self.fee_max))


class Portfolio(db.Model):
    """A goal the user invests for; exactly one is the default, where trades go when none is chosen."""
    __tablename__ = "portfolios"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.Text, nullable=False, unique=True)
    description = db.Column(db.Text)
    is_default  = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    position    = db.Column(db.Integer, nullable=False, default=0, server_default="0")  # order in lists
    active      = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
