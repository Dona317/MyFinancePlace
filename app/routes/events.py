"""Spending events (F20): trips, weddings, renovations — their movements, total and budget."""
from datetime import date

from apiflask import APIBlueprint
from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.event import SpendingEvent
from app.routes.helpers import back_to, form_ids
from app.services import spending_events
from app.services.parsing import to_date, to_decimal

events_bp = APIBlueprint("events", __name__, url_prefix="/events", tag="Events")


def _save(event: SpendingEvent) -> bool:
    form = request.form
    name, start, end = form.get("name", ""), to_date(form.get("start")), to_date(form.get("end"))
    budget = to_decimal(form.get("budget"))
    try:
        spending_events.validate(name, start, end, budget)
    except spending_events.EventError as exc:
        flash(str(exc), "error")
        return False
    event.name, event.start, event.end, event.budget = name.strip(), start, end, budget
    event.notes = (form.get("notes") or "").strip() or None
    db.session.add(event)
    db.session.commit()
    return True


@events_bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        event = SpendingEvent()
        if _save(event):
            flash(_("Evento creato: aggiungi i suoi movimenti."), "success")
            return redirect(url_for("events.detail", event_id=event.id))
        return redirect(url_for("events.index"))
    today = date.today()
    start = date(today.year, 1, 1)
    return render_template("events/index.html", summaries=spending_events.all_summaries(), year=today.year,
                           ordinary=spending_events.spent_outside_events(start, today),
                           in_events=spending_events.spent_in_events(start, today))


@events_bp.route("/<int:event_id>", methods=["GET", "POST"])
def detail(event_id):
    event = db.get_or_404(SpendingEvent, event_id)
    if request.method == "POST":
        if _save(event):
            flash(_("Evento salvato."), "success")
        return redirect(url_for("events.detail", event_id=event.id))
    rows = spending_events.movements(event)
    return render_template("events/detail.html", event=event, rows=rows, summary=spending_events.summary(event, rows),
                           suggestions=spending_events.suggestions(event))


@events_bp.route("/<int:event_id>/delete", methods=["POST"])
def delete(event_id):
    db.session.delete(db.get_or_404(SpendingEvent, event_id))
    db.session.commit()
    flash(_("Evento eliminato; i suoi movimenti restano."), "success")
    return redirect(url_for("events.index"))


@events_bp.route("/assign", methods=["POST"])
def assign():
    """Put the selected movements in an event, or take them out (empty event)."""
    event_id = request.form.get("event_id", type=int)
    event = db.session.get(SpendingEvent, event_id) if event_id else None
    count = spending_events.assign(sorted(form_ids()), event)
    db.session.commit()
    if event:
        flash(_("%(count)s movimenti aggiunti a «%(name)s».", count=count, name=event.name), "success")
    else:
        flash(_("%(count)s movimenti tolti dagli eventi.", count=count), "success")
    return back_to("events.detail", event_id=event.id) if event else back_to("events.index")
