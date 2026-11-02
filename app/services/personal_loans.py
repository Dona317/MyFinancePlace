"""
Money between people (F22): who owes what to whom — lent, advanced for someone, borrowed, given back — with each
person's balance, the reminders at the due date, and the two everyday cases tied to the movements:

- an expense shared with others («dividi con…»): the others' shares become what they owe me, and the expense is
  split so that only my part stays in its category; their part goes to «Anticipi per altri», a category left out of
  the analyses (it is not my spending);
- money given back by someone: an income linked to them, in the same excluded category (it is not my income).

In the balance sheet what people owe me is an asset, what I owe them a liability.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from flask_babel import gettext as _

from app.extensions import db
from app.models.category import Category
from app.models.personal_loan import PersonalLoan
from app.models.transaction import Transaction
from app.services import categories, money, splits
from app.services.i18n import N_

FOR_OTHERS = "Anticipi per altri"
KINDS = {  # what happened → the sign of the entry
    "lent": (N_("Ho prestato o anticipato"), 1),
    "repaid_me": (N_("Mi ha restituito"), -1),
    "borrowed": (N_("Mi ha prestato"), -1),
    "repaid_them": (N_("Gli ho restituito"), 1),
}
REMIND_DAYS = 7


@dataclass
class Person:
    name: str
    balance: Decimal          # + owes me, − I owe them
    entries: list[PersonalLoan]
    due: date | None          # the earliest due date of an open balance


def _name(text: str | None) -> str:
    """The person's name as first written («luca» is the «Luca» already there)."""
    name = " ".join((text or "").split())[:80]
    if not name:
        raise ValueError(_("Scrivi il nome della persona."))
    known = (db.session.query(PersonalLoan.person).filter(db.func.lower(PersonalLoan.person) == name.lower())
             .order_by(PersonalLoan.id).first())
    return known[0] if known else name


def add(person: str, kind: str, amount: Decimal | None, on: date | None, description: str | None = None,
        due: date | None = None, transaction: Transaction | None = None) -> PersonalLoan:
    if kind not in KINDS:
        raise ValueError(_("Scegli cosa è successo."))
    if amount is None or amount <= 0:
        raise ValueError(_("L'importo deve essere positivo."))
    entry = PersonalLoan(person=_name(person), date=on or date.today(), amount=money.cents(amount) * KINDS[kind][1],
                         description=(description or "").strip() or None, due=due,
                         transaction_id=transaction.id if transaction else None)
    db.session.add(entry)
    return entry


def people() -> list[Person]:
    """Everyone with entries, the ones with an open balance first (largest first)."""
    grouped = defaultdict(list)
    for entry in PersonalLoan.query.order_by(PersonalLoan.date, PersonalLoan.id):
        grouped[entry.person].append(entry)
    found = []
    for name, entries in grouped.items():
        balance = sum((Decimal(e.amount) for e in entries), Decimal(0))
        dues = [e.due for e in entries if e.due] if balance else []
        found.append(Person(name, balance, entries, min(dues) if dues else None))
    return sorted(found, key=lambda p: (p.balance == 0, -abs(p.balance), p.name.lower()))


def totals() -> dict[str, Decimal]:
    balances = [p.balance for p in people()]
    return {"owed_to_me": sum((b for b in balances if b > 0), Decimal(0)),
            "i_owe": -sum((b for b in balances if b < 0), Decimal(0))}


def due_soon(today: date | None = None) -> list[Person]:
    today = today or date.today()
    return [p for p in people() if p.balance and p.due and p.due <= today + timedelta(days=REMIND_DAYS)]


def _for_others_category() -> str:
    """«Anticipi per altri», left out of the analyses, made the first time."""
    category = Category.query.filter_by(name=FOR_OTHERS).first()
    if category is None:
        db.session.add(Category(name=FOR_OTHERS, kind="both", excluded=True, position=len(categories.all_categories()),
                                hint="soldi spesi per altri o restituiti da altri: non sono spese né entrate tue"))
        db.session.flush()
        categories.forget()
    return FOR_OTHERS


def share_expense(tx: Transaction, shares: dict[str, Decimal], on: date | None = None) -> list[PersonalLoan]:
    """An expense paid for others too: {person: their share}. My part stays in the expense's category."""
    if tx.type != "expense":
        raise ValueError(_("Si divide solo una spesa."))
    if tx.splits:
        raise ValueError(_("La spesa è già suddivisa in categorie: dividila con le persone prima di suddividerla."))
    shares = {_name(p): money.cents(a) for p, a in shares.items() if a}
    if not shares or any(a <= 0 for a in shares.values()):
        raise ValueError(_("Indica almeno una persona e la sua quota."))
    total, others = abs(Decimal(tx.amount)), sum(shares.values(), Decimal(0))
    if others >= total:
        raise ValueError(_("Le quote degli altri devono essere meno del totale (%(total)s).", total=total))
    splits.apply(tx, [(tx.category or categories.FALLBACK, total - others), (_for_others_category(), others)])
    return [add(person, "lent", amount, on or tx.date, tx.description, transaction=tx) for person, amount in shares.items()]


def equal_shares(total: Decimal, people_: list[str], with_me: bool = True) -> dict[str, Decimal]:
    """The total divided in equal parts among the people (and me): what each of them owes."""
    names = [_name(p) for p in people_ if p.strip()]
    if not names:
        raise ValueError(_("Indica almeno una persona."))
    each = money.cents(total / (len(names) + (1 if with_me else 0)))
    return {name: each for name in names}


def repayment(tx: Transaction, person: str) -> PersonalLoan:
    """An income from someone giving money back: it stops counting as my income."""
    if tx.type != "income":
        raise ValueError(_("Una restituzione è un'entrata."))
    tx.category = _for_others_category()
    return add(person, "repaid_me", abs(Decimal(tx.amount)), tx.date, tx.description, transaction=tx)


def recent(kind: str, days: int = 60) -> list[Transaction]:
    """Recent movements to share or to mark as given back."""
    since = date.today() - timedelta(days=days)
    query = Transaction.query.filter(Transaction.type == kind, Transaction.date >= since)
    if kind == "expense":
        query = query.filter(~Transaction.splits.any())
    else:
        query = query.filter((Transaction.category.is_(None)) | (Transaction.category != FOR_OTHERS))
    return query.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(50).all()
