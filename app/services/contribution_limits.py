"""
Contribution limits (F22): the money that can go into something each year, and how much already has.

A limit follows the accounts the money arrives on (giroconti to them), the holdings it buys or pays into (operations
and contributions linked to the holding; sales do not free any room) and, if chosen, a category of expenses. Each
movement counts once. Ready-made limits for the Italian rules can be added and changed:
- a pension fund: 5.164,57 € a year deductible (the same ceiling as the 730's line E27, services.tax_rules);
- a PIR: 40.000 € a year and 200.000 € in all; an alternative PIR: 300.000 € a year and 1.500.000 € in all.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from flask_babel import gettext as _
from sqlalchemy import or_

from app.extensions import db
from app.models.account import Account
from app.models.limit import ContributionLimit
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import categories
from app.services.i18n import N_

D = Decimal


@dataclass(frozen=True)
class Preset:
    kind: str
    name: str
    yearly: Decimal
    total: Decimal | None
    deductible: bool  # the room left at the end of the year is lost for the tax return


PRESETS = (
    Preset("pension", N_("Fondo pensione (deducibile)"), D("5164.57"), None, True),
    Preset("pir", N_("PIR ordinario"), D(40000), D(200000), False),
    Preset("pir_alt", N_("PIR alternativo"), D(300000), D(1500000), False),
)
BY_KIND = {preset.kind: preset for preset in PRESETS}
REMIND_FROM_MONTH = 10  # from October: still time to pay into the pension fund before 31 December


@dataclass
class Standing:
    limit: ContributionLimit
    year: int
    paid: Decimal          # in the year
    paid_total: Decimal    # since `since_year` (only for a lifetime limit)
    movements: list[Transaction]

    @property
    def left(self) -> Decimal:
        room = Decimal(self.limit.yearly) - self.paid
        if self.limit.total is not None:
            room = min(room, Decimal(self.limit.total) - self.paid_total)
        return max(room, Decimal(0))

    @property
    def over(self) -> Decimal:
        """How much went in beyond the yearly limit (not deductible, or out of the PIR's benefit)."""
        return max(self.paid - Decimal(self.limit.yearly), Decimal(0))

    @property
    def pct(self) -> float:
        return min(float(self.paid / Decimal(self.limit.yearly) * 100), 100.0) if self.limit.yearly else 0.0

    @property
    def total_pct(self) -> float | None:
        if self.limit.total is None or not self.limit.total:
            return None
        return min(float(self.paid_total / Decimal(self.limit.total) * 100), 100.0)

    @property
    def deductible(self) -> bool:
        preset = BY_KIND.get(self.limit.kind)
        return bool(preset and preset.deductible)


def _matches(limit: ContributionLimit):
    """The movements that put money into what the limit follows."""
    conditions = []
    if limit.account_ids:
        conditions.append((Transaction.type == "transfer") & Transaction.counter_account_id.in_(limit.account_ids))
    if limit.holding_ids:
        conditions.append(Transaction.type.in_(["transfer", "expense"]) & Transaction.holding_id.in_(limit.holding_ids)
                          & (Transaction.units.is_(None) | (Transaction.units > 0)))
    if limit.category:
        names = [limit.category, *categories.children(limit.category)]
        conditions.append((Transaction.type == "expense") & Transaction.category.in_(names))
    return or_(*conditions) if conditions else None


def _movements(limit: ContributionLimit, start: date, end: date) -> list[Transaction]:
    condition = _matches(limit)
    if condition is None:
        return []
    return (Transaction.query.filter(condition, Transaction.date >= start, Transaction.date <= end)
            .order_by(Transaction.date).all())


def _value(tx: Transaction) -> Decimal:
    return abs(Decimal(tx.amount_base if tx.amount_base is not None else tx.amount))


def standing(limit: ContributionLimit, year: int) -> Standing:
    moves = _movements(limit, date(year, 1, 1), date(year, 12, 31))
    paid = sum((_value(tx) for tx in moves), Decimal(0))
    paid_total = paid
    if limit.total is not None:
        first = date(limit.since_year or 1900, 1, 1)
        paid_total = sum((_value(tx) for tx in _movements(limit, first, date(year, 12, 31))), Decimal(0))
    return Standing(limit, year, paid, paid_total, moves)


def all_standings(year: int) -> list[Standing]:
    return [standing(limit, year) for limit in ContributionLimit.query.order_by(ContributionLimit.name)]


def _ids(values, model) -> list[int]:
    wanted = {int(v) for v in values if str(v).isdigit()}
    return sorted(i for (i,) in db.session.query(model.id).filter(model.id.in_(wanted))) if wanted else []


def save(limit: ContributionLimit | None, *, name: str, kind: str, yearly: Decimal | None, total: Decimal | None,
         since_year: int | None, account_ids, holding_ids, category: str | None, notes: str | None) -> ContributionLimit:
    name = " ".join((name or "").split())[:120]
    if not name:
        raise ValueError(_("Scrivi il nome del tetto."))
    if yearly is None or yearly <= 0:
        raise ValueError(_("Il tetto annuo deve essere un importo positivo."))
    if total is not None and total < yearly:
        raise ValueError(_("Il tetto totale non può essere più basso di quello annuo."))
    accounts, holdings = _ids(account_ids, Account), _ids(holding_ids, Holding)
    category = (category or "").strip() or None
    if not (accounts or holdings or category):
        raise ValueError(_("Scegli almeno un conto, un titolo o una categoria in cui finiscono i versamenti."))
    limit = limit or ContributionLimit()
    limit.name, limit.kind = name, kind if kind in BY_KIND else "custom"
    limit.yearly, limit.total, limit.since_year = yearly, total, since_year
    limit.account_ids, limit.holding_ids, limit.category = accounts, holdings, category
    limit.notes = (notes or "").strip() or None
    db.session.add(limit)
    return limit


def reminders(today: date) -> list[Standing]:
    """Deductible limits with room left late in the year: the room is lost on 31 December."""
    if today.month < REMIND_FROM_MONTH:
        return []
    return [s for s in all_standings(today.year) if s.deductible and s.left > 0]
