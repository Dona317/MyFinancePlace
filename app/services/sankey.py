"""Where the money goes: a Sankey diagram (income categories → total → expenses and savings).

22 Nov 2026: the server gives the figures only; the page draws them on the block's real size (static/js/sankey.js),
again whenever the block changes size, with as many categories as the width allows (the rest in «Altre»)."""
from datetime import date

from sqlalchemy import and_, func

from app.extensions import db
from app.models.transaction import Transaction
from app.services.analytics import OTHER, category_breakdown
from app.services.i18n import N_, tr

SIDE = 30  # categories sent for each side, biggest first; the rest add up in «Altre» (the page groups further)
SAVINGS = N_("Risparmio")
FROM_SAVINGS = N_("Dai risparmi")  # spent more than earned: the gap is taken from savings
INVESTED = N_("Investimenti")  # 23 Nov 2026: securities bought (less those sold), with their commissions
SOLD = N_("Vendite di titoli")  # more sold than bought: money that came back from the securities


def invested(start: date, end: date) -> float:
    """The money put into securities in [start, end): purchases less sales, plus the trades' commissions."""
    size = func.abs(func.coalesce(Transaction.amount_base, Transaction.amount))
    when = and_(Transaction.date >= start, Transaction.date < end)
    trades = db.session.query(Transaction.units > 0, func.sum(size)).filter(
        when, Transaction.holding_id.isnot(None), Transaction.units.isnot(None)).group_by(Transaction.units > 0).all()
    fees = db.session.query(func.sum(size)).filter(when, Transaction.fee_for_id.isnot(None)).scalar() or 0
    bought = sum(float(total or 0) for buying, total in trades if buying)
    sold = sum(float(total or 0) for buying, total in trades if not buying)
    return round(bought - sold + float(fees), 2)


def _side(items: list[dict]) -> list[tuple[str, float]]:
    shown = [(i["category"], i["amount"]) for i in items[:SIDE] if i["amount"] > 0]
    rest = sum(i["amount"] for i in items[SIDE:])
    return shown + ([(OTHER, rest)] if rest > 0 else [])


def _node(name: str, amount: float, special: bool = False) -> dict:
    """A category of one side: its label (translated), amount, and the category it opens (None: not a real one)."""
    return {"label": str(tr(name)), "amount": round(amount, 2), "special": special,
            "category": None if special or name == OTHER else name}


def flow(start: date, end: date) -> dict | None:
    """
    The money of [start, end): income categories (left) → the middle → expense categories (right), biggest first;
    the savings close the right side (or, when more was spent than earned, «Dai risparmi» the left one). None when
    nothing moved.
    """
    incomes = _side(category_breakdown(start, end, "income"))
    expenses = _side(category_breakdown(start, end, "expense"))
    total_in, total_out = sum(a for _, a in incomes), sum(a for _, a in expenses)
    put_in = invested(start, end)
    if not total_in and not total_out and not put_in:
        return None
    left = [_node(name, amount) for name, amount in incomes]
    right = [_node(name, amount) for name, amount in expenses]
    # the money into securities goes out on the right, next to the expenses (not a spending: an investment); more
    # sold than bought comes in on the left
    if put_in > 0:
        right.append(dict(_node(INVESTED, put_in, special=True), kind="invest"))
        total_out += put_in
    elif put_in < 0:
        left.append(dict(_node(SOLD, -put_in, special=True), kind="invest"))
        total_in += -put_in
    if total_in > total_out:
        right.append(_node(SAVINGS, total_in - total_out, special=True))
    elif total_out > total_in:
        left.append(_node(FROM_SAVINGS, total_out - total_in, special=True))
    # the middle is what passes through: the income, or the expenses when part of them came from the savings
    middle = {"label": str(tr(N_("Entrate") if total_in >= total_out else N_("Uscite"))),
              "amount": round(max(total_in, total_out), 2)}
    return {"incomes": left, "expenses": right, "middle": middle, "other": str(tr(OTHER)),
            "total_in": round(total_in, 2), "total_out": round(total_out, 2)}
