from datetime import date
from decimal import Decimal

from flask import flash, redirect, render_template, request, url_for
from apiflask import APIBlueprint

from app.extensions import db
from app.models.budget import Budget
from app.models.wealth import Goal
from app.routes.helpers import form_date, form_decimal, form_text
from app.services import analytics, budgets, categories
from app.services.periods import add_months

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
    planned = sum(line["planned"] for line in lines.values())
    return render_template(
        "lifestyle/budget.html", month=month, rows=rows, planned=planned,
        spent_total=sum(line["spent"] for line in lines.values()),
        unbudgeted=sum(v for k, v in spent.items() if k not in lines),
        prev=add_months(month, -1), next=add_months(month, 1), warning=budgets.WARNING_SHARE,
    )


@lifestyle_bp.route("/budget", methods=["POST"])
def budget_save():
    month = _month_arg()
    try:
        for name in request.form.getlist("category"):
            budgets.save(name, form_decimal(f"every-{name}", f"Budget mensile di {name}"), None)
            budgets.save(name, form_decimal(f"month-{name}", f"Budget di questo mese per {name}"), month)
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return redirect(url_for("lifestyle.budget", month=f"{month:%Y-%m}"))
    db.session.commit()
    flash("Budget salvati.", "success")
    return redirect(url_for("lifestyle.budget", month=f"{month:%Y-%m}"))


# ── Savings goals ──────────────────────────────────────────────────────────────

def _suggestions() -> list[dict]:
    """Common goals; the emergency fund is sized on six months of the user's own average spending."""
    trailing = analytics.last_12_months()
    avg_expenses = sum(trailing["expenses"]) / 12
    emergency = round(avg_expenses * 6, -2) if avg_expenses else 10000
    return [
        {"name": "Fondo d'emergenza", "icon": "bi-shield-check", "target": emergency,
         "hint": "6 mesi delle tue spese medie" if avg_expenses else "3–6 mesi di spese"},
        {"name": "Pensione integrativa", "icon": "bi-person-check", "target": 50000, "hint": "Contribuzione mensile"},
        {"name": "Acquisto casa", "icon": "bi-house-heart", "target": 40000, "hint": "Anticipo e spese notarili"},
        {"name": "Vacanza", "icon": "bi-airplane", "target": 3000, "hint": "Risparmio per viaggi"},
        {"name": "Istruzione", "icon": "bi-mortarboard", "target": 5000, "hint": "Corsi e formazione"},
        {"name": "Veicolo", "icon": "bi-car-front", "target": 15000, "hint": "Auto o moto"},
    ]


def _goal_from_form(goal: Goal) -> Goal:
    goal.name = form_text("name", "Nome", required=True)
    goal.target_amount = form_decimal("target_amount", "Importo obiettivo", required=True)
    goal.saved_amount = form_decimal("saved_amount", "Già risparmiato") or 0
    goal.target_date = form_date("target_date", "Data obiettivo")
    goal.notes = form_text("notes", "Note")
    if not goal.target_amount:
        raise ValueError("Importo obiettivo: deve essere maggiore di zero.")
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
        try:
            goal = _goal_from_form(Goal())
        except ValueError as exc:
            flash(str(exc), "error")
            return _render_goal_form(None, request.form)
        db.session.add(goal)
        db.session.commit()
        flash(f"Obiettivo «{goal.name}» creato.", "success")
        return redirect(url_for("lifestyle.goals"))
    # a suggestion pre-fills name and amount
    prefill = {k: request.args[k] for k in ("name", "target_amount") if request.args.get(k)}
    return _render_goal_form(None, prefill)


@lifestyle_bp.route("/goals/<int:goal_id>/edit", methods=["GET", "POST"])
def goal_edit(goal_id):
    goal = db.get_or_404(Goal, goal_id)
    if request.method == "POST":
        try:
            _goal_from_form(goal)
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
            return _render_goal_form(goal, request.form)
        db.session.commit()
        flash(f"Obiettivo «{goal.name}» aggiornato.", "success")
        return redirect(url_for("lifestyle.goals"))
    return _render_goal_form(goal, {})


@lifestyle_bp.route("/goals/<int:goal_id>/contribute", methods=["POST"])
def goal_contribute(goal_id):
    """Add (or, with a negative amount, withdraw) money set aside for the goal."""
    goal = db.get_or_404(Goal, goal_id)
    try:
        amount = form_decimal("amount", "Importo", required=True, allow_negative=True)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("lifestyle.goals"))
    was_completed = goal.completed
    goal.saved_amount = max(Decimal(goal.saved_amount or 0) + amount, Decimal(0))
    db.session.commit()
    if goal.completed and not was_completed:
        flash(f"🎉 Obiettivo «{goal.name}» raggiunto!", "success")
    else:
        shown = f"{abs(amount):.2f}".replace(".", ",")
        flash(f"«{goal.name}»: {'aggiunti' if amount >= 0 else 'tolti'} € {shown}.", "success")
    return redirect(url_for("lifestyle.goals"))


@lifestyle_bp.route("/goals/<int:goal_id>/delete", methods=["POST"])
def goal_delete(goal_id):
    goal = db.get_or_404(Goal, goal_id)
    db.session.delete(goal)
    db.session.commit()
    flash(f"Obiettivo «{goal.name}» eliminato.", "success")
    return redirect(url_for("lifestyle.goals"))
