"""
Reminders collected from the rest of the app: insurance expiries, recurring transactions and debt
installments coming up, budgets at 80% or over, savings goals running late. Nothing is stored except
the reminders the user dismissed (by key: a key includes the date, so next month's reminder shows again).
"""
import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from flask import url_for

from app.models.transaction import Transaction
from app.models.wealth import Debt, Goal, InsurancePolicy
from app.routes.settings import current_settings
from app.services import budgets, forecast, request_cache, settings_store, wealth

DISMISSED_SETTING = "notifications.dismissed"
KEEP_DISMISSED = 500
DAYS_AHEAD = 7            # recurring transactions and installments
POLICY_DAYS = 60          # insurance expiries
GOAL_DAYS = 30            # goals whose date is near
LEVELS = {"danger": 0, "warning": 1, "info": 2}


@dataclass
class Notification:
    key: str
    level: str      # "danger" | "warning" | "info"
    icon: str
    title: str
    detail: str
    when: date
    url: str

    def to_dict(self) -> dict:
        return asdict(self) | {"when": self.when.isoformat()}


def _money(value: float) -> str:
    return f"€ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _policies(today: date) -> list[Notification]:
    items = []
    for p in InsurancePolicy.query.filter(InsurancePolicy.expiry_date.isnot(None)).all():
        days = (p.expiry_date - today).days
        if -7 <= days <= POLICY_DAYS:
            level = "danger" if days < 0 else "warning" if days <= 15 else "info"
            when = "scaduta" if days < 0 else "scade oggi" if days == 0 else f"scade tra {days} giorni"
            items.append(Notification(f"policy-{p.id}-{p.expiry_date}", level, "shield-exclamation",
                                      f"Polizza {p.type} · {p.company}", f"{when.capitalize()} ({p.expiry_date:%d/%m/%Y})",
                                      p.expiry_date, url_for("insurance.edit", policy_id=p.id)))
    return items


def _recurring(today: date) -> list[Notification]:
    items = []
    end = today + timedelta(days=DAYS_AHEAD + 1)
    templates = forecast.scheduled_templates(Transaction.query.filter(Transaction.is_recurring.is_(True)).all())
    for tx in templates:
        for due in forecast.occurrences(tx, today, end):
            income = tx.type == "income"
            items.append(Notification(
                f"recurring-{tx.id}-{due}", "info", "arrow-repeat",
                f"{'Entrata' if income else 'Spesa'} ricorrente: {tx.description}",
                f"{_money(tx.magnitude)} il {due:%d/%m/%Y}", due, url_for("transactions.edit", tx_id=tx.id)))
    return items


def _installments(today: date) -> list[Notification]:
    items = []
    end = today + timedelta(days=DAYS_AHEAD)
    for debt in Debt.query.all():
        for row in wealth.schedule(debt):
            if today <= row.due <= end:
                items.append(Notification(f"debt-{debt.id}-{row.due}", "info", "credit-card",
                                          f"Rata {debt.name}", f"{_money(row.payment)} il {row.due:%d/%m/%Y}",
                                          row.due, url_for("debt.detail", debt_id=debt.id)))
            if row.due > end:
                break
    return items


def _budgets(today: date) -> list[Notification]:
    items = []
    for line in budgets.alerts(today):
        over = line["state"] == "over"
        items.append(Notification(
            f"budget-{line['category']}-{today:%Y-%m}-{line['state']}", "danger" if over else "warning", "clipboard-x",
            f"Budget {line['category']} {'superato' if over else 'quasi esaurito'}",
            f"Spesi {_money(line['spent'])} su {_money(line['planned'])} ({line['share']:.0f}%)",
            today, url_for("lifestyle.budget")))
    return items


def _goals(today: date) -> list[Notification]:
    items = []
    for goal in Goal.query.filter(Goal.target_date.isnot(None)).all():
        if goal.completed:
            continue
        days = (goal.target_date - today).days
        if days < 0:
            items.append(Notification(f"goal-{goal.id}-late", "warning", "trophy", f"Obiettivo «{goal.name}» scaduto",
                                      f"Mancano {_money(goal.remaining)}; sposta la data o aggiungi un versamento",
                                      goal.target_date, url_for("lifestyle.goals")))
        elif days <= GOAL_DAYS:
            items.append(Notification(f"goal-{goal.id}-{goal.target_date}", "info", "trophy",
                                      f"Obiettivo «{goal.name}» tra {days} giorni",
                                      f"Mancano {_money(goal.remaining)} ({goal.progress:.0f}% raggiunto)",
                                      goal.target_date, url_for("lifestyle.goals")))
    return items


# each source, and the setting that must be on for it (a module switched off gives no reminders)
SOURCES = ((_policies, "module_insurance"), (_recurring, None), (_installments, "module_debt"),
           (_budgets, None), (_goals, "lifestyle_goals"))


def dismissed() -> list[str]:
    try:
        keys = json.loads(settings_store.get(DISMISSED_SETTING) or "[]")
    except ValueError:
        return []
    return keys if isinstance(keys, list) else []


def collect(today: date | None = None, include_dismissed: bool = False) -> list[Notification]:
    """Every current reminder, most urgent first (cached for the request when not including dismissed)."""
    today = today or date.today()
    store, cache_key = request_cache.cache(), f"notifications-{today}"
    if not include_dismissed and cache_key in store:
        return store[cache_key]
    enabled = current_settings()
    items = [item for source, setting in SOURCES if not setting or enabled.get(setting, True) for item in source(today)]
    if not include_dismissed:
        hidden = set(dismissed())
        items = [item for item in items if item.key not in hidden]
    items.sort(key=lambda n: (LEVELS.get(n.level, 3), n.when))
    if not include_dismissed:
        store[cache_key] = items
    return items


def dismiss(keys: list[str]) -> None:
    current = dismissed()
    current.extend(k for k in keys if k not in current)
    settings_store.set(DISMISSED_SETTING, json.dumps(current[-KEEP_DISMISSED:]))
