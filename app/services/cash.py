"""
The cash wallet (F22): ATM withdrawals become giroconti to the «Contanti» account and cash paid in at the bank
(«versamento contanti») giroconti from it, cash spending is entered on it,
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
DEPOSIT = re.compile(r"\b(versamento contanti|versamento contante|vers contanti|versamento atm|versamento bancomat|"
                     r"versamento banconote|vers banconote|versamento in contanti|deposito contanti|cash deposit|"
                     r"atm deposit)\b")
WALLET_NAME = "Contanti"
UNRECORDED = "Spese non annotate"
FOUND = "Contanti trovati"


def is_withdrawal(*texts: str | None) -> bool:
    return bool(WITHDRAWAL.search(normalize(" ".join(t for t in texts if t))))


def is_deposit(*texts: str | None) -> bool:
    return bool(DEPOSIT.search(normalize(" ".join(t for t in texts if t))))


def realign() -> int:
    """The movements of the register that are cash going in or out of a bank account but were saved as an expense
    (a withdrawal) or an income (cash paid in): each one becomes a giroconto with Contanti, the wallet made if
    needed. Returns how many changed. Run on every import and once a day."""
    banks = [a.id for a in Account.query.filter(Account.kind.notin_(("cash", "debt")))]
    if not banks:
        return 0
    changed = 0
    candidates = Transaction.query.filter(Transaction.type.in_(["income", "expense"]), Transaction.account_id.in_(banks),
                                          Transaction.holding_id.is_(None), Transaction.debt_id.is_(None))
    for tx in candidates:
        if tx.type == "expense" and is_withdrawal(tx.description, tx.bank_description):
            tx.type, tx.counter_account_id = "transfer", wallet(create=True).id  # from the bank to the cash
        elif tx.type == "income" and is_deposit(tx.description, tx.bank_description):
            # from the cash to the bank: the cash is the account it leaves, the bank the one it arrives on
            tx.type, tx.account_id, tx.counter_account_id = "transfer", wallet(create=True).id, tx.account_id
        else:
            continue
        tx.category = "Giroconto"
        changed += 1
    if changed:
        db.session.commit()
    return changed


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


def tracking(account: Account, year: int) -> dict:
    """How much of the cash spent in `year` was written down: the spending entered one by one, and what a count
    found missing («Spese non annotate»). The share written down is what the cash page encourages to raise."""
    start, end = date(year, 1, 1), date(year + 1, 1, 1)
    spent = Transaction.query.filter(Transaction.account_id == account.id, Transaction.type == "expense",
                                     Transaction.date >= start, Transaction.date < end).all()
    unrecorded = sum(abs(Decimal(t.amount)) for t in spent if t.category == UNRECORDED)
    recorded = sum(abs(Decimal(t.amount)) for t in spent if t.category != UNRECORDED)
    total = recorded + unrecorded
    return {"year": year, "recorded": float(recorded), "unrecorded": float(unrecorded),
            "share": round(float(recorded / total * 100), 1) if total else None}


def negative() -> list[tuple[Account, float]]:
    """Cash accounts below zero: a withdrawal or an income was not recorded."""
    return [(a, balance) for a in Account.query.filter_by(kind="cash", active=True).order_by(Account.name)
            if (balance := accounts.balance(a)) < -0.005]
