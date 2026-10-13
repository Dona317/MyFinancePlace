"""
The cash wallet (F22): ATM withdrawals become giroconti to the «Contanti» account, cash spending is entered on it,
and counting what is in the wallet («ho 85 €») closes the gap — the difference with the app's balance is recorded as
spending nobody wrote down (or cash found), and the count is remembered like a reconciliation.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.services import accounts, money
from app.services.parsing import normalize

WITHDRAWAL = re.compile(r"\b(prelievo|prelevamento|prel bancomat|prel atm|bancomat atm|atm withdrawal|cash withdrawal|"
                        r"ritiro contanti|prelievo contanti)\b")
WALLET_NAME = "Contanti"
UNRECORDED = "Spese non annotate"
FOUND = "Contanti trovati"


def is_withdrawal(*texts: str | None) -> bool:
    return bool(WITHDRAWAL.search(normalize(" ".join(t for t in texts if t))))


def wallet(create: bool = False) -> Account | None:
    """The cash account (the first active one), made the first time it is needed when `create`."""
    found = Account.query.filter_by(kind="cash", active=True).order_by(Account.id).first()
    if found is None and create:
        name, number = WALLET_NAME, 2
        while Account.query.filter_by(name=name).first() is not None:
            name, number = f"{WALLET_NAME} {number}", number + 1
        found = Account(name=name, kind="cash", currency="EUR")
        db.session.add(found)
        db.session.flush()
    return found


def count(account: Account, counted: Decimal, on: date | None = None) -> Transaction | None:
    """What is in the wallet now: the difference with the balance becomes a movement, and the count is remembered."""
    on = on or date.today()
    if account.kind != "cash":
        raise ValueError(_("Si contano solo i conti di contanti."))
    if counted is None or counted < 0:
        raise ValueError(_("Scrivi quanti contanti hai (zero o più)."))
    difference = money.cents(counted - Decimal(str(accounts.balance(account, on))))
    tx = None
    if difference:
        spent = difference < 0
        tx = Transaction(date=on, amount=abs(difference), currency=account.currency, account_id=account.id,
                         type="expense" if spent else "income", category=UNRECORDED if spent else FOUND,
                         description=_("Conta dei contanti: spese non annotate") if spent
                         else _("Conta dei contanti: contanti in più"), tags=[])
        db.session.add(tx)
    account.reconciled_on, account.reconciled_balance = on, counted
    return tx


def negative() -> list[tuple[Account, float]]:
    """Cash accounts below zero: a withdrawal or an income was not recorded."""
    return [(a, balance) for a in Account.query.filter_by(kind="cash", active=True).order_by(Account.name)
            if (balance := accounts.balance(a)) < -0.005]
