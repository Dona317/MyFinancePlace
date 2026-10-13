"""
Reminders collected from the rest of the app: insurance expiries, recurring transactions and debt
installments coming up, budgets at 80% or over, savings goals running late. Nothing is stored except
the reminders the user dismissed (by key: a key includes the date, so next month's reminder shows again).
"""
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from flask import url_for
from flask_babel import gettext as _

from app.models.transaction import Transaction
from app.models.wealth import Debt, Goal, InsurancePolicy
from app.services import (
    budgets,
    contribution_limits,
    data_health,
    display,
    forecast,
    gigs,
    investment_plans,
    portfolio_rules,
    request_cache,
    sections,
    settings_store,
    wealth,
)
from app.services.i18n import tr

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
    return display.money(value)


def _policies(today: date) -> list[Notification]:
    items = []
    for p in InsurancePolicy.query.filter(InsurancePolicy.expiry_date.isnot(None)).all():
        days = (p.expiry_date - today).days
        if -7 <= days <= POLICY_DAYS:
            level = "danger" if days < 0 else "warning" if days <= 15 else "info"
            when = _("Scaduta") if days < 0 else _("Scade oggi") if days == 0 else _("Scade tra %(days)s giorni", days=days)
            items.append(Notification(f"policy-{p.id}-{p.expiry_date}", level, "shield-exclamation",
                                      _("Polizza %(type)s · %(company)s", type=tr(p.type), company=p.company), f"{when} ({display.day(p.expiry_date)})",
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
                (_("Entrata ricorrente: %(description)s", description=tx.description) if income
                 else _("Spesa ricorrente: %(description)s", description=tx.description)),
                _("%(amount)s il %(day)s", amount=_money(tx.magnitude), day=display.day(due)), due, url_for("transactions.edit", tx_id=tx.id)))
    return items


def _installments(today: date) -> list[Notification]:
    items = []
    end = today + timedelta(days=DAYS_AHEAD)
    for debt in Debt.query.all():
        for row in wealth.schedule(debt):
            if today <= row.due <= end:
                items.append(Notification(f"debt-{debt.id}-{row.due}", "info", "credit-card",
                                          _("Rata %(name)s", name=debt.name), _("%(amount)s il %(day)s", amount=_money(row.payment), day=display.day(row.due)),
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
            (_("Budget %(category)s superato", category=line['category']) if over
             else _("Budget %(category)s quasi esaurito", category=line['category'])),
            _("Spesi %(spent)s su %(planned)s (%(share)s%%)", spent=_money(line['spent']), planned=_money(line['planned']),
              share=f"{line['share']:.0f}"),
            today, url_for("lifestyle.budget")))
    return items


def _goals(today: date) -> list[Notification]:
    items = []
    for goal in Goal.query.filter(Goal.target_date.isnot(None)).all():
        if goal.completed:
            continue
        days = (goal.target_date - today).days
        if days < 0:
            items.append(Notification(f"goal-{goal.id}-late", "warning", "trophy", _("Obiettivo «%(name)s» scaduto", name=goal.name),
                                      _("Mancano %(amount)s; sposta la data o aggiungi un versamento", amount=_money(goal.remaining)),
                                      goal.target_date, url_for("lifestyle.goals")))
        elif days <= GOAL_DAYS:
            items.append(Notification(f"goal-{goal.id}-{goal.target_date}", "info", "trophy",
                                      _("Obiettivo «%(name)s» tra %(days)s giorni", name=goal.name, days=days),
                                      _("Mancano %(amount)s (%(progress)s%% raggiunto)", amount=_money(goal.remaining),
                                        progress=f"{goal.progress:.0f}"),
                                      goal.target_date, url_for("lifestyle.goals")))
    return items


def _portfolio(today: date) -> list[Notification]:
    """The rules on the investments that tripped, and the PAC instalments to confirm."""
    items = [Notification(a.key, a.level, "graph-down-arrow" if a.level == "warning" else "bell", a.title, a.detail, a.when,
                          a.url) for a in portfolio_rules.evaluate(today)]
    for plan in investment_plans.due(today):
        items.append(Notification(f"plan-{plan.id}-{investment_plans.period(today)}", "info", "piggy-bank",
                                  _("PAC «%(name)s»: %(amount)s da investire", name=plan.name, amount=_money(plan.amount)),
                                  _("Conferma gli acquisti del %(day)s", day=display.day(investment_plans.due_date(plan, today))),
                                  today, url_for("portfolio.plan_run", plan_id=plan.id)))
    return items


def _data_health(today: date) -> list[Notification]:
    """The problems that make the numbers wrong (a negative holding, a currency without rates)."""
    return [Notification(f"health-{check.key}-{check.count}", "danger", "exclamation-triangle", check.title,
                         check.hint, today, url_for("health.index")) for check in data_health.severe(today)]


def _limits(today: date) -> list[Notification]:
    """Deductible room still free late in the year (a pension fund): lost on 31 December."""
    return [Notification(f"limit-{s.limit.id}-{s.year}", "info", "piggy-bank",
                         _("%(name)s: puoi ancora versare %(amount)s", name=s.limit.name, amount=_money(s.left)),
                         _("Entro il 31/12 per dedurli nella dichiarazione del prossimo anno."), today,
                         url_for("tax.limits", year=s.year)) for s in contribution_limits.reminders(today)]


def _gigs(today: date) -> list[Notification]:
    """Odd jobs not paid a month after they were done."""
    return [Notification(f"gig-{g.id}", "warning", "tools", _("Da incassare: %(client)s", client=g.client),
                         _("%(job)s del %(day)s, %(amount)s", job=g.description, day=display.day(g.date),
                           amount=_money(gigs.net(g))), g.date, url_for("gigs.index", year=g.date.year))
            for g in gigs.late(today)]


# each source, and the setting that must be on for it (a module switched off gives no reminders)
# Each kind of reminder and the section it belongs to: none from a section switched off or blocked for the user
SOURCES = ((_policies, "insurance"), (_recurring, "transactions"), (_installments, "debt"), (_budgets, "budget"),
           (_goals, "goals"), (_portfolio, "portfolio"),
           (_data_health, "health"), (_limits, "tax"), (_gigs, "gigs"))


def dismissed() -> list[str]:
    return settings_store.get_json(DISMISSED_SETTING, [], expect=list)


def collect(today: date | None = None, include_dismissed: bool = False) -> list[Notification]:
    """Every current reminder, most urgent first (cached for the request when not including dismissed)."""
    today = today or date.today()
    store, cache_key = request_cache.cache(), f"notifications-{today}"
    if not include_dismissed and cache_key in store:
        return store[cache_key]
    items = [item for source, section in SOURCES if not sections.switched_off(section) and not sections.blocked(section)
             for item in source(today)]
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
    settings_store.set_json(DISMISSED_SETTING, current[-KEEP_DISMISSED:])
