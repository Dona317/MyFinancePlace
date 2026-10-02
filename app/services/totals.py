"""The sum every report starts from: the value in the base currency of the transactions matching some filters."""
from sqlalchemy import func

from app.extensions import db
from app.models.transaction import Transaction

VALUE = func.abs(Transaction.amount_base)  # stored in base currency; the sign comes from `type`


def value_total(*criteria) -> float:
    return float(db.session.query(func.coalesce(func.sum(VALUE), 0)).filter(*criteria).scalar())
