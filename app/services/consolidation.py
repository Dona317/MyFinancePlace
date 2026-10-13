"""
The consolidated view of a group of archives (F21): each member's numbers, computed in its own archive with the
same services as its pages, and their sum.

- Net worth (cash, investments, other assets, debts) today and at the end of each of the last 12 months; income and
  expenses of the last 12 months, spending by category, passive income; investments merged by ISIN (or ticker, or
  name) with the allocation by class; debts and goals with the archive they belong to.
- Money moved between two archives of the group (Marco pays Giulia's share of the rent) is an expense in one and an
  income in the other: added up it would count twice. A movement whose causale names the IBAN of an account of
  another member, or one of its holders (Impostazioni → Titolari e IBAN), is an *internal move*: it is left out of
  the consolidated income and expenses and listed apart.
- An archive whose totals are in another currency (Settings → Visualizzazione) is shown but not added up.

Read only: nothing is written in any archive.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from app.models.account import Account
from app.models.client import Client, ClientGroup
from app.models.transaction import Transaction
from app.models.wealth import Debt, Goal
from app.services import (
    analytics,
    categories,
    currency,
    income_report,
    owners,
    periods,
    portfolio_models,
    studio,
    wealth,
)
from app.services.parsing import normalize
from app.services.spending_rhythm import by_category

MONTHS = 12


@dataclass
class Identity:
    """What names an archive in someone else's causale: the IBANs of its accounts and its holders."""
    ibans: set[str]
    names: list[list[str]]


@dataclass
class Member:
    client: Client
    currency: str
    included: bool = True
    net_worth: float = 0.0
    cash: float = 0.0
    investments: float = 0.0
    other_assets: float = 0.0
    liabilities: float = 0.0
    passive_12: float = 0.0
    trend: list[float] = field(default_factory=list)
    income: list[float] = field(default_factory=list)      # per month, internal moves left out
    expenses: list[float] = field(default_factory=list)
    spending: dict[str, float] = field(default_factory=dict)
    holdings: list[dict] = field(default_factory=list)
    debts: list[dict] = field(default_factory=list)
    goals: list[dict] = field(default_factory=list)
    internal: list[dict] = field(default_factory=list)
    labels: dict[str, list[str]] = field(default_factory=dict)  # of the trend and of the months

    @property
    def income_12(self) -> float:
        return round(sum(self.income), 2)

    @property
    def expenses_12(self) -> float:
        return round(sum(self.expenses), 2)


def _identity() -> Identity:
    ibans = {iban for (iban,) in Account.query.with_entities(Account.iban).filter(Account.iban.isnot(None))}
    return Identity(ibans, [normalize(name).split() for name in owners.holders()])


def _names_other(text: str, compact: str, own: list[list[str]], others: dict[int, Identity]) -> int | None:
    """The member (client id) a causale names, other than the archive's own holders."""
    words = set(normalize(text).split())
    for client_id, other in others.items():
        if any(iban in compact for iban in other.ibans):
            return client_id
        if any(name not in own and all(part in words for part in name) for name in other.names):
            return client_id
    return None


def _internal_moves(start: date, end: date, own: Identity, others: dict[int, Identity]) -> list[dict]:
    if not others:
        return []
    found = []
    query = Transaction.query.filter(Transaction.type.in_(["income", "expense"]), Transaction.date >= start,
                                     Transaction.date < end).order_by(Transaction.date)
    for tx in query:
        text = " ".join(t for t in (tx.description, tx.bank_description, tx.counterparty) if t)
        other = _names_other(text, re.sub(r"\s", "", text).upper(), own.names, others)
        if other is not None:
            found.append({"date": tx.date, "description": tx.description, "type": tx.type, "other": other,
                          "category": categories.main_or(tx.category, categories.FALLBACK),
                          "amount": round(float(abs(tx.amount_base if tx.amount_base is not None else tx.amount)), 2)})
    return found


def _holding(h) -> dict:
    return {"key": (h.isin or "").upper() or (h.ticker or "").upper() or h.name.strip().lower(), "name": h.name,
            "isin": h.isin, "ticker": h.ticker, "asset_class": h.asset_class, "units": h.units,
            "value": round(h.value, 2), "cost": round(h.cost, 2)}


def _measure(member: Member, today: date, start: date, end: date, own: Identity, others: dict[int, Identity]) -> None:
    """Fill `member` from the archive that is open now."""
    sheet = wealth.balance_sheet()
    member.net_worth, member.cash, member.investments = sheet["net_worth"], sheet["cash"], sheet["investments"]
    member.liabilities = sheet["total_liabilities"]
    member.other_assets = round(sheet["total_assets"] - sheet["cash"] - sheet["investments"], 2)
    trend, flows = wealth.net_worth_trend(MONTHS, today), analytics.last_12_months(today)
    member.trend, member.labels = trend["data"], {"trend": trend["labels"], "months": flows["labels"]}
    member.income, member.expenses = list(flows["income"]), list(flows["expenses"])
    member.spending = {name: float(value) for name, value in by_category(start, today).items()}
    member.internal = _internal_moves(start, end, own, others)
    for move in member.internal:
        index = (move["date"].year - start.year) * 12 + move["date"].month - start.month
        series = member.income if move["type"] == "income" else member.expenses
        series[index] = round(series[index] - move["amount"], 2)
        if move["type"] == "expense":
            member.spending[move["category"]] = member.spending.get(move["category"], 0.0) - move["amount"]
    member.spending = {k: round(v, 2) for k, v in member.spending.items() if round(v, 2) > 0}
    member.passive_12 = float(income_report.report(today.year, today)["last_12"])
    member.holdings = [_holding(h) for h in portfolio_models.investments() if h.value]
    member.debts = [{"name": d.name, "type": d.type, "balance": s["balance"]}
                    for d in Debt.query.order_by(Debt.name) if (s := wealth.debt_summary(d, today))["balance"] > 0]
    member.goals = [{"name": g.name, "target": float(g.target_amount), "saved": float(g.saved_amount),
                     "progress": g.progress} for g in Goal.query.order_by(Goal.name)]


def _merge_holdings(members: list[Member]) -> list[dict]:
    merged: dict[str, dict] = {}
    for member in members:
        for h in member.holdings:
            row = merged.setdefault(h["key"], {**h, "units": 0.0, "value": 0.0, "cost": 0.0, "members": []})
            row["units"] += h["units"]
            row["value"] += h["value"]
            row["cost"] += h["cost"]
            row["members"].append(member.client.name)
    rows = sorted(merged.values(), key=lambda r: -r["value"])
    for row in rows:
        row["value"], row["cost"] = round(row["value"], 2), round(row["cost"], 2)
        row["gain"] = round(row["value"] - row["cost"], 2)
        row["gain_pct"] = round(row["gain"] / row["cost"] * 100, 1) if row["cost"] else 0.0
    return rows


def _total(members: list[Member], attr: str) -> float:
    return round(sum(getattr(m, attr) for m in members), 2)


def _sum_series(series: list[list[float]]) -> list[float]:
    return [round(sum(values), 2) for values in zip(*series)] if series else [0.0] * MONTHS


def consolidate(group: ClientGroup, today: date | None = None) -> dict:
    """Every member's numbers and the group's totals (computed once: a page and its charts share the result)."""
    today = today or date.today()
    start = periods.add_months(periods.first_of_month(today), -(MONTHS - 1))
    end = periods.add_months(periods.first_of_month(today), 1)
    clients = sorted(group.members, key=lambda c: (not c.is_primary, c.name))
    identities, currencies = {}, {}
    for client in clients:
        with studio.using(client):
            identities[client.id], currencies[client.id] = _identity(), currency.base()
    group_currency = currencies[clients[0].id] if clients else currency.BASE
    members = []
    for client in clients:
        member = Member(client, currencies[client.id], currencies[client.id] == group_currency)
        others = {cid: identity for cid, identity in identities.items()
                  if cid != client.id and currencies[cid] == group_currency}
        with studio.using(client):
            _measure(member, today, start, end, identities[client.id], others)
        members.append(member)
    names = {client.id: client.name for client in clients}
    summed = [m for m in members if m.included]
    spending = defaultdict(float)
    for member in summed:
        for name, value in member.spending.items():
            spending[name] += value
    holdings = _merge_holdings(summed)
    allocation = defaultdict(float)
    for row in holdings:
        allocation[row["asset_class"] or categories.FALLBACK] += row["value"]
    internal = sorted(({**move, "member": member.client.name, "other_name": names[move["other"]]}
                       for member in summed for move in member.internal), key=lambda move: move["date"])
    return {
        "group": group, "today": today, "currency": group_currency, "members": members,
        "excluded": [m for m in members if not m.included],
        "labels": members[0].labels["trend"] if members else [], "months": members[0].labels["months"] if members else [],
        "net_worth": _total(summed, "net_worth"), "cash": _total(summed, "cash"),
        "investments": _total(summed, "investments"), "other_assets": _total(summed, "other_assets"),
        "liabilities": _total(summed, "liabilities"), "passive_12": _total(summed, "passive_12"),
        "income_12": _total(summed, "income_12"), "expenses_12": _total(summed, "expenses_12"),
        "trend": _sum_series([m.trend for m in summed]), "income": _sum_series([m.income for m in summed]),
        "expenses": _sum_series([m.expenses for m in summed]),
        "spending": sorted(((k, round(v, 2)) for k, v in spending.items()), key=lambda kv: -kv[1]),
        "holdings": holdings, "allocation": sorted(((k, round(v, 2)) for k, v in allocation.items()), key=lambda kv: -kv[1]),
        "debts": [{**d, "member": m.client.name} for m in summed for d in m.debts],
        "goals": [{**g, "member": m.client.name} for m in summed for g in m.goals],
        "internal": internal, "internal_total": round(sum(move["amount"] for move in internal if move["type"] == "expense"), 2),
    }


def csv_rows(data: dict) -> list[list]:
    """The consolidated table: one row per archive, then the group's total."""
    header = ["Archivio", "Valuta", "Liquidità", "Investimenti", "Altri beni", "Debiti", "Patrimonio netto",
              "Entrate 12 mesi", "Uscite 12 mesi", "Rendite 12 mesi", "Sommato"]
    rows = [header]
    for m in data["members"]:
        rows.append([m.client.name, m.currency, m.cash, m.investments, m.other_assets, m.liabilities, m.net_worth,
                     m.income_12, m.expenses_12, m.passive_12, "sì" if m.included else "no"])
    rows.append([data["group"].name, data["currency"], data["cash"], data["investments"], data["other_assets"],
                 data["liabilities"], data["net_worth"], data["income_12"], data["expenses_12"], data["passive_12"], ""])
    return rows
