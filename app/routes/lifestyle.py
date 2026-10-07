from datetime import date
from decimal import Decimal

from flask import flash, redirect, render_template, request, url_for
from apiflask import APIBlueprint

from app.extensions import db
from app.models.budget import Budget
from app.models.wealth import Goal
from app.routes.helpers import delete_and_redirect, form_date, form_decimal, form_text, save_form
from app.services import analytics, budgets, categories, display
from app.services.periods import add_months
from flask_babel import gettext as _

lifestyle_bp = APIBlueprint(
    "lifestyle",
    __name__,
    url_prefix="/lifestyle",
    tag="Lifestyle"
)


@lifestyle_bp.route("/")
def index():
    years = analytics.available_years()
    year = request.args.get("year", type=int) or date.today().year
    report = analytics.lifestyle_report(year)
    return render_template("lifestyle/index.html", report=report, years=years, year=year)


# ── Monthly budgets ────────────────────────────────────────────────────────────

def _month_arg() -> date:
    raw = request.values.get("month", "")
    try:
        year, month = (int(part) for part in raw.split("-"))
        return date(year, month, 1)
    except ValueError:
        return date.today().replace(day=1)


@lifestyle_bp.route("/budget")
def budget():
    month = _month_arg()
    lines = {line["category"]: line for line in budgets.status(month)}
    spent = budgets.spent_by_category(month)
    names = sorted(set(categories.expense_categories()) | set(lines) | set(spent), key=str.casefold)
    every_month = {b.category: b.amount for b in Budget.query.filter(Budget.month.is_(None))}
    this_month = {b.category: b.amount for b in Budget.query.filter(Budget.month == month)}
    rows = [{"category": n, "line": lines.get(n), "spent": spent.get(n, 0.0),
             "every_month": every_month.get(n), "this_month": this_month.get(n)} for n in names]
    rollover = {b.category for b in Budget.query.filter(Budget.month.is_(None), Budget.rollover_since.isnot(None))}
    for row in rows:
        row["rollover"] = row["category"] in rollover
    planned = sum(line["available"] for line in lines.values())
    return render_template(
        "lifestyle/budget.html", month=month, rows=rows, planned=planned,
        carried=sum(line["carried"] for line in lines.values()), set_asides=budgets.set_asides(),
        spent_total=sum(line["spent"] for line in lines.values()),
        unbudgeted=sum(v for k, v in spent.items() if k not in lines),
        prev=add_months(month, -1), next=add_months(month, 1), warning=budgets.WARNING_SHARE,
    )


@lifestyle_bp.route("/budget", methods=["POST"])
def budget_save():
    month = _month_arg()
    try:
        for name in request.form.getlist("category"):
            budgets.save(name, form_decimal(f"every-{name}", _("Budget mensile di %(name)s", name=name)), None,
                         rollover=f"rollover-{name}" in request.form, since=month)
            budgets.save(name, form_decimal(f"month-{name}", _("Budget di questo mese per %(name)s", name=name)), month)
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return redirect(url_for("lifestyle.budget", month=f"{month:%Y-%m}"))
    db.session.commit()
    flash(_("Budget salvati."), "success")
    return redirect(url_for("lifestyle.budget", month=f"{month:%Y-%m}"))


@lifestyle_bp.route("/budget/set-aside", methods=["POST"])
def budget_set_aside():
    """Budget the monthly quota of a not-monthly category, carried over month after month until it is spent."""
    month = _month_arg()
    category = request.form.get("category") or ""
    quota = next((item["monthly"] for item in budgets.set_asides() if item["category"] == category), None)
    if quota is None:
        flash(_("«%(name)s» non è una categoria di spese non mensili con spese nell'ultimo anno.", name=category), "error")
    else:
        budgets.set_aside(category, Decimal(str(quota)), month)
        db.session.commit()
        flash(_("«%(name)s»: %(amount)s al mese accantonati, con riporto.", name=category, amount=display.money(quota)), "success")
    return redirect(url_for("lifestyle.budget", month=f"{month:%Y-%m}"))


# ── Savings goals ──────────────────────────────────────────────────────────────

def _suggestions() -> list[dict]:
    """Common goals; the emergency fund is sized on six months of the user's own average spending."""
    trailing = analytics.last_12_months()
    avg_expenses = sum(trailing["expenses"]) / 12
    emergency = round(avg_expenses * 6, -2) if avg_expenses else 10000
    return [
        {"name": _("Fondo d'emergenza"), "icon": "bi-shield-check", "target": emergency,
         "hint": _("6 mesi delle tue spese medie") if avg_expenses else _("3–6 mesi di spese")},
        {"name": _("Pensione integrativa"), "icon": "bi-person-check", "target": 50000, "hint": _("Contribuzione mensile")},
        {"name": _("Acquisto casa"), "icon": "bi-house-heart", "target": 40000, "hint": _("Anticipo e spese notarili")},
        {"name": _("Vacanza"), "icon": "bi-airplane", "target": 3000, "hint": _("Risparmio per viaggi")},
        {"name": _("Istruzione"), "icon": "bi-mortarboard", "target": 5000, "hint": _("Corsi e formazione")},
        {"name": _("Veicolo"), "icon": "bi-car-front", "target": 15000, "hint": _("Auto o moto")},
    ]


def _goal_from_form(goal: Goal) -> Goal:
    goal.name = form_text("name", _("Nome"), required=True)
    goal.target_amount = form_decimal("target_amount", _("Importo obiettivo"), required=True)
    goal.saved_amount = form_decimal("saved_amount", _("Già risparmiato")) or 0
    goal.target_date = form_date("target_date", _("Data obiettivo"))
    goal.notes = form_text("notes", _("Note"))
    if not goal.target_amount:
        raise ValueError(_("Importo obiettivo: deve essere maggiore di zero."))
    return goal


def _render_goal_form(goal, values):
    return render_template("lifestyle/goal_form.html", goal=goal, values=values)


@lifestyle_bp.route("/goals")
def goals():
    all_goals = Goal.query.order_by(Goal.target_date.is_(None), Goal.target_date, Goal.name).all()
    active = [g for g in all_goals if not g.completed]
    return render_template(
        "lifestyle/goals.html",
        goals=all_goals,
        active_count=len(active),
        completed_count=len(all_goals) - len(active),
        saved_total=sum(float(g.saved_amount) for g in all_goals),
        target_total=sum(float(g.target_amount) for g in all_goals),
        monthly_total=sum(g.monthly_needed() or 0 for g in active),
        suggestions=_suggestions(),
        today=date.today(),
    )


@lifestyle_bp.route("/goals/new", methods=["GET", "POST"])
def goal_new():
    if request.method == "POST":
        return save_form(Goal(), _goal_from_form, _render_goal_form,
                         lambda g: _("Obiettivo «%(name)s» creato.", name=g.name), lambda g: url_for("lifestyle.goals"))
    # a suggestion pre-fills name and amount
    prefill = {k: request.args[k] for k in ("name", "target_amount") if request.args.get(k)}
    return _render_goal_form(None, prefill)


@lifestyle_bp.route("/goals/<int:goal_id>/edit", methods=["GET", "POST"])
def goal_edit(goal_id):
    goal = db.get_or_404(Goal, goal_id)
    if request.method == "POST":
        return save_form(goal, _goal_from_form, _render_goal_form,
                         lambda g: _("Obiettivo «%(name)s» aggiornato.", name=g.name), lambda g: url_for("lifestyle.goals"))
    return _render_goal_form(goal, {})


@lifestyle_bp.route("/goals/<int:goal_id>/contribute", methods=["POST"])
def goal_contribute(goal_id):
    """Add (or, with a negative amount, withdraw) money set aside for the goal."""
    goal = db.get_or_404(Goal, goal_id)
    try:
        amount = form_decimal("amount", _("Importo"), required=True, allow_negative=True)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("lifestyle.goals"))
    was_completed = goal.completed
    goal.saved_amount = max(Decimal(goal.saved_amount or 0) + amount, Decimal(0))
    db.session.commit()
    if goal.completed and not was_completed:
        flash(_("🎉 Obiettivo «%(name)s» raggiunto!", name=goal.name), "success")
    else:
        shown = display.money(abs(amount))
        flash(_("«%(name)s»: aggiunti %(amount)s.", name=goal.name, amount=shown) if amount >= 0
              else _("«%(name)s»: tolti %(amount)s.", name=goal.name, amount=shown), "success")
    return redirect(url_for("lifestyle.goals"))


@lifestyle_bp.route("/goals/<int:goal_id>/delete", methods=["POST"])
def goal_delete(goal_id):
    goal = db.get_or_404(Goal, goal_id)
    return delete_and_redirect(goal, _("Obiettivo «%(name)s» eliminato.", name=goal.name), url_for("lifestyle.goals"))
