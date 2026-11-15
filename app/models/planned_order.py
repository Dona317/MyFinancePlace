"""
Theoretical orders (planned_orders): what a rebalancing or a PAC instalment says to buy or sell, kept until the
user says they were executed. Until then they move nothing: positions, average prices and liquidity shown with them
are estimates, the liquidity gross of the commissions (services.planned_orders).
"""
from datetime import datetime

from app.extensions import db


class PlannedOrder(db.Model):
    __tablename__ = "planned_orders"

    id         = db.Column(db.Integer, primary_key=True)
    batch      = db.Column(db.String(32), nullable=False, index=True)   # the orders saved together
    source     = db.Column(db.String(20), nullable=False, default="rebalance")  # rebalance | pac
    label      = db.Column(db.Text)                                     # the model's part, the plan's name
    holding_id = db.Column(db.Integer, db.ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False, index=True)
    side       = db.Column(db.String(4), nullable=False)                # buy | sell
    units      = db.Column(db.Numeric(38, 8), nullable=False)
    price      = db.Column(db.Numeric(38, 6), nullable=False)           # the price expected, in euro
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"))  # where the money moves
    securities_account_id = db.Column(db.Integer, db.ForeignKey("securities_accounts.id", ondelete="SET NULL"))
    portfolio_id = db.Column(db.Integer, db.ForeignKey("portfolios.id", ondelete="SET NULL"))
    plan_id    = db.Column(db.Integer, db.ForeignKey("investment_plans.id", ondelete="SET NULL"))  # a PAC instalment
    notes      = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    holding = db.relationship("Holding")
    account = db.relationship("Account")
    securities_account = db.relationship("SecuritiesAccount")
    portfolio = db.relationship("Portfolio")
    plan = db.relationship("InvestmentPlan")
