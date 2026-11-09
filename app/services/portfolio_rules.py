"""
Rules on the investments (F19e): watches that become reminders when they trip (services.notifications, and the
desktop alerts built on them).

- drift: a part of the active model portfolio is further from its target than the rule's points (or the model's band)
- drawdown: a holding has lost more than X % from its average price
- price_above / price_below: a holding's price is above / below a threshold in euro
- concentration: a holding weighs more than X % of the investments

Rebalancing tied to events (F51):
- new_cash: the liquidity of the securities accounts (their settlement accounts) is above X euro — time to invest it
  following the model (buying only what is under target)
- pac_soon: an instalment of a PAC (investment plan) is due within X days — the split that reduces the drift
- calendar: every X months (1, 3, 6, 12), on the first day of the period, a reminder to check the rebalancing
- market_move: a holding moved more than X % (up or down) in the last 7 days

A reminder's key carries the day of the price it was computed on: dismissed, it comes back only with a new price.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from flask import url_for
from flask_babel import gettext as _

from app.models.portfolio_model import InvestmentPlan, PortfolioRule
from app.models.wealth import Holding, HoldingPrice
from app.services import display, investment_plans, portfolio_models, securities
from app.services.i18n import N_

KINDS = {
    "drift": N_("Scostamento dal portafoglio modello (punti)"),
    "drawdown": N_("Calo dal prezzo medio (in percentuale)"),
    "price_above": N_("Prezzo sopra (€)"),
    "price_below": N_("Prezzo sotto (€)"),
    "concentration": N_("Peso di un titolo oltre (in percentuale)"),
    "new_cash": N_("Liquidità da investire sui conti titoli oltre (€)"),
    "pac_soon": N_("Rata del PAC entro (giorni)"),
    "calendar": N_("Controllo del ribilanciamento ogni (mesi)"),
    "market_move": N_("Movimento di mercato in 7 giorni oltre (in percentuale)"),
}
NEEDS_HOLDING = ("price_above", "price_below")
MOVE_DAYS = 7


class RuleError(ValueError):
    """The rule cannot be saved as it is; the message is shown to the user."""


@dataclass
class Alert:
    key: str
    level: str      # "danger" | "warning" | "info"
    title: str
    detail: str
    when: date
    url: str


def validate(kind: str, holding_id: int | None, threshold: Decimal | None) -> None:
    if kind not in KINDS:
        raise RuleError(_("Tipo di regola sconosciuto."))
    if kind in NEEDS_HOLDING and holding_id is None:
        raise RuleError(_("Una soglia di prezzo vale per un titolo: sceglilo."))
    if kind != "drift" and (threshold is None or threshold <= 0):
        raise RuleError(_("Indica una soglia maggiore di zero."))
    if kind in ("drawdown", "concentration", "market_move") and threshold > 100:
        raise RuleError(_("La soglia in percentuale va da 0 a 100."))
    if kind == "calendar" and threshold not in (1, 3, 6, 12):
        raise RuleError(_("Il controllo periodico va ogni 1, 3, 6 o 12 mesi."))
    if kind == "pac_soon" and threshold > 31:
        raise RuleError(_("Per la rata del PAC indica da 1 a 31 giorni."))


def _day(holding: Holding, today: date) -> str:
    return (holding.price_date or today).isoformat()


def _drift(rule: PortfolioRule, holdings: list[Holding], total: Decimal, today: date) -> list[Alert]:
    template = portfolio_models.active()
    if template is None:
        return []
    band = Decimal(rule.threshold) if rule.threshold else Decimal(template.band)
    lines, _total = portfolio_models.standing(template, holdings)
    return [Alert(f"rule-{rule.id}-{position}-{today:%Y-%m}", "warning",
                  _("«%(part)s» è fuori dal modello di %(points)s punti", part=line.label,
                    points=display.number(line.drift, 1)),
                  _("Pesa %(weight)s %% contro un obiettivo del %(target)s %%", weight=display.number(line.weight, 1),
                    target=display.number(line.target, 1)),
                  today, url_for("portfolio.rebalance"))
            for position, line in enumerate(lines) if abs(line.drift) > band]


def _drawdown(rule: PortfolioRule, holdings: list[Holding], total: Decimal, today: date) -> list[Alert]:
    return [Alert(f"rule-{rule.id}-{h.id}-{_day(h, today)}", "warning",
                  _("%(name)s ha perso il %(pct)s %% dal prezzo medio", name=h.name, pct=display.number(-h.gain_pct, 1)),
                  _("Prezzo %(price)s, prezzo medio %(avg)s", price=display.money(h.price), avg=display.money(h.avg_price)),
                  h.price_date or today, url_for("portfolio.detail", holding_id=h.id))
            for h in holdings if h.cost and h.gain_pct <= -float(rule.threshold)]


def _price(rule: PortfolioRule, holdings: list[Holding], total: Decimal, today: date) -> list[Alert]:
    above = rule.kind == "price_above"
    limit = float(rule.threshold)
    return [Alert(f"rule-{rule.id}-{h.id}-{_day(h, today)}", "info",
                  (_("%(name)s è salito sopra %(limit)s", name=h.name, limit=display.money(limit)) if above
                   else _("%(name)s è sceso sotto %(limit)s", name=h.name, limit=display.money(limit))),
                  _("Ultimo prezzo %(price)s", price=display.money(h.price)),
                  h.price_date or today, url_for("portfolio.detail", holding_id=h.id))
            for h in holdings if (h.price >= limit if above else h.price <= limit)]


def _concentration(rule: PortfolioRule, holdings: list[Holding], total: Decimal, today: date) -> list[Alert]:
    if not total:
        return []
    alerts = []
    for h in holdings:
        weight = Decimal(str(h.value)) / total * 100
        if weight > Decimal(rule.threshold):
            alerts.append(Alert(f"rule-{rule.id}-{h.id}-{_day(h, today)}", "warning",
                                _("%(name)s pesa il %(pct)s %% degli investimenti", name=h.name, pct=display.number(weight, 1)),
                                _("Oltre il limite del %(limit)s %%", limit=display.number(rule.threshold, 1)),
                                h.price_date or today, url_for("portfolio.detail", holding_id=h.id)))
    return alerts


def _new_cash(rule: PortfolioRule, holdings: list[Holding], total: Decimal, today: date) -> list[Alert]:
    alerts = []
    for dossier in securities.accounts():
        cash = securities.cash(dossier)
        if cash > float(rule.threshold):
            alerts.append(Alert(f"rule-{rule.id}-{dossier.id}-{today:%Y-%m}-{int(cash)}", "info",
                                _("%(amount)s da investire su «%(name)s»", amount=display.money(cash), name=dossier.name),
                                _("Ribilancia con i nuovi versamenti: compri solo ciò che è sotto l'obiettivo."),
                                today, url_for("portfolio.rebalance", mode="new", amount=f"{cash:.2f}")))
    return alerts


def _pac_soon(rule: PortfolioRule, holdings: list[Holding], total: Decimal, today: date) -> list[Alert]:
    alerts = []
    for plan in InvestmentPlan.query.order_by(InvestmentPlan.name):
        for month_ahead in (0, 1):  # this month's instalment, or next month's when close to the end of the month
            month = (today.replace(day=1) + timedelta(days=32 * month_ahead)).replace(day=1)
            on = investment_plans.due_date(plan, month)
            if on is None or on < today or (on - today).days > int(rule.threshold) or on < plan.start \
                    or (plan.end and on > plan.end) or (plan.last_done or "") >= investment_plans.period(on):
                continue
            alerts.append(Alert(f"rule-{rule.id}-{plan.id}-{on:%Y-%m}", "info",
                                _("Rata del PAC «%(name)s» il %(day)s", name=plan.name, day=display.day(on)),
                                _("%(amount)s divisi per ridurre lo scostamento dal modello.",
                                  amount=display.money(plan.amount)),
                                today, url_for("portfolio.plan_run", plan_id=plan.id)))
            break
    return alerts


def _calendar(rule: PortfolioRule, holdings: list[Holding], total: Decimal, today: date) -> list[Alert]:
    months = int(rule.threshold)
    if (today.month - 1) % months:
        return []
    return [Alert(f"rule-{rule.id}-{today:%Y-%m}", "info", _("È il momento di controllare il ribilanciamento"),
                  _("Controllo periodico ogni %(months)s mesi.", months=months), today.replace(day=1),
                  url_for("portfolio.rebalance"))]


def _market_move(rule: PortfolioRule, holdings: list[Holding], total: Decimal, today: date) -> list[Alert]:
    alerts = []
    since = today - timedelta(days=MOVE_DAYS)
    for h in holdings:
        before = (HoldingPrice.query.filter(HoldingPrice.holding_id == h.id, HoldingPrice.on <= since)
                  .order_by(HoldingPrice.on.desc()).first())
        if before is None or not before.price or h.price_date is None or h.price_date <= before.on:
            continue
        change = (h.price / float(before.price) - 1) * 100
        if abs(change) > float(rule.threshold):
            alerts.append(Alert(f"rule-{rule.id}-{h.id}-{_day(h, today)}", "warning",
                                _("%(name)s si è mosso del %(pct)s %% in %(days)s giorni", name=h.name,
                                  pct=("+" if change > 0 else "") + display.number(change, 1), days=MOVE_DAYS),
                                _("Il portafoglio può essere uscito dalle bande: controlla il ribilanciamento."),
                                h.price_date, url_for("portfolio.rebalance")))
    return alerts


CHECKS = {"drift": _drift, "drawdown": _drawdown, "price_above": _price, "price_below": _price,
          "concentration": _concentration, "new_cash": _new_cash, "pac_soon": _pac_soon, "calendar": _calendar,
          "market_move": _market_move}


def evaluate(today: date | None = None) -> list[Alert]:
    """The alerts of the active rules now."""
    today = today or date.today()
    rules = PortfolioRule.query.filter_by(active=True).order_by(PortfolioRule.id).all()
    if not rules:
        return []
    investments = portfolio_models.investments()
    total = sum((Decimal(str(h.value)) for h in investments), Decimal(0))
    alerts = []
    for rule in rules:
        holdings = [h for h in investments if rule.holding_id is None or h.id == rule.holding_id]
        alerts += CHECKS[rule.kind](rule, investments if rule.kind == "drift" else holdings, total, today)
    return alerts
