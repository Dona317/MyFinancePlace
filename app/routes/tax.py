"""Fisco (F15): the 730's deductible expenses, capital gains and losses of the trades, stamp duty and IVAFE."""
import csv
import io
from datetime import date

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from sqlalchemy import func

from app.extensions import db
from app.models.transaction import Transaction
from app.services import capital_gains, categories, display, stamp_duty, tax_730, tax_rules

tax_bp = Blueprint("tax", __name__, url_prefix="/tax")


def _years() -> list[int]:
    first = db.session.query(func.min(Transaction.date)).scalar()
    this_year = date.today().year
    return list(range(this_year, min(first.year if first else this_year, this_year) - 1, -1))


def _year(default: int) -> int:
    value = request.args.get("year", "")
    return int(value) if value.isdigit() and 1900 < int(value) < 3000 else default


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
    year = _year(date.today().year - 1)  # the 730 filed this year is about last year
    return _page("tax/deductions.html", "730", year, data=tax_730.summary(year), mapping=tax_730.mapping(),
                 people=tax_730.people(), category_names=_spending_categories(),
                 items=tax_rules.items(year))


@tax_bp.route("/730/categories", methods=["POST"])
def save_categories():
    year = _year(date.today().year - 1)
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
    year = _year(date.today().year - 1)
    data = tax_730.summary(year)
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([_("Rigo"), _("Voce"), _("Data"), _("Descrizione"), _("Categoria"), _("Importo"), _("Conto")])
    for line in data["lines"]:
        for tx, amount in line.entries:
            writer.writerow([line.item.form_line, _(line.item.label), tx.date.isoformat(), tx.description,
                             tx.category or "", display.number(amount), tx.account.name if tx.account else ""])
    return Response("﻿" + buffer.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="730_{year}.csv"'})


@tax_bp.route("/investments")
def investments():
    year = _year(date.today().year)
    return _page("tax/investments.html", "investments", year, data=capital_gains.year_summary(year))


@tax_bp.route("/duties")
def duties():
    year = _year(date.today().year)
    return _page("tax/duties.html", "duties", year, data=stamp_duty.year_summary(year))
