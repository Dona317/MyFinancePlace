"""
What the user owns and owes beyond the transactions: investments and other assets, debts,
insurance policies, savings goals, archived documents and snapshots of the net worth over time.
"""
from datetime import date, datetime

from app.extensions import db


def _number(value) -> float:
    return float(value or 0)


class Holding(db.Model):
    """An investment or other asset: shares, ETFs, crypto, bonds, savings accounts, pension funds, property."""
    __tablename__ = "holdings"

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.Text, nullable=False)
    ticker        = db.Column(db.Text)
    asset_class   = db.Column(db.Text, nullable=False)
    quantity      = db.Column(db.Numeric(38, 8), nullable=False)
    avg_price     = db.Column(db.Numeric(38, 6), nullable=False)   # average purchase price per unit
    current_price = db.Column(db.Numeric(38, 6))                  # empty = still worth the purchase price
    price_date    = db.Column(db.Date)                            # when the current price was last updated
    purchase_date = db.Column(db.Date)
    notes         = db.Column(db.Text)
    # Taxes (F15): the rate on its capital gains when not the usual one for its class (12.5 for government bonds),
    # and whether it is held abroad (IVAFE instead of the stamp duty)
    tax_rate      = db.Column(db.Numeric(5, 2))
    abroad        = db.Column(db.Boolean, nullable=False, default=False, server_default="false")

    @property
    def price(self) -> float:
        return _number(self.current_price if self.current_price is not None else self.avg_price)

    @property
    def cost(self) -> float:
        return _number(self.quantity) * _number(self.avg_price)

    @property
    def value(self) -> float:
        return _number(self.quantity) * self.price

    @property
    def gain(self) -> float:
        return self.value - self.cost

    @property
    def gain_pct(self) -> float:
        return self.gain / self.cost * 100 if self.cost else 0.0


class HoldingPrice(db.Model):
    """The price of a holding on a date (F5): past balance sheets value the holding at the latest one known by then."""
    __tablename__ = "holding_prices"
    __table_args__ = (db.UniqueConstraint("holding_id", "on"),)

    id         = db.Column(db.Integer, primary_key=True)
    holding_id = db.Column(db.Integer, db.ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False, index=True)
    on         = db.Column(db.Date, nullable=False)
    price      = db.Column(db.Numeric(38, 6), nullable=False)


class Debt(db.Model):
    """A mortgage, loan or credit card, repaid with constant monthly installments (French amortization)."""
    __tablename__ = "debts"

    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.Text, nullable=False)        # lender or a short label
    type            = db.Column(db.Text, nullable=False)
    principal       = db.Column(db.Numeric(38, 2), nullable=False)
    annual_rate     = db.Column(db.Numeric(9, 4), nullable=False, default=0)   # percent, e.g. 3.25
    term_months     = db.Column(db.Integer)
    start_date      = db.Column(db.Date)
    monthly_payment = db.Column(db.Numeric(38, 2))              # empty = computed from rate and term
    balance         = db.Column(db.Numeric(38, 2))              # known outstanding balance; empty = from the plan
    notes           = db.Column(db.Text)


class InsurancePolicy(db.Model):
    __tablename__ = "insurance_policies"

    id             = db.Column(db.Integer, primary_key=True)
    type           = db.Column(db.Text, nullable=False)
    company        = db.Column(db.Text, nullable=False)
    policy_number  = db.Column(db.Text)
    premium        = db.Column(db.Numeric(38, 2), nullable=False)   # amount of each payment
    frequency      = db.Column(db.String(20), nullable=False, default="annual")
    coverage_limit = db.Column(db.Numeric(38, 2))
    start_date     = db.Column(db.Date)
    expiry_date    = db.Column(db.Date)
    notes          = db.Column(db.Text)

    PAYMENTS_PER_YEAR = {"monthly": 12, "quarterly": 4, "biannual": 2, "annual": 1}

    @property
    def annual_premium(self) -> float:
        return _number(self.premium) * self.PAYMENTS_PER_YEAR.get(self.frequency, 1)

    def is_active(self, today: date | None = None) -> bool:
        return self.expiry_date is None or self.expiry_date >= (today or date.today())


class Goal(db.Model):
    """A savings goal: emergency fund, holiday, house deposit..."""
    __tablename__ = "goals"

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.Text, nullable=False)
    target_amount = db.Column(db.Numeric(38, 2), nullable=False)
    saved_amount  = db.Column(db.Numeric(38, 2), nullable=False, default=0)
    target_date   = db.Column(db.Date)
    notes         = db.Column(db.Text)
    created_at    = db.Column(db.Date, nullable=False, default=date.today)

    @property
    def progress(self) -> float:
        target = _number(self.target_amount)
        return round(min(_number(self.saved_amount) / target * 100, 100), 1) if target else 0.0

    @property
    def remaining(self) -> float:
        return max(_number(self.target_amount) - _number(self.saved_amount), 0.0)

    @property
    def completed(self) -> bool:
        return self.remaining == 0

    def monthly_needed(self, today: date | None = None) -> float | None:
        """How much to put aside each month to reach the target on time (None without a date)."""
        if self.target_date is None or self.completed:
            return None
        today = today or date.today()
        months = (self.target_date.year - today.year) * 12 + self.target_date.month - today.month
        return self.remaining / max(months, 1)


class Document(db.Model):
    """A file in the archive (invoice, receipt, contract...), stored under <instance>/documents."""
    __tablename__ = "documents"

    id             = db.Column(db.Integer, primary_key=True)
    filename       = db.Column(db.Text, nullable=False)                 # original name, shown to the user
    stored_name    = db.Column(db.String(80), nullable=False, unique=True)
    mimetype       = db.Column(db.Text)
    size           = db.Column(db.BigInteger, nullable=False, default=0)
    doc_type       = db.Column(db.Text)
    fiscal_year    = db.Column(db.Integer)
    category       = db.Column(db.Text)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id", ondelete="SET NULL"), index=True)
    notes          = db.Column(db.Text)
    uploaded_at    = db.Column(db.DateTime, nullable=False, default=datetime.now)

    transaction = db.relationship("Transaction", lazy="joined")

    @property
    def is_pdf(self) -> bool:
        return (self.mimetype or "").endswith("pdf") or self.filename.lower().endswith(".pdf")

    @property
    def is_image(self) -> bool:
        return (self.mimetype or "").startswith("image/")


class Snapshot(db.Model):
    """The net worth at a point in time, with the detail it was computed from."""
    __tablename__ = "snapshots"

    id          = db.Column(db.Integer, primary_key=True)
    taken_on    = db.Column(db.Date, nullable=False, default=date.today)
    label       = db.Column(db.Text)
    cash        = db.Column(db.Numeric(38, 2), nullable=False, default=0)
    investments = db.Column(db.Numeric(38, 2), nullable=False, default=0)
    other_assets = db.Column(db.Numeric(38, 2), nullable=False, default=0)
    liabilities = db.Column(db.Numeric(38, 2), nullable=False, default=0)
    net_worth   = db.Column(db.Numeric(38, 2), nullable=False, default=0)
    detail      = db.Column(db.JSON)          # the balance sheet lines at that moment

    @property
    def total_assets(self) -> float:
        return _number(self.cash) + _number(self.investments) + _number(self.other_assets)
