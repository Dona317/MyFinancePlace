"""
Data health (F20): what in the archive needs fixing, in one list, each problem with a link to where it is fixed.

- danger: the numbers are wrong (a holding sold beyond what it held, money in a currency without exchange rates);
  these also become reminders (services.notifications)
- warning: the numbers may be wrong (stale prices, giroconti with one side only, possible duplicates)
- info: tidiness (movements without a category, instruments that cannot be priced, accounts never reconciled)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from flask import url_for
from flask_babel import gettext as _
from sqlalchemy import or_

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import cash, categories, currency, display, duplicates, wealth

STALE_DAYS = 7
RECONCILE_DAYS = 90
UNCATEGORIZED_MONTHS = 12
SHOWN = 20  # items listed per check (the count says how many there are)
LEVELS = {"danger": 0, "warning": 1, "info": 2}


@dataclass
class Item:
    label: str
    url: str


@dataclass
class Check:
    key: str
    level: str
    title: str
    hint: str
    count: int
    items: list[Item] = field(default_factory=list)
    url: str | None = None  # where the whole list is fixed


def _investments() -> list[Holding]:
    classes = [name for name, (_line, investing) in wealth.ASSET_CLASSES.items() if investing]
    return Holding.query.filter(Holding.asset_class.in_(classes)).order_by(Holding.name).all()


def _holding_item(h: Holding, detail: str) -> Item:
    return Item(f"{h.name} — {detail}", url_for("portfolio.detail", holding_id=h.id))


def _oversold(today: date) -> Check:
    found = Holding.query.filter(Holding.quantity < 0).order_by(Holding.name).all()
    return Check("oversold", "danger", _("Titoli con quantità negativa"),
                 _("Una vendita supera le quote possedute: manca un acquisto o la posizione iniziale."), len(found),
                 [_holding_item(h, display.plain(h.quantity)) for h in found[:SHOWN]])


def _missing_rates(today: date) -> Check:
    found = [row for row in currency.foreign_usage() if not row["has_rates"]]
    return Check("rates", "danger", _("Valute senza tassi di cambio"),
                 _("I movimenti in queste valute non si possono convertire in euro."), len(found),
                 [Item(_("%(currency)s: %(count)s movimenti", currency=row["currency"], count=row["count"]),
                       url_for("settings.currencies_page")) for row in found], url_for("settings.currencies_page"))


def _stale_prices(today: date) -> Check:
    limit = today - timedelta(days=STALE_DAYS)
    found = [h for h in _investments() if h.price_source != "manual"
             and (h.price_date is None or h.price_date < limit) and h.quantity]
    return Check("stale", "warning", _("Prezzi vecchi"),
                 _("Prezzo più vecchio di %(days)s giorni: aggiornali o inseriscili a mano.", days=STALE_DAYS),
                 len(found), [_holding_item(h, display.day(h.price_date) if h.price_date else _("mai"))
                              for h in found[:SHOWN]], url_for("portfolio.prices"))


def _half_transfers(today: date) -> Check:
    query = (Transaction.query.filter(Transaction.type == "transfer", Transaction.holding_id.is_(None),
                                      Transaction.debt_id.is_(None),
                                      or_(Transaction.account_id.is_(None), Transaction.counter_account_id.is_(None)))
             .order_by(Transaction.date.desc()))
    found = query.limit(SHOWN).all()
    return Check("transfers", "warning", _("Giroconti con un solo conto"),
                 _("Manca il conto di partenza o di arrivo: il saldo di uno dei due conti è sbagliato."),
                 query.count(), [Item(f"{display.day(tx.date)} · {tx.description} · {display.money(tx.amount)}",
                                      url_for("transactions.edit", tx_id=tx.id)) for tx in found])


def _duplicates(today: date) -> Check:
    groups = duplicates.find_groups()
    return Check("duplicates", "warning", _("Possibili doppioni"),
                 _("Movimenti con stesso importo, data vicina e descrizione simile."), len(groups), [],
                 url_for("transactions.duplicates_page"))


def _uncategorized(today: date) -> Check:
    since = today - timedelta(days=UNCATEGORIZED_MONTHS * 31)
    query = Transaction.query.filter(Transaction.date >= since, Transaction.type != "transfer",
                                     or_(Transaction.category.is_(None), Transaction.category == "",
                                         Transaction.category == categories.FALLBACK))
    return Check("uncategorized", "info", _("Movimenti senza categoria"),
                 _("Ultimi 12 mesi, in «%(name)s» o senza categoria: i report li contano a parte.",
                   name=categories.FALLBACK), query.count(), [],
                 url_for("transactions.index", category=categories.FALLBACK))


def _unpriceable(today: date) -> Check:
    found = [h for h in _investments() if not h.isin and not h.ticker and h.price_source != "manual"]
    return Check("unpriceable", "info", _("Titoli senza ISIN né ticker"),
                 _("Il prezzo non si può cercare su internet: aggiungi l'ISIN o scegli il prezzo manuale."),
                 len(found), [_holding_item(h, h.asset_class) for h in found[:SHOWN]])


def _unreconciled(today: date) -> Check:
    limit = today - timedelta(days=RECONCILE_DAYS)
    found = [a for a in Account.query.filter_by(active=True).order_by(Account.name)
             if a.reconciled_on is None or a.reconciled_on < limit]
    return Check("reconcile", "info", _("Conti da riconciliare"),
                 _("Saldo mai confrontato con l'estratto conto, o non da più di %(days)s giorni.", days=RECONCILE_DAYS),
                 len(found), [Item(f"{a.name} — {display.day(a.reconciled_on) if a.reconciled_on else _('mai')}",
                                   url_for("accounts.index")) for a in found[:SHOWN]], url_for("accounts.index"))


def _negative_cash(today: date) -> Check:
    """A cash wallet below zero: a withdrawal or an income in cash was not recorded (F22)."""
    found = cash.negative()
    return Check("cash", "warning", _("Contanti in negativo"),
                 _("Il saldo dei contanti è sotto zero: manca un prelievo o un'entrata in contanti, oppure conta il portafoglio."),
                 len(found), [Item(f"{a.name} — {display.money(balance)}", url_for("accounts.detail", account_id=a.id))
                              for a, balance in found[:SHOWN]], url_for("accounts.index"))


CHECKS = (_oversold, _negative_cash, _missing_rates, _stale_prices, _half_transfers, _duplicates, _uncategorized, _unpriceable,
          _unreconciled)
SEVERE = (_oversold, _missing_rates)  # cheap enough to run on every page, for the reminders


def run(today: date | None = None, checks=CHECKS) -> list[Check]:
    """The checks, problems first (most serious first), then the ones that are fine."""
    today = today or date.today()
    results = [check(today) for check in checks]
    return sorted(results, key=lambda c: (c.count == 0, LEVELS[c.level]))


def severe(today: date | None = None) -> list[Check]:
    return [check for check in run(today, SEVERE) if check.count]
