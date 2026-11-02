"""
Rules on the investments (F19e): watches that become reminders when they trip (services.notifications, and the
desktop alerts built on them).

- drift: a part of the active model portfolio is further from its target than the rule's points (or the model's band)
- drawdown: a holding has lost more than X % from its average price
- price_above / price_below: a holding's price is above / below a threshold in euro
- concentration: a holding weighs more than X % of the investments

A reminder's key carries the day of the price it was computed on: dismissed, it comes back only with a new price.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from flask import url_for
from flask_babel import gettext as _

from app.models.portfolio_model import PortfolioRule
from app.models.wealth import Holding
from app.services import display, portfolio_models
from app.services.i18n import N_

KINDS = {
    "drift": N_("Scostamento dal portafoglio modello (punti)"),
    "drawdown": N_("Calo dal prezzo medio (in percentuale)"),
    "price_above": N_("Prezzo sopra (€)"),
    "price_below": N_("Prezzo sotto (€)"),
    "concentration": N_("Peso di un titolo oltre (in percentuale)"),
}
NEEDS_HOLDING = ("price_above", "price_below")


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
    if kind in ("drawdown", "concentration") and threshold > 100:
        raise RuleError(_("La soglia in percentuale va da 0 a 100."))


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


CHECKS = {"drift": _drift, "drawdown": _drawdown, "price_above": _price, "price_below": _price,
          "concentration": _concentration}


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
