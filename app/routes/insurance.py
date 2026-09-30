from collections import defaultdict
from datetime import date, timedelta

from flask import flash, redirect, render_template, request, url_for
from apiflask import APIBlueprint

from app.extensions import db
from app.models.wealth import InsurancePolicy
from app.routes.helpers import form_choice, form_date, form_decimal, form_text
from flask_babel import gettext as _

insurance_bp = APIBlueprint(
    "insurance",
    __name__,
    url_prefix="/insurance",
    tag="Insurance"
)

POLICY_TYPES = ["Vita", "Salute", "Auto", "Casa", "Infortuni", "RC Professionale", "Viaggi", "Altro"]
FREQUENCIES = [("monthly", "Mensile"), ("quarterly", "Trimestrale"), ("biannual", "Semestrale"), ("annual", "Annuale")]
REMINDER_DAYS = 60  # expiries within this many days are highlighted


def _policy_from_form(policy: InsurancePolicy) -> InsurancePolicy:
    policy.type = form_choice("type", "Tipo", POLICY_TYPES)
    policy.company = form_text("company", "Compagnia", required=True)
    policy.policy_number = form_text("policy_number", "Numero polizza")
    policy.frequency = form_choice("frequency", "Frequenza", dict(FREQUENCIES))
    policy.premium = form_decimal("premium", "Premio", required=True)
    policy.coverage_limit = form_decimal("coverage_limit", "Massimale")
    policy.start_date = form_date("start_date", "Data di inizio")
    policy.expiry_date = form_date("expiry_date", "Data di scadenza")
    policy.notes = form_text("notes", "Note")
    if policy.start_date and policy.expiry_date and policy.expiry_date < policy.start_date:
        raise ValueError(_("La scadenza non può essere prima dell'inizio."))
    return policy


def _render_form(policy, values):
    return render_template("insurance/form.html", policy=policy, policy_types=POLICY_TYPES,
                           frequencies=FREQUENCIES, values=values)


@insurance_bp.route("/")
def index():
    today = date.today()
    selected = request.args.get("type", "")
    policies = InsurancePolicy.query.order_by(InsurancePolicy.expiry_date.is_(None), InsurancePolicy.expiry_date,
                                              InsurancePolicy.company).all()
    active = [p for p in policies if p.is_active(today)]
    upcoming = [p for p in active if p.expiry_date and p.expiry_date <= today + timedelta(days=REMINDER_DAYS)]
    by_type = defaultdict(float)
    for p in active:
        by_type[p.type] += p.annual_premium
    return render_template(
        "insurance/index.html",
        policies=[p for p in policies if not selected or p.type == selected],
        active_count=len(active),
        annual_total=sum(p.annual_premium for p in active),
        coverage_total=sum(float(p.coverage_limit or 0) for p in active),
        next_expiry=next((p for p in active if p.expiry_date), None),
        upcoming=upcoming,
        by_type=sorted(by_type.items(), key=lambda item: item[1], reverse=True),
        policy_types=POLICY_TYPES,
        frequency_labels=dict(FREQUENCIES),
        selected=selected,
        today=today,
        reminder_days=REMINDER_DAYS,
    )


@insurance_bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        try:
            policy = _policy_from_form(InsurancePolicy())
        except ValueError as exc:
            flash(str(exc), "error")
            return _render_form(None, request.form)
        db.session.add(policy)
        db.session.commit()
        flash(_("Polizza %(type)s di %(company)s aggiunta.", type=policy.type, company=policy.company), "success")
        return redirect(url_for("insurance.index"))
    return _render_form(None, {})


@insurance_bp.route("/<int:policy_id>/edit", methods=["GET", "POST"])
def edit(policy_id):
    policy = db.get_or_404(InsurancePolicy, policy_id)
    if request.method == "POST":
        try:
            _policy_from_form(policy)
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
            return _render_form(policy, request.form)
        db.session.commit()
        flash(_("Polizza %(type)s di %(company)s aggiornata.", type=policy.type, company=policy.company), "success")
        return redirect(url_for("insurance.index"))
    return _render_form(policy, {})


@insurance_bp.route("/<int:policy_id>/delete", methods=["POST"])
def delete(policy_id):
    policy = db.get_or_404(InsurancePolicy, policy_id)
    db.session.delete(policy)
    db.session.commit()
    flash(_("Polizza %(type)s di %(company)s eliminata.", type=policy.type, company=policy.company), "success")
    return redirect(url_for("insurance.index"))
