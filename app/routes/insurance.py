from collections import defaultdict
from datetime import date, timedelta

from apiflask import APIBlueprint
from flask import render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.wealth import InsurancePolicy
from app.routes.helpers import delete_and_redirect, form_choice, form_date, form_decimal, form_text, save_form
from app.services.i18n import N_, _l

insurance_bp = APIBlueprint(
    "insurance",
    __name__,
    url_prefix="/insurance",
    tag="Insurance"
)

POLICY_TYPES = [N_("Vita"), N_("Salute"), N_("Auto"), N_("Casa"), N_("Infortuni"), N_("RC Professionale"), N_("Viaggi"), N_("Altro")]
FREQUENCIES = [("monthly", _l("Mensile")), ("quarterly", _l("Trimestrale")), ("biannual", _l("Semestrale")), ("annual", _l("Annuale"))]
REMINDER_DAYS = 60  # expiries within this many days are highlighted


def _policy_from_form(policy: InsurancePolicy) -> InsurancePolicy:
    policy.type = form_choice("type", _("Tipo"), POLICY_TYPES)
    policy.company = form_text("company", _("Compagnia"), required=True)
    policy.policy_number = form_text("policy_number", _("Numero polizza"))
    policy.frequency = form_choice("frequency", _("Frequenza"), dict(FREQUENCIES))
    policy.premium = form_decimal("premium", _("Premio"), required=True)
    policy.coverage_limit = form_decimal("coverage_limit", _("Massimale"))
    policy.start_date = form_date("start_date", _("Data di inizio"))
    policy.expiry_date = form_date("expiry_date", _("Data di scadenza"))
    policy.notes = form_text("notes", _("Note"))
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
        return save_form(InsurancePolicy(), _policy_from_form, _render_form,
                         lambda p: _("Polizza %(type)s di %(company)s aggiunta.", type=p.type, company=p.company),
                         lambda p: url_for("insurance.index"))
    return _render_form(None, {})


@insurance_bp.route("/<int:policy_id>/edit", methods=["GET", "POST"])
def edit(policy_id):
    policy = db.get_or_404(InsurancePolicy, policy_id)
    if request.method == "POST":
        return save_form(policy, _policy_from_form, _render_form,
                         lambda p: _("Polizza %(type)s di %(company)s aggiornata.", type=p.type, company=p.company),
                         lambda p: url_for("insurance.index"))
    return _render_form(policy, {})


@insurance_bp.route("/<int:policy_id>/delete", methods=["POST"])
def delete(policy_id):
    policy = db.get_or_404(InsurancePolicy, policy_id)
    return delete_and_redirect(policy, _("Polizza %(type)s di %(company)s eliminata.", type=policy.type, company=policy.company),
                               url_for("insurance.index"))
