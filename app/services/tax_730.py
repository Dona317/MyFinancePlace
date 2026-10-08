"""
The 730 from the year's transactions (F15): the expenses that lower the tax, gathered by quadro E line.

Each line takes the expenses of the categories the user assigned to it (Fisco → 730 → Categorie; Salute and
Istruzione to start with); an expense of a subcategory counts for its main category too. Expenses tagged
«detraibile» or «deducibile» that no line takes are listed apart, to be assigned. Per line: total paid, minus the
franchigia, up to the ceiling, and the deduction it is worth.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.models.transaction import Transaction
from app.services import categories, settings_store, tax_rules
from app.services.tax_rules import DETRAZIONE

MAP_SETTING = "tax.730_categories"
DEFAULT_MAP = {"sanitarie": ["Salute"], "istruzione": ["Istruzione"]}
TAX_TAGS = {"detraibile", "deducibile"}
CENT = Decimal("0.01")


@dataclass
class Line:
    item: tax_rules.Item
    paid: Decimal = Decimal(0)
    entries: list[tuple[Transaction, Decimal]] = field(default_factory=list)
    in_cash: int = 0  # paid in cash: for most lines the deduction needs a traceable payment
    people: int = 1

    @property
    def counted(self) -> Decimal:
        """What counts: above the franchigia, within the ceiling (per student or child when it is per person)."""
        base = max(self.paid - self.item.threshold, Decimal(0))
        if self.item.ceiling is not None:
            base = min(base, self.item.ceiling * (self.people if self.item.per_person else 1))
        return base

    @property
    def benefit(self) -> Decimal:
        """A detrazione: the tax it takes off. A deduction: the income it takes off (worth it × the marginal rate)."""
        if self.item.kind == DETRAZIONE:
            return (self.counted * self.item.rate / 100).quantize(CENT, rounding=ROUND_HALF_UP)
        return self.counted.quantize(CENT)


def mapping() -> dict[str, list[str]]:
    """{line code: [categories]} as saved, the defaults before the first save."""
    raw = settings_store.get(MAP_SETTING)
    try:
        saved = json.loads(raw) if raw else None
    except ValueError:
        saved = None
    return {k: [c for c in v if isinstance(c, str)] for k, v in saved.items() if isinstance(v, list)} \
        if isinstance(saved, dict) else {k: list(v) for k, v in DEFAULT_MAP.items()}


def save_mapping(chosen: dict[str, list[str]], people: dict[str, int]) -> None:
    settings_store.set(MAP_SETTING, json.dumps({k: sorted(set(v)) for k, v in chosen.items() if v}))
    settings_store.set(MAP_SETTING + ".people", json.dumps({k: n for k, n in people.items() if n > 1}))


def people() -> dict[str, int]:
    """How many students or children a per-person ceiling applies to (Fisco → 730 → Categorie)."""
    try:
        saved = json.loads(settings_store.get(MAP_SETTING + ".people") or "{}")
    except ValueError:
        return {}
    return {k: int(v) for k, v in saved.items() if isinstance(v, int) and 1 <= v <= 20} if isinstance(saved, dict) else {}


def summary(year: int) -> dict:
    """The year's 730 lines with their expenses, the unassigned tagged ones and the totals."""
    lines = {item.code: Line(item, people=people().get(item.code, 1)) for item in tax_rules.items(year)}
    owner = {}
    for code, names in mapping().items():
        for name in names:
            owner.setdefault(name, code)
    unassigned = []
    expenses = (Transaction.query.filter(Transaction.type == "expense", Transaction.date >= date(year, 1, 1),
                                         Transaction.date < date(year + 1, 1, 1))
                .order_by(Transaction.date, Transaction.id))
    for tx in expenses:
        taken = False
        for category, value in tx.parts():
            code = owner.get(category) or owner.get(categories.top(category))
            if code in lines:
                amount = Decimal(str(round(value, 2)))
                line = lines[code]
                line.paid += amount
                line.entries.append((tx, amount))
                line.in_cash += 1 if tx.account and tx.account.kind == "cash" else 0
                taken = True
        if not taken and {t.lower() for t in tx.tags or []} & TAX_TAGS:
            unassigned.append(tx)
    used = [line for line in lines.values() if line.paid]
    return {
        "year": year, "lines": used, "all_lines": list(lines.values()), "unassigned": unassigned,
        "detrazioni": sum((line.benefit for line in used if line.item.kind == DETRAZIONE), Decimal(0)),
        "deduzioni": sum((line.benefit for line in used if line.item.kind != DETRAZIONE), Decimal(0)),
        "rates": tax_rules.irpef_rates(year),
    }
