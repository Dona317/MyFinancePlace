"""
Whose things are (F20): accounts, holdings and debts can belong to one of the holders (Impostazioni → Titolari e
IBAN), be joint, or stay with the family (no owner). The net worth is split by person: a joint item is shared in equal
parts among the holders; the family's items are shown apart.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from flask import request
from flask_babel import gettext as _

from app.models.account import Account
from app.models.wealth import Debt, Holding
from app.services import accounts, currency, owners, wealth

JOINT = "joint"
FAMILY = ""  # no owner


def choices() -> list[tuple[str, str]]:
    """The owners a form offers: each holder, and «joint» when there are two or more."""
    names = owners.holders()
    return [(name, name) for name in names] + ([(JOINT, _("Cointestato"))] if len(names) > 1 else [])


def label(owner: str | None) -> str:
    if owner == JOINT:
        return _("Cointestato")
    return owner or _("Famiglia")


def from_form(field: str = "owner") -> str | None:
    """The owner chosen in a form, if it is one of the choices."""
    value = (request.form.get(field) or "").strip()
    return value if value in {key for key, _label in choices()} else None


def shares(owner: str | None) -> dict[str, float]:
    """How an item is split: all to its holder, in equal parts when joint, to the family when nobody's."""
    names = owners.holders()
    if owner == JOINT and names:
        return {name: 1 / len(names) for name in names}
    if owner and owner in names:
        return {owner: 1.0}
    return {FAMILY: 1.0}


def by_person(on: date | None = None) -> list[dict]:
    """Cash, investments, other assets, debts and net worth of each holder, then the family's unassigned part."""
    on = on or date.today()
    rows = defaultdict(lambda: defaultdict(float))
    target = currency.base()
    for account in Account.query.all():
        value = float(currency.to_base(accounts.balance(account, on), account.currency, on, target=target))
        for person, share in shares(account.owner).items():
            rows[person]["cash"] += value * share
    for holding in wealth.holdings_on(on):
        line = "investments" if wealth.ASSET_CLASSES.get(holding.asset_class, ("", False))[1] else "other"
        for person, share in shares(holding.owner).items():
            rows[person][line] += holding.value * share
    for debt in Debt.query.all():
        owed = wealth.debt_summary(debt, on)["balance"]
        for person, share in shares(debt.owner).items():
            rows[person]["debts"] += owed * share
    order = owners.holders() + [FAMILY]
    result = []
    for person in order:
        if person not in rows:
            continue
        r = rows[person]
        result.append({"person": person, "label": label(person), "cash": round(r["cash"], 2),
                       "investments": round(r["investments"], 2), "other": round(r["other"], 2),
                       "debts": round(r["debts"], 2),
                       "net": round(r["cash"] + r["investments"] + r["other"] - r["debts"], 2)})
    return result


def holdings_of(person: str | None, holdings: list[Holding]) -> list[Holding]:
    """The holdings a person has a share of (theirs and the joint ones); all when no person is chosen."""
    if not person:
        return holdings
    return [h for h in holdings if person in shares(h.owner)]


def account_ids_of(person: str) -> list[int]:
    return [a.id for a in Account.query.all() if person in shares(a.owner)]
