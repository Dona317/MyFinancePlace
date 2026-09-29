from app.extensions import db


class ExchangeRate(db.Model):
    """Value of one unit of a foreign currency in euro on a date (entered by hand or downloaded from the ECB)."""
    __tablename__ = "exchange_rates"
    __table_args__ = (db.UniqueConstraint("currency", "on"),)

    id       = db.Column(db.Integer, primary_key=True)
    currency = db.Column(db.String(3), nullable=False, index=True)
    on       = db.Column(db.Date, nullable=False)
    rate     = db.Column(db.Numeric(20, 8), nullable=False)   # 1 unit of `currency` = `rate` EUR
    source   = db.Column(db.String(10), nullable=False, default="manual")  # "manual" | "ecb"
