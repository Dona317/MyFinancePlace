"""
Rules and investment plans (F19e), on the portfolio's blueprint: the watches on the investments, the PACs, and the
page that confirms an instalment's purchases; and the passive income page (F20).
"""
from datetime import date

from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.portfolio_model import InvestmentPlan, PortfolioRule, PortfolioTemplate
from app.models.wealth import Holding
from app.routes.helpers import year_arg
from app.routes.portfolio import portfolio_bp
from app.services import (
    accounts,
    composition,
    display,
    family,
    income_report,
    investment_plans,
    performance,
    periods,
    portfolio_highlights,
    portfolio_models,
    portfolio_ops,
    portfolio_rules,
    price_feed,
    taxonomies,
)
from app.services.parsing import to_date, to_decimal


@portfolio_bp.route("/rules")
def rules():
    return render_template("portfolio/rules.html", rules=PortfolioRule.query.order_by(PortfolioRule.id).all(),
                           plans=InvestmentPlan.query.order_by(InvestmentPlan.name).all(), kinds=portfolio_rules.KINDS,
                           holdings=portfolio_models.investments(), alerts=portfolio_rules.evaluate(),
                           due={plan.id for plan in investment_plans.due()}, frequencies=investment_plans.FREQUENCIES)


@portfolio_bp.route("/rules/new", methods=["POST"])
def rule_new():
    kind = request.form.get("kind", "")
    holding_id = request.form.get("holding_id", type=int)
    threshold = to_decimal(request.form.get("threshold"))
    try:
        portfolio_rules.validate(kind, holding_id, threshold)
    except portfolio_rules.RuleError as exc:
        flash(str(exc), "error")
        return redirect(url_for("portfolio.rules"))
    db.session.add(PortfolioRule(kind=kind, holding_id=holding_id, threshold=threshold))
    db.session.commit()
    flash(_("Regola aggiunta: gli avvisi compaiono tra i promemoria."), "success")
    return redirect(url_for("portfolio.rules"))


@portfolio_bp.route("/rules/<int:rule_id>/toggle", methods=["POST"])
def rule_toggle(rule_id):
    rule = db.get_or_404(PortfolioRule, rule_id)
    rule.active = not rule.active
    db.session.commit()
    return redirect(url_for("portfolio.rules"))


@portfolio_bp.route("/rules/<int:rule_id>/delete", methods=["POST"])
def rule_delete(rule_id):
    db.session.delete(db.get_or_404(PortfolioRule, rule_id))
    db.session.commit()
    flash(_("Regola eliminata."), "success")
    return redirect(url_for("portfolio.rules"))


# ── Investment plans (PAC) ─────────────────────────────────────────────────────

def _plan_page(plan: InvestmentPlan | None, values):
    return render_template("portfolio/plan_form.html", plan=plan, values=values, accounts=accounts.active(),
                           templates=PortfolioTemplate.query.order_by(PortfolioTemplate.name).all(),
                           frequencies=investment_plans.FREQUENCIES, today=date.today())


def _plan_form(plan: InvestmentPlan | None):
    if request.method == "GET":
        return _plan_page(plan, {})
    form = request.form
    name, amount, frequency = form.get("name", ""), to_decimal(form.get("amount")), form.get("frequency", "")
    day, start, end = form.get("day", type=int), to_date(form.get("start")), to_date(form.get("end"))
    try:
        investment_plans.validate(name, amount, frequency, day, start, end)
    except investment_plans.PlanError as exc:
        flash(str(exc), "error")
        return _plan_page(plan, form.to_dict())
    plan = plan or InvestmentPlan()
    account_id, template_id = form.get("account_id", type=int), form.get("template_id", type=int)
    plan.name, plan.amount, plan.frequency, plan.day = name.strip(), amount, frequency, day
    plan.start, plan.end, plan.fractional = start, end, bool(form.get("fractional"))
    plan.account_id = account_id if account_id and db.session.get(Account, account_id) else None
    plan.template_id = template_id if template_id and db.session.get(PortfolioTemplate, template_id) else None
    db.session.add(plan)
    db.session.commit()
    flash(_("Piano d'accumulo salvato."), "success")
    return redirect(url_for("portfolio.rules"))


@portfolio_bp.route("/plans/new", methods=["GET", "POST"])
def plan_new():
    return _plan_form(None)


@portfolio_bp.route("/plans/<int:plan_id>", methods=["GET", "POST"])
def plan_edit(plan_id):
    return _plan_form(db.get_or_404(InvestmentPlan, plan_id))


@portfolio_bp.route("/plans/<int:plan_id>/delete", methods=["POST"])
def plan_delete(plan_id):
    db.session.delete(db.get_or_404(InvestmentPlan, plan_id))
    db.session.commit()
    flash(_("Piano d'accumulo eliminato."), "success")
    return redirect(url_for("portfolio.rules"))


def _orders() -> list[investment_plans.Order]:
    orders = []
    for index in range(request.form.get("rows", 0, type=int)):
        if not request.form.get(f"buy-{index}"):
            continue
        units, price = to_decimal(request.form.get(f"units-{index}")), to_decimal(request.form.get(f"price-{index}"))
        orders.append(investment_plans.Order(request.form.get(f"holding-{index}", type=int),
                                             request.form.get(f"label-{index}", ""), request.form.get(f"isin-{index}") or None,
                                             request.form.get(f"ticker-{index}") or None, units or 0, price or 0))
    return orders


@portfolio_bp.route("/plans/<int:plan_id>/run", methods=["GET", "POST"])
def plan_run(plan_id):
    plan = db.get_or_404(InvestmentPlan, plan_id)
    if request.method == "POST":
        try:
            with db.session.begin_nested():
                bought = investment_plans.confirm(plan, _orders(), to_date(request.form.get("on")) or date.today())
        except (investment_plans.PlanError, ValueError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("portfolio.plan_run", plan_id=plan.id))
        db.session.commit()
        flash(_("%(count)s acquisti del PAC registrati.", count=bought), "success")
        return redirect(url_for("portfolio.index"))
    try:
        purchases = investment_plans.proposal(plan)
    except investment_plans.PlanError as exc:
        flash(str(exc), "error")
        return redirect(url_for("portfolio.models_index"))
    return render_template("portfolio/plan_run.html", plan=plan, purchases=purchases, today=date.today(),
                           is_due=investment_plans.is_due(plan, date.today()))


# ── Passive income (F20) ───────────────────────────────────────────────────────

@portfolio_bp.route("/income")
def income():
    today = date.today()
    report = income_report.report(year_arg(today.year), today)
    return render_template("portfolio/income.html", report=report, kinds=income_report.KINDS,
                           month_labels=periods.month_labels())


# ── Performance (F20) ──────────────────────────────────────────────────────────

@portfolio_bp.route("/performance", methods=["GET", "POST"])
def performance_page():
    if request.method == "POST":
        ticker = (request.form.get("ticker") or "").strip().upper()
        if not ticker:
            performance.save_benchmark("", {}, date.today())
            flash(_("Benchmark tolto."), "success")
        else:
            try:
                performance.save_benchmark(ticker, price_feed.benchmark_history(ticker), date.today())
                db.session.commit()
                flash(_("Storico di %(ticker)s scaricato.", ticker=ticker), "success")
            except (ValueError, OSError) as exc:
                flash(_("Benchmark non aggiornato: %(error)s", error=exc), "error")
        return redirect(url_for("portfolio.performance_page", person=request.args.get("person", "")))
    person = request.args.get("person", "")
    holdings = family.holdings_of(person, portfolio_models.investments())
    return render_template("portfolio/performance.html", report=performance.report(holdings), person=person,
                           xirr=portfolio_ops.performance(holdings)["xirr"] if holdings else None,
                           benchmark=performance.benchmark_settings())


# ── Splits and composition (F20) ───────────────────────────────────────────────

@portfolio_bp.route("/<int:holding_id>/split", methods=["POST"])
def split(holding_id):
    holding = db.get_or_404(Holding, holding_id)
    ratio, on = to_decimal(request.form.get("ratio")), to_date(request.form.get("on")) or date.today()
    try:
        adjusted = composition.split(holding, ratio, on)
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return redirect(url_for("portfolio.detail", holding_id=holding.id))
    db.session.commit()
    flash(_("Frazionamento 1:%(ratio)s applicato dal %(day)s: %(count)s operazioni precedenti adeguate.",
            ratio=display.plain(ratio), day=display.day(on), count=adjusted), "success")
    return redirect(url_for("portfolio.detail", holding_id=holding.id))


@portfolio_bp.route("/highlights")
def highlights_page():
    return render_template("portfolio/highlights.html", data=portfolio_highlights.highlights())


@portfolio_bp.route("/composition")
def composition_page():
    person = request.args.get("person", "")
    holdings = family.holdings_of(person, portfolio_models.investments())
    return render_template("portfolio/composition.html", exposure=composition.exposure(holdings), person=person,
                           unset=composition.UNSET,
                           own=[(t, taxonomies.exposure(t, holdings)) for t in taxonomies.all_taxonomies()])
