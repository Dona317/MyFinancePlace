"""Where the money goes: a Sankey diagram (income categories → total → expenses and savings)."""
from datetime import date

from app.services.analytics import OTHER, category_breakdown
from app.services.i18n import N_

SIDE = 7  # categories shown on each side; the rest add up in "Altre"
SAVINGS = N_("Risparmio")
FROM_SAVINGS = N_("Dai risparmi")  # spent more than earned: the gap is taken from savings
# 22 Nov 2026: drawn for a block two columns wide and two rows tall — narrower and taller than before, the amount
# under each label; a small category still gets the room of its two lines (SLOT), so the labels do not overlap
WIDTH, HEIGHT, NODE, GAP, SLOT = 560, 500, 14, 12, 34


def _side(items: list[dict]) -> list[tuple[str, float]]:
    shown = [(i["category"], i["amount"]) for i in items[:SIDE] if i["amount"] > 0]
    rest = sum(i["amount"] for i in items[SIDE:])
    return shown + ([(OTHER, rest)] if rest > 0 else [])


def _category(name: str, special: bool) -> str | None:
    """The category a node or a band opens in the transactions; None when it is not a real category."""
    return None if special or name == OTHER else name


def _band(x0: float, y0: float, x1: float, y1: float, thickness: float) -> str:
    """An SVG path: a band of `thickness` from (x0, y0) to (x1, y1) (top edges), curved in the middle."""
    middle = (x0 + x1) / 2
    return (f"M{x0:.1f},{y0:.1f} C{middle:.1f},{y0:.1f} {middle:.1f},{y1:.1f} {x1:.1f},{y1:.1f} "
            f"L{x1:.1f},{y1 + thickness:.1f} C{middle:.1f},{y1 + thickness:.1f} {middle:.1f},{y0 + thickness:.1f} "
            f"{x0:.1f},{y0 + thickness:.1f} Z")


def flow(start: date, end: date) -> dict | None:
    """
    Nodes and bands of the money flow in [start, end): income categories (left) → the total (middle) →
    expense categories and savings (right). Sizes are proportional to amounts; None when nothing moved.
    """
    incomes = _side(category_breakdown(start, end, "income"))
    expenses = _side(category_breakdown(start, end, "expense"))
    total_in, total_out = sum(a for _, a in incomes), sum(a for _, a in expenses)
    if not total_in and not total_out:
        return None
    if total_in > total_out:
        expenses.append((SAVINGS, total_in - total_out))
    elif total_out > total_in:
        incomes.append((FROM_SAVINGS, total_out - total_in))
    total = max(total_in, total_out)
    rows = max(len(incomes), len(expenses))
    scale = (HEIGHT - GAP * (rows - 1)) / total

    def column(items, x, kind):
        height = sum(max(a * scale, SLOT) for _, a in items) + GAP * (len(items) - 1)
        y, nodes = max((HEIGHT - height) / 2, 0), []
        for index, (name, amount) in enumerate(items):
            special = name in (SAVINGS, FROM_SAVINGS)
            nodes.append({"label": name, "amount": round(amount, 2), "x": x, "y": round(y, 1),
                          "h": round(max(amount * scale, 1), 1), "kind": kind, "special": special,
                          "category": _category(name, special),
                          "color": "positive" if special else f"chart-{index % 8 + 1}"})
            y += max(amount * scale, SLOT) + GAP
        return nodes

    left = column(incomes, 0, "income")
    right = column(expenses, WIDTH - NODE, "expense")
    centre_x = (WIDTH - NODE) / 2
    # the middle is what passes through: the income, or the expenses when part of them came from the savings
    centre = {"label": N_("Entrate") if total_in >= total_out else N_("Uscite"), "amount": round(total, 2), "x": centre_x,
              "y": round((HEIGHT - total * scale) / 2, 1), "h": round(total * scale, 1), "kind": "total",
              "special": False, "category": None, "color": "primary"}
    bands, y_in, y_out = [], centre["y"], centre["y"]
    for node in left:   # each income flows into the middle, stacked; its band opens the income category
        bands.append({"d": _band(NODE, node["y"], centre_x, y_in, node["h"]), "color": node["color"],
                      "label": node["label"], "amount": node["amount"], "to": centre["label"],
                      "kind": "income", "category": node["category"]})
        y_in += node["h"]
    for node in right:  # the middle flows out to each expense, stacked; its band opens the expense category
        bands.append({"d": _band(centre_x + NODE, y_out, node["x"], node["y"], node["h"]), "color": node["color"],
                      "label": centre["label"], "amount": node["amount"], "to": node["label"],
                      "kind": "expense", "category": node["category"]})
        y_out += node["h"]
    bottom = max(n["y"] + max(n["h"], SLOT) for n in [*left, *right])
    return {"nodes": [*left, centre, *right], "bands": bands, "width": WIDTH, "height": round(max(HEIGHT, bottom), 1),
            "node_width": NODE, "total_in": round(total_in, 2), "total_out": round(total_out, 2)}
