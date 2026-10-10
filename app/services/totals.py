"""The sum every report starts from: the value in the base currency of the transactions matching some filters."""
from sqlalchemy import case, func

from app.extensions import db
from app.models.transaction import Transaction, TransactionSplit

VALUE = func.abs(Transaction.amount_base)  # stored in base currency; the sign comes from `type`

# Totals by category look at the parts of a split transaction (70 Spesa + 30 Casa), each worth its share of the
# transaction's value in euro: use these on a query passed through with_lines()
LINE_CATEGORY = func.coalesce(TransactionSplit.category, Transaction.category)
LINE_VALUE = case(
    (TransactionSplit.id.is_(None), VALUE),
    else_=VALUE * func.abs(TransactionSplit.amount) / func.nullif(func.abs(Transaction.amount), 0),
)


def with_lines(query):
    """One row per part: a split transaction counts once per split, the others once (`query` on Transaction)."""
    return query.outerjoin(TransactionSplit, TransactionSplit.transaction_id == Transaction.id)


def lines_query(*entities):
    """A query of `entities` over the parts of the transactions (see with_lines)."""
    return with_lines(db.session.query(*entities).select_from(Transaction))


def value_total(*criteria) -> float:
    return float(db.session.query(func.coalesce(func.sum(VALUE), 0)).filter(*criteria).scalar())
