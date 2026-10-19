"""Scadenzario (F23): every deadline in a month grid, the weeks ahead, the hand-written ones, the .ics file."""
from datetime import date, datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import format_date
from flask_babel import gettext as _

from app.extensions import db
from app.models.reminder import Reminder
from app.routes.helpers import download, flash_errors
from app.services import deadlines, periods
from app.services.parsing import to_date, to_decimal

deadlines_bp = Blueprint("deadlines", __name__, url_prefix="/deadlines")


def _month() -> date:
    try:
        return datetime.strptime(request.args.get("month", ""), "%Y-%m").date()
    except ValueError:
        return periods.first_of_month(date.today())


@deadlines_bp.route("/")
def index():
    today = date.today()
    edit = db.session.get(Reminder, request.args.get("edit", type=int) or 0)
    grid = deadlines.month_grid(_month())
    return render_template("deadlines/index.html", grid=grid, today=today,
                           month_title=format_date(grid["month"], "LLLL yyyy").capitalize(),
                           upcoming=deadlines.upcoming(today), reminders=Reminder.query.order_by(Reminder.due).all(),
                           repeats=deadlines.REPEATS, edit=edit, fiscal=deadlines.fiscal_on())


def _save(reminder: Reminder | None):
    form = request.form
    with flash_errors(rollback=True):
        saved = deadlines.save(reminder, title=form.get("title", ""), due=to_date(form.get("due")),
                               repeat=form.get("repeat", "none"), amount=to_decimal(form.get("amount")),
                               notes=form.get("notes"))
        db.session.commit()
        flash(_("Scadenza «%(title)s» salvata.", title=saved.title), "success")
        return redirect(url_for("deadlines.index", month=f"{saved.due:%Y-%m}"))
    return redirect(url_for("deadlines.index"))


@deadlines_bp.route("/new", methods=["POST"])
def create():
    return _save(None)


@deadlines_bp.route("/<int:reminder_id>/edit", methods=["POST"])
def edit(reminder_id):
    return _save(db.get_or_404(Reminder, reminder_id))


@deadlines_bp.route("/<int:reminder_id>/done", methods=["POST"])
def done(reminder_id):
    """A one-off deadline taken care of; a repeating one moves on to its next date."""
    reminder = db.get_or_404(Reminder, reminder_id)
    if reminder.repeat == "none":
        reminder.done = not reminder.done
    else:
        reminder.due = periods.add_months(reminder.due, 1 if reminder.repeat == "monthly" else 12)
    db.session.commit()
    return redirect(request.referrer or url_for("deadlines.index"))


@deadlines_bp.route("/<int:reminder_id>/delete", methods=["POST"])
def delete(reminder_id):
    db.session.delete(db.get_or_404(Reminder, reminder_id))
    db.session.commit()
    flash(_("Scadenza eliminata."), "success")
    return redirect(url_for("deadlines.index"))


@deadlines_bp.route("/fiscal", methods=["POST"])
def fiscal():
    deadlines.set_fiscal(request.form.get("on") == "1")
    db.session.commit()
    return redirect(url_for("deadlines.index"))


@deadlines_bp.route("/scadenze.ics")
def calendar_file():
    """The next twelve months (and the last one) for Google Calendar, Outlook or the phone's calendar."""
    today = date.today()
    return download(deadlines.ics(today - timedelta(days=31), today + timedelta(days=366)), "scadenze.ics",
                    "text/calendar; charset=utf-8")
