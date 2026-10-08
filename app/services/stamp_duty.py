"""
Stamp duty and IVAFE of a year (F15), for an individual:

- **current accounts**: 34,20 euro when the average balance of the year is above 5.000 euro (giacenza media,
  from the daily balances of the transactions); an account abroad pays the same as IVAFE;
- **deposit accounts and investments**: 0,2% of the value at the end of the year (or today, for the current
  year) — stamp duty in Italy, IVAFE abroad; crypto held abroad or in a private wallet pay the IC (imposta sul
  valore delle cripto-attività), also 0,2%.

Cards and cash pay nothing. An estimate: the bank's statement says what it actually charged (the duty is pro rata
for accounts opened or closed during the year).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.models.account import Account
from app.models.wealth import Holding
from app.services import accounts, tax_rules, wealth
from app.services.i18n import N_

CENT = Decimal("0.01")
BOLLO, IVAFE, IC = N_("Imposta di bollo"), N_("IVAFE"), N_("IC cripto-attività")
SAVINGS_CLASS = "Conto Risparmio"


@dataclass
class Duty:
    name: str
    tax: str          # BOLLO, IVAFE or IC
    basis: str        # what the duty is computed on, in words
    base: Decimal     # average balance or value
    amount: Decimal
    account: Account | None = None
    holding: Holding | None = None


def _period(year: int, today: date) -> tuple[date, date]:
    return date(year, 1, 1), min(date(year, 12, 31), today)


def _percent(value: Decimal) -> Decimal:
    return (max(value, Decimal(0)) * tax_rules.SECURITIES_RATE / 100).quantize(CENT, rounding=ROUND_HALF_UP)


def account_duties(year: int, today: date | None = None) -> list[Duty]:
    today = today or date.today()
    start, end = _period(year, today)
    duties = []
    for account in Account.query.filter(Account.kind.in_(("current", "savings"))).order_by(Account.name):
        tax = IVAFE if account.abroad else BOLLO
        if account.kind == "current":
            average = Decimal(str(accounts.average_balance(account, start, end)))
            due = tax_rules.ACCOUNT_DUTY if average > tax_rules.ACCOUNT_DUTY_THRESHOLD else Decimal(0)
            duties.append(Duty(account.name, tax, N_("giacenza media"), average, due, account=account))
        else:
            value = Decimal(str(accounts.balance(account, end)))
            duties.append(Duty(account.name, tax, N_("saldo a fine anno"), value, _percent(value), account=account))
    return duties


def holding_duties(year: int, today: date | None = None) -> list[Duty]:
    today = today or date.today()
    _, end = _period(year, today)
    prices = wealth.prices_on(end)
    duties = []
    for holding in wealth.holdings_on(end):
        if holding.asset_class not in tax_rules.MARKET_CLASSES + (SAVINGS_CLASS,):
            continue
        value = Decimal(str(round(wealth.value_on(holding, end, prices), 2)))
        if holding.asset_class == tax_rules.CRYPTO:
            tax = IC if holding.abroad else BOLLO
        else:
            tax = IVAFE if holding.abroad else BOLLO
        duties.append(Duty(holding.name, tax, N_("valore a fine anno"), value, _percent(value), holding=holding))
    return duties


def year_summary(year: int, today: date | None = None) -> dict:
    duties = account_duties(year, today) + holding_duties(year, today)
    totals = {}
    for duty in duties:
        totals[duty.tax] = totals.get(duty.tax, Decimal(0)) + duty.amount
    return {"year": year, "duties": duties, "totals": totals, "total": sum(totals.values(), Decimal(0)),
            "partial": year >= (today or date.today()).year}
