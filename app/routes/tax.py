"""Fisco (F15): the 730's deductible expenses, capital gains and losses of the trades, stamp duty and IVAFE."""
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from sqlalchemy import func

from app.extensions import db
from app.models.limit import ContributionLimit
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.routes.helpers import csv_text, download, flash_errors, year_arg
from app.services import accounts, capital_gains, categories, contribution_limits, display, stamp_duty, tax_730, tax_rules
from app.services.parsing import to_decimal

tax_bp = Blueprint("tax", __name__, url_prefix="/tax")


def _years() -> list[int]:
    first = db.session.query(func.min(Transaction.date)).scalar()
    this_year = date.today().year
    return list(range(this_year, min(first.year if first else this_year, this_year) - 1, -1))


def _spending_categories() -> list[str]:
    """Main categories an expense can have: managed ones not for income only, and those already used."""
    income_only = {c.name for c in categories.all_categories() if c.kind == "income"}
    parents = categories.parents()
    return [n for n in categories.known_categories() if n not in income_only and n not in parents]


def _page(template: str, tab: str, year: int, **context):
    return render_template(template, tab=tab, year=year, years=sorted(set(_years()) | {year}, reverse=True), **context)


@tax_bp.route("/")
def index():
    return redirect(url_for("tax.deductions"))


@tax_bp.route("/730")
def deductions():
    year = year_arg(date.today().year - 1)  # the 730 filed this year is about last year
    return _page("tax/deductions.html", "730", year, data=tax_730.summary(year), mapping=tax_730.mapping(),
                 people=tax_730.people(), category_names=_spending_categories(),
                 items=tax_rules.items(year))


@tax_bp.route("/730/categories", methods=["POST"])
def save_categories():
    year = year_arg(date.today().year - 1)
    known = set(categories.known_categories())
    chosen, people = {}, {}
    for item in tax_rules.items(year):
        chosen[item.code] = [name for name in request.form.getlist(f"cat-{item.code}") if name in known]
        count = request.form.get(f"people-{item.code}", "")
        if count.isdigit() and 1 <= int(count) <= 20:
            people[item.code] = int(count)
    tax_730.save_mapping(chosen, people)
    db.session.commit()
    flash(_("Categorie del 730 salvate."), "success")
    return redirect(url_for("tax.deductions", year=year))


@tax_bp.route("/730.csv")
def deductions_csv():
    year = year_arg(date.today().year - 1)
    data = tax_730.summary(year)
    rows = [[_("Rigo"), _("Voce"), _("Data"), _("Descrizione"), _("Categoria"), _("Importo"), _("Conto")]]
    rows += [[line.item.form_line, _(line.item.label), tx.date.isoformat(), tx.description, tx.category or "",
              display.number(amount), tx.account.name if tx.account else ""]
             for line in data["lines"] for tx, amount in line.entries]
    return download(csv_text(rows), f"730_{year}.csv", "text/csv; charset=utf-8")


@tax_bp.route("/investments")
def investments():
    year = year_arg(date.today().year)
    return _page("tax/investments.html", "investments", year, data=capital_gains.year_summary(year))


@tax_bp.route("/duties")
def duties():
    year = year_arg(date.today().year)
    return _page("tax/duties.html", "duties", year, data=stamp_duty.year_summary(year))


# ── Contribution limits (F22) ──────────────────────────────────────────────────

def _limit_form(limit: ContributionLimit | None):
    form = request.form
    kind, name, yearly = form.get("kind", "custom"), form.get("name", ""), to_decimal(form.get("yearly"))
    total = to_decimal(form.get("total")) if (form.get("total") or "").strip() else None
    preset = contribution_limits.BY_KIND.get(kind)
    if preset is not None and yearly is None:  # a ready-made limit: its amounts unless typed
        yearly, total = preset.yearly, total if total is not None else preset.total
    if preset is not None and not name.strip():
        name = _(preset.name)
    return contribution_limits.save(
        limit, name=name, kind=kind, yearly=yearly, total=total, since_year=form.get("since_year", type=int), account_ids=form.getlist("account_ids"),
        holding_ids=form.getlist("holding_ids"), category=form.get("category"), notes=form.get("notes"))


@tax_bp.route("/limits")
def limits():
    year = year_arg(date.today().year)
    return _page("tax/limits.html", "limits", year, standings=contribution_limits.all_standings(year),
                 presets=contribution_limits.PRESETS, accounts=accounts.active(),
                 holdings=Holding.query.order_by(Holding.name).all(), category_names=_spending_categories())


@tax_bp.route("/limits/new", methods=["POST"])
def limit_new():
    with flash_errors(rollback=True):
        limit = _limit_form(None)
        db.session.commit()
        flash(_("Tetto «%(name)s» aggiunto.", name=limit.name), "success")
    return redirect(url_for("tax.limits"))


@tax_bp.route("/limits/<int:limit_id>/edit", methods=["POST"])
def limit_edit(limit_id):
    limit = db.get_or_404(ContributionLimit, limit_id)
    with flash_errors(rollback=True):
        _limit_form(limit)
        db.session.commit()
        flash(_("Tetto «%(name)s» aggiornato.", name=limit.name), "success")
    return redirect(url_for("tax.limits"))


@tax_bp.route("/limits/<int:limit_id>/delete", methods=["POST"])
def limit_delete(limit_id):
    db.session.delete(db.get_or_404(ContributionLimit, limit_id))
    db.session.commit()
    flash(_("Tetto eliminato: i movimenti restano."), "success")
    return redirect(url_for("tax.limits"))
