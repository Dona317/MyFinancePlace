"""
Model portfolios (F19d): the target allocation the investments are kept close to. A template has slots (a share of
the portfolio each, adding up to 100 %); a holding counts in a slot when it is assigned to it, or has the slot's ISIN
or ticker, or is of the slot's asset class.
"""
from datetime import datetime

from app.extensions import db


class PortfolioTemplate(db.Model):
    __tablename__ = "portfolio_templates"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    band        = db.Column(db.Numeric(5, 2), nullable=False, default=5, server_default="5")  # tolerated drift, in points
    active      = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    created_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    slots = db.relationship("TemplateSlot", order_by="TemplateSlot.position", cascade="all, delete-orphan",
                            back_populates="template")


class TemplateSlot(db.Model):
    __tablename__ = "template_slots"

    id          = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("portfolio_templates.id", ondelete="CASCADE"), nullable=False,
                            index=True)
    position    = db.Column(db.Integer, nullable=False, default=0)
    label       = db.Column(db.Text, nullable=False)
    target      = db.Column(db.Numeric(6, 2), nullable=False)   # % of the portfolio
    asset_class = db.Column(db.Text)                             # every holding of this class not placed elsewhere
    isin        = db.Column(db.String(12))                       # the instrument suggested (or held) for the slot
    ticker      = db.Column(db.Text)

    template = db.relationship("PortfolioTemplate", back_populates="slots")
    links = db.relationship("SlotHolding", cascade="all, delete-orphan", back_populates="slot")

    @property
    def holding_ids(self) -> set[int]:
        return {link.holding_id for link in self.links}


class SlotHolding(db.Model):
    """A holding placed by hand in a slot."""
    __tablename__ = "slot_holdings"
    __table_args__ = (db.UniqueConstraint("slot_id", "holding_id"),)

    id         = db.Column(db.Integer, primary_key=True)
    slot_id    = db.Column(db.Integer, db.ForeignKey("template_slots.id", ondelete="CASCADE"), nullable=False, index=True)
    holding_id = db.Column(db.Integer, db.ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False, index=True)

    slot = db.relationship("TemplateSlot", back_populates="links")


class PortfolioRule(db.Model):
    """A watch on the investments (F19e); when it trips, a reminder appears (notifications, desktop alerts)."""
    __tablename__ = "portfolio_rules"

    id         = db.Column(db.Integer, primary_key=True)
    kind       = db.Column(db.String(20), nullable=False)   # drift | drawdown | price_above | price_below | concentration
    holding_id = db.Column(db.Integer, db.ForeignKey("holdings.id", ondelete="CASCADE"), index=True)  # empty = every one
    threshold  = db.Column(db.Numeric(18, 6))                # points, %, or a price in euro (empty drift = the band)
    active     = db.Column(db.Boolean, nullable=False, default=True, server_default="true")

    holding = db.relationship("Holding")


class InvestmentPlan(db.Model):
    """A PAC (F19e): an amount invested every month or quarter, split as the model portfolio says."""
    __tablename__ = "investment_plans"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.Text, nullable=False)
    amount      = db.Column(db.Numeric(14, 2), nullable=False)
    frequency   = db.Column(db.String(10), nullable=False, default="monthly")  # monthly | quarterly
    day         = db.Column(db.Integer, nullable=False, default=1)             # of the month
    account_id  = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"))
    template_id = db.Column(db.Integer, db.ForeignKey("portfolio_templates.id", ondelete="SET NULL"))  # empty = active
    fractional  = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    start       = db.Column(db.Date, nullable=False)
    end         = db.Column(db.Date)
    last_done   = db.Column(db.String(7))                    # "2026-10": the last period confirmed

    account = db.relationship("Account")
    template = db.relationship("PortfolioTemplate")
