from collections import defaultdict
from datetime import date

from flask import flash, redirect, render_template, request, url_for
from apiflask import APIBlueprint

from app.extensions import db
from app.models.wealth import Debt
from app.routes.helpers import form_choice, form_date, form_decimal, form_int, form_text
from app.services import wealth
from flask_babel import gettext as _

debt_bp = APIBlueprint(
    "debt",
    __name__,
    url_prefix="/debt",
    tag="Debt"
)


def _debt_from_form(debt: Debt) -> Debt:
    debt.name = form_text("name", _("Istituto / descrizione"), required=True)
    debt.type = form_choice("type", _("Tipo"), wealth.DEBT_TYPES)
    debt.principal = form_decimal("principal", _("Capitale iniziale"), required=True)
    rate = form_decimal("annual_rate", _("Tasso annuo"))
    if rate is not None and rate > 100:
        raise ValueError(_("Tasso annuo: al massimo 100%."))
    debt.annual_rate = rate or 0
    debt.term_months = form_int("term_months", _("Durata (mesi)"), minimum=1, maximum=wealth.MAX_PLAN_MONTHS)
    debt.start_date = form_date("start_date", _("Data di inizio"))
    debt.monthly_payment = form_decimal("monthly_payment", _("Rata mensile"))
    debt.balance = form_decimal("balance", _("Saldo residuo"))
    debt.notes = form_text("notes", _("Note"))
    if not debt.principal:
        raise ValueError(_("Capitale iniziale: deve essere maggiore di zero."))
    return debt


def _render_form(debt, values):
    return render_template("debt/form.html", debt=debt, debt_types=wealth.DEBT_TYPES, values=values)


@debt_bp.route("/")
def index():
    today = date.today()
    debts = Debt.query.order_by(Debt.name).all()
    summaries = [wealth.debt_summary(d, today) for d in debts]
    by_type = defaultdict(float)
    for s in summaries:
        by_type[s["debt"].type] += s["balance"]
    monthly_total = sum(s["installment"] or 0 for s in summaries if s["balance"] > 0)
    income = wealth.monthly_average_income(today)
    return render_template(
        "debt/index.html",
        summaries=summaries,
        total_balance=sum(s["balance"] for s in summaries),
        monthly_total=monthly_total,
        interest_ytd=sum(s["interest_ytd"] for s in summaries),
        debt_to_income=round(monthly_total / income * 100, 1) if income else None,
        average_income=income,
        projection=wealth.debts_projection([s["debt"] for s in summaries if s["balance"] > 0], today),
        by_type=sorted(((t, round(v, 2)) for t, v in by_type.items() if v > 0), key=lambda i: i[1], reverse=True),
    )


@debt_bp.route("/<int:debt_id>")
def detail(debt_id):
    debt = db.get_or_404(Debt, debt_id)
    return render_template(
        "debt/detail.html",
        summary=wealth.debt_summary(debt),
        plan=wealth.schedule(debt),
        today=date.today(),
    )


@debt_bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        try:
            debt = _debt_from_form(Debt())
        except ValueError as exc:
            flash(str(exc), "error")
            return _render_form(None, request.form)
        db.session.add(debt)
        db.session.commit()
        flash(_("Debito «%(name)s» aggiunto.", name=debt.name), "success")
        return redirect(url_for("debt.detail", debt_id=debt.id))
    return _render_form(None, {})


@debt_bp.route("/<int:debt_id>/edit", methods=["GET", "POST"])
def edit(debt_id):
    debt = db.get_or_404(Debt, debt_id)
    if request.method == "POST":
        try:
            _debt_from_form(debt)
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
            return _render_form(debt, request.form)
        db.session.commit()
        flash(_("Debito «%(name)s» aggiornato.", name=debt.name), "success")
        return redirect(url_for("debt.detail", debt_id=debt.id))
    return _render_form(debt, {})


@debt_bp.route("/<int:debt_id>/delete", methods=["POST"])
def delete(debt_id):
    debt = db.get_or_404(Debt, debt_id)
    db.session.delete(debt)
    db.session.commit()
    flash(_("Debito «%(name)s» eliminato.", name=debt.name), "success")
    return redirect(url_for("debt.index"))
