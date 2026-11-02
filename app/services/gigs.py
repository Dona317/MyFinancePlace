"""
Odd jobs and occasional work (F22): the register of the year, what is still to be collected, the INPS threshold and
the figures for the tax return.

- Withholding: 20 % of the gross when the client is a withholding agent (a company, a professional); a private person
  pays the gross. Net = gross − withholding.
- INPS: occasional self-employment above 5.000 € gross a year (all clients together) owes contributions to the
  gestione separata on the part above: a warning from 80 %.
- Tax return: «redditi diversi» (730 quadro D, rigo D5 / Redditi PF quadro RL): the gross, the expenses of the jobs
  and the withholdings already paid.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.gig import Gig
from app.models.transaction import Transaction
from app.services import money
from app.services.i18n import N_

WITHHOLDING = Decimal(20)
INPS_THRESHOLD = Decimal(5000)
WARN_AT = Decimal("0.8")
LATE_DAYS = 30
CATEGORY = "Lavori occasionali"
METHODS = {"cash": N_("Contanti"), "transfer": N_("Bonifico"), "other": N_("Altro")}


def withholding(gig: Gig) -> Decimal:
    return money.cents(Decimal(gig.gross) * Decimal(gig.withholding_rate) / 100, half_up=True)


def net(gig: Gig) -> Decimal:
    return Decimal(gig.gross) - withholding(gig)


def paid(gig: Gig) -> bool:
    return gig.paid_on is not None


@dataclass
class Year:
    year: int
    gigs: list[Gig]
    gross: Decimal
    withheld: Decimal
    expenses: Decimal
    net: Decimal
    to_collect: Decimal
    by_client: list[tuple[str, Decimal, int]]

    @property
    def threshold_pct(self) -> float:
        return min(float(self.gross / INPS_THRESHOLD * 100), 100.0)

    @property
    def over_threshold(self) -> Decimal:
        return max(self.gross - INPS_THRESHOLD, Decimal(0))

    @property
    def near_threshold(self) -> bool:
        return self.gross >= INPS_THRESHOLD * WARN_AT

    @property
    def taxable(self) -> Decimal:
        """Redditi diversi: the gross less the expenses of the jobs (never below zero)."""
        return max(self.gross - self.expenses, Decimal(0))


def year(year_: int) -> Year:
    gigs = (Gig.query.filter(Gig.date >= date(year_, 1, 1), Gig.date <= date(year_, 12, 31))
            .order_by(Gig.date.desc(), Gig.id.desc()).all())
    clients = defaultdict(lambda: [Decimal(0), 0])
    for gig in gigs:
        clients[gig.client][0] += Decimal(gig.gross)
        clients[gig.client][1] += 1
    return Year(year_, gigs, sum((Decimal(g.gross) for g in gigs), Decimal(0)),
                sum((withholding(g) for g in gigs), Decimal(0)), sum((Decimal(g.expenses) for g in gigs), Decimal(0)),
                sum((net(g) for g in gigs), Decimal(0)), sum((net(g) for g in gigs if not paid(g)), Decimal(0)),
                sorted(((name, total, count) for name, (total, count) in clients.items()), key=lambda row: -row[1]))


def years() -> list[int]:
    found = {d.year for (d,) in db.session.query(Gig.date)}
    return sorted(found | {date.today().year}, reverse=True)


def clients() -> list[str]:
    return [name for (name,) in db.session.query(Gig.client).distinct().order_by(Gig.client)]


def save(gig: Gig, *, client: str, description: str, owner: str | None, on: date | None, hours: Decimal | None,
         gross: Decimal | None, withholding_agent: bool, expenses: Decimal | None, method: str, notes: str | None) -> Gig:
    client, description = " ".join((client or "").split()), " ".join((description or "").split())
    if not client or not description:
        raise ValueError(_("Scrivi per chi e che lavoro."))
    if on is None:
        raise ValueError(_("Scrivi la data del lavoro."))
    if gross is None or gross <= 0:
        raise ValueError(_("Il compenso lordo deve essere positivo."))
    if (hours is not None and hours < 0) or (expenses is not None and expenses < 0):
        raise ValueError(_("Ore e spese non possono essere negative."))
    gig.client, gig.description, gig.owner, gig.date, gig.hours = client[:120], description[:200], owner, on, hours
    gig.gross, gig.withholding_rate = gross, WITHHOLDING if withholding_agent else Decimal(0)
    gig.expenses, gig.method = expenses or Decimal(0), method if method in METHODS else "other"
    gig.notes = (notes or "").strip() or None
    db.session.add(gig)
    return gig


def collect(gig: Gig, account: Account | None, on: date | None = None) -> Transaction:
    """Paid: the net arrives on the account (the cash wallet, or the bank), as an income of the category."""
    if paid(gig):
        raise ValueError(_("Il lavoro è già incassato."))
    on = on or date.today()
    tx = Transaction(date=on, amount=net(gig), currency=account.currency if account else "EUR", type="income",
                     category=CATEGORY, description=_("%(client)s: %(job)s", client=gig.client, job=gig.description),
                     counterparty=gig.client, account_id=account.id if account else None, tags=[])
    db.session.add(tx)
    db.session.flush()
    gig.transaction_id, gig.paid_on = tx.id, on
    return tx


def link(gig: Gig, tx: Transaction) -> None:
    """Paid by a movement already in the archive (from the bank statement)."""
    if tx.type != "income":
        raise ValueError(_("Si collega solo un'entrata."))
    gig.transaction_id, gig.paid_on = tx.id, tx.date


def unpay(gig: Gig) -> None:
    """Back to «to be collected»; the movement made by «collect» goes with it, one linked from the bank stays."""
    tx = gig.transaction
    if tx is not None and tx.category == CATEGORY and tx.counterparty == gig.client and tx.import_ref is None:
        db.session.delete(tx)
    gig.transaction_id, gig.paid_on = None, None


def candidates(gig: Gig) -> list[Transaction]:
    """Incomes near the job's date with about its net, to link."""
    target = net(gig)
    return (Transaction.query.filter(Transaction.type == "income", Transaction.date >= gig.date - timedelta(days=7),
                                     Transaction.date <= gig.date + timedelta(days=90),
                                     Transaction.amount.between(target - 1, Decimal(gig.gross) + 1))
            .order_by(Transaction.date).limit(10).all())


def late(today: date | None = None) -> list[Gig]:
    today = today or date.today()
    return (Gig.query.filter(Gig.paid_on.is_(None), Gig.date < today - timedelta(days=LATE_DAYS))
            .order_by(Gig.date).all())
