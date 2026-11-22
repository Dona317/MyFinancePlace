"""Where the money goes: a Sankey diagram (income categories → total → expenses and savings).

22 Nov 2026: the server gives the figures only; the page draws them on the block's real size (static/js/sankey.js),
again whenever the block changes size, with as many categories as the width allows (the rest in «Altre»)."""
from datetime import date

from app.services.analytics import OTHER, category_breakdown
from app.services.i18n import N_, tr

SIDE = 30  # categories sent for each side, biggest first; the rest add up in «Altre» (the page groups further)
SAVINGS = N_("Risparmio")
FROM_SAVINGS = N_("Dai risparmi")  # spent more than earned: the gap is taken from savings


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
    if not total_in and not total_out:
        return None
    left = [_node(name, amount) for name, amount in incomes]
    right = [_node(name, amount) for name, amount in expenses]
    if total_in > total_out:
        right.append(_node(SAVINGS, total_in - total_out, special=True))
    elif total_out > total_in:
        left.append(_node(FROM_SAVINGS, total_out - total_in, special=True))
    # the middle is what passes through: the income, or the expenses when part of them came from the savings
    middle = {"label": str(tr(N_("Entrate") if total_in >= total_out else N_("Uscite"))),
              "amount": round(max(total_in, total_out), 2)}
    return {"incomes": left, "expenses": right, "middle": middle, "other": str(tr(OTHER)),
            "total_in": round(total_in, 2), "total_out": round(total_out, 2)}
