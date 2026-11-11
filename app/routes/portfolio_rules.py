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
from app.models.securities import Portfolio, SecuritiesAccount
from app.models.wealth import Holding
from app.routes.helpers import uploaded_file, year_arg
from app.routes.portfolio import portfolio_bp
from app.services import (
    accounts,
    bonds,
    composition,
    display,
    family,
    income_report,
    investment_plans,
    lookthrough,
    performance,
    periods,
    portfolio_highlights,
    portfolio_models,
    portfolio_ops,
    portfolio_rules,
    price_feed,
    securities,
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
                           folios=securities.portfolios(), dossiers=securities.accounts(),
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
    folio_id, dossier_id = form.get("portfolio_id", type=int), form.get("securities_account_id", type=int)
    plan.portfolio_id = folio_id if folio_id and db.session.get(Portfolio, folio_id) else None
    plan.securities_account_id = dossier_id if dossier_id and db.session.get(SecuritiesAccount, dossier_id) else None
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
                           place=investment_plans.place_of(plan), model=investment_plans.template_of(plan),
                           is_due=investment_plans.is_due(plan, date.today()))


# ── Passive income (F20) ───────────────────────────────────────────────────────

@portfolio_bp.route("/income")
def income():
    today = date.today()
    report = income_report.report(year_arg(today.year), today)
    return render_template("portfolio/income.html", report=report, kinds=income_report.KINDS,
                           month_labels=periods.month_labels(), coupons=bonds.upcoming(Holding.query.all(), today))


# ── Performance (F20) ──────────────────────────────────────────────────────────

@portfolio_bp.route("/performance", methods=["GET", "POST"])
def performance_page():
    if request.method == "POST":
        _performance_post()
        return redirect(url_for("portfolio.performance_page", person=request.args.get("person", ""),
                                period=request.args.get("period", "")))
    person = request.args.get("person", "")
    period = request.args.get("period", "all")
    holdings = family.holdings_of(person, portfolio_models.investments())
    return render_template("portfolio/performance.html", report=performance.report(holdings), person=person,
                           month_names=[str(_(m)) for m in periods.MONTH_LABELS],
                           xirr=portfolio_ops.performance(holdings)["xirr"] if holdings else None,
                           benchmarks=performance.benchmarks(), max_benchmarks=performance.MAX_BENCHMARKS,
                           contribution=performance.contributions(holdings, period),
                           period_choices=performance.PERIODS)


def _performance_post() -> None:
    """The benchmarks (add or refresh one, remove one) and the risk-free rate (F58, F59)."""
    if "risk_free" in request.form:
        rate = to_decimal(request.form.get("risk_free"))
        try:
            if rate is None:
                raise ValueError(rate)
            performance.save_risk_free(float(rate))
            flash(_("Tasso senza rischio salvato."), "success")
        except ValueError:
            flash(_("Indica un tasso tra -10 e 50 %."), "error")
        return
    removed = (request.form.get("remove") or "").strip().upper()
    if removed:
        performance.remove_benchmark(removed)
        flash(_("Benchmark tolto."), "success")
        return
    ticker = (request.form.get("ticker") or "").strip().upper()
    if not ticker:
        performance.save_benchmark("", {}, date.today())
        flash(_("Benchmark tolti."), "success")
    elif not performance.can_add_benchmark(ticker):
        flash(_("Al massimo %(count)s benchmark: togline uno prima di aggiungerne un altro.",
                count=performance.MAX_BENCHMARKS), "error")
    else:
        try:
            performance.save_benchmark(ticker, price_feed.benchmark_history(ticker), date.today())
            db.session.commit()
            flash(_("Storico di %(ticker)s scaricato.", ticker=ticker), "success")
        except (ValueError, OSError) as exc:
            flash(_("Benchmark non aggiornato: %(error)s", error=exc), "error")


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
    return render_template("portfolio/composition.html", look=lookthrough.portfolio(holdings), person=person,
                           unset=composition.UNSET,
                           own=[(t, taxonomies.exposure(t, holdings)) for t in taxonomies.all_taxonomies()])


# ── Look-through of the funds (F57) ───────────────────────────────────────────

def _back_to_lookthrough(holding):
    return redirect(url_for("portfolio.detail", holding_id=holding.id) + "#lookthrough")


@portfolio_bp.route("/<int:holding_id>/lookthrough/upload", methods=["POST"])
def lookthrough_upload(holding_id):
    """The holdings file downloaded from the issuer's site: countries, sectors, currencies, top companies."""
    holding = db.get_or_404(Holding, holding_id)
    upload = uploaded_file()
    if upload is None:
        flash(_("Scegli il file delle partecipazioni scaricato dal sito dell'emittente."), "error")
        return _back_to_lookthrough(holding)
    try:
        parsed = lookthrough.import_file(holding, upload.filename, upload.read(), to_date(request.form.get("as_of")))
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return _back_to_lookthrough(holding)
    db.session.commit()
    flash(_("Composizione letta da %(source)s: %(rows)s righe, dati al %(day)s.", source=parsed.source,
            rows=parsed.rows, day=display.day(parsed.as_of)), "success")
    return _back_to_lookthrough(holding)


@portfolio_bp.route("/<int:holding_id>/lookthrough/manual", methods=["POST"])
def lookthrough_manual(holding_id):
    """The top countries and sectors typed by hand (from the fund's factsheet)."""
    holding = db.get_or_404(Holding, holding_id)
    rows = {kind: list(zip(request.form.getlist(f"{kind}_name"), request.form.getlist(f"{kind}_weight")))
            for kind in ("country", "sector")}
    try:
        lookthrough.manual(holding, rows, to_date(request.form.get("as_of")))
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return _back_to_lookthrough(holding)
    db.session.commit()
    flash(_("Composizione salvata."), "success")
    return _back_to_lookthrough(holding)


@portfolio_bp.route("/<int:holding_id>/lookthrough/clear", methods=["POST"])
def lookthrough_clear(holding_id):
    holding = db.get_or_404(Holding, holding_id)
    lookthrough.clear(holding)
    db.session.commit()
    flash(_("Composizione cancellata: il titolo conta di nuovo con area e settore della sua scheda."), "success")
    return _back_to_lookthrough(holding)
