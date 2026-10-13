"""
The sum every report starts from: the value in the base currency of the transactions matching some filters.

The analyses (reports, budgets, rhythm, savings rate…) leave out the categories excluded from them (F22: refunds
of work expenses, money spent for others); balances, the balance sheet and the tax pages count everything.
"""
from sqlalchemy import case, func, or_, true

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


def analysed(column=Transaction.category):
    """The condition that keeps the categories excluded from the analyses out (an uncategorized movement stays)."""
    from app.services import categories  # here: categories imports this module

    names = categories.excluded_names()
    return or_(column.is_(None), column.notin_(names)) if names else true()


def with_lines(query, analysis: bool = True):
    """One row per part: a split transaction counts once per split, the others once (`query` on Transaction);
    the parts in an excluded category are left out unless `analysis` is False."""
    query = query.outerjoin(TransactionSplit, TransactionSplit.transaction_id == Transaction.id)
    return query.filter(analysed(LINE_CATEGORY)) if analysis else query


def lines_query(*entities, analysis: bool = True):
    """A query of `entities` over the parts of the transactions (see with_lines)."""
    return with_lines(db.session.query(*entities).select_from(Transaction), analysis)


def value_total(*criteria) -> float:
    return float(db.session.query(func.coalesce(func.sum(VALUE), 0)).filter(analysed(), *criteria).scalar())


def excluded_total(*criteria) -> float:
    """What the excluded categories add up to (shown apart: «left out of the analyses: X €»)."""
    from app.services import categories

    names = categories.excluded_names()
    if not names:
        return 0.0
    query = lines_query(func.coalesce(func.sum(LINE_VALUE), 0), analysis=False).filter(LINE_CATEGORY.in_(names), *criteria)
    return float(query.scalar())
