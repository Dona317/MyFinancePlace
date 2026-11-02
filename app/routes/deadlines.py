"""
Promemoria (F23): one page with the reminders on top, then every deadline in a month grid, the next ones in date
or amount order, the hand-written ones and the .ics file. Its blocks are arranged with Modifica like the dashboard.
"""
from datetime import date, datetime, timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_babel import format_date
from flask_babel import gettext as _

from app.extensions import db
from app.models.reminder import Reminder
from app.routes.helpers import download, flash_errors
from app.services import deadlines, notifications, page_layout, periods, sections
from app.services.i18n import _l
from app.services.parsing import to_date, to_decimal

deadlines_bp = Blueprint("deadlines", __name__, url_prefix="/deadlines")


def _month() -> date:
    try:
        return datetime.strptime(request.args.get("month", ""), "%Y-%m").date()
    except ValueError:
        return periods.first_of_month(date.today())


# The blocks of the page: {id: default width (thirds)}, in the default order
BLOCKS = {"reminders": 3, "calendar": 2, "next": 1, "mine": 2, "fiscal": 1}
BLOCK_TITLES = {"reminders": _l("Promemoria"), "calendar": _l("Calendario del mese"), "next": _l("Prossime scadenze"),
                "mine": _l("Le tue scadenze"), "fiscal": _l("Scadenze fiscali")}
LAYOUT_SETTING = "deadlines.layout"
NEXT_DAYS, NEXT_ROWS = 366, 100  # the next deadlines: a year ahead, the first hundred


def render_page():
    """The reminders and, when the section is on, the deadlines; shared by the bell's page and the Scadenzario."""
    today = date.today()
    items = notifications.collect()
    hidden = [n for n in notifications.collect(include_dismissed=True) if n.key in set(notifications.dismissed())]
    context = {"items": items, "hidden": hidden, "today": today, "with_deadlines": sections.allowed("deadlines"),
               "layout": page_layout.load(LAYOUT_SETTING, BLOCKS), "titles": BLOCK_TITLES}
    if context["with_deadlines"]:
        grid = deadlines.month_grid(_month())
        upcoming = deadlines.upcoming(today, days=NEXT_DAYS)
        context.update(grid=grid, month_title=format_date(grid["month"], "LLLL yyyy").capitalize(),
                       upcoming=upcoming, upcoming_60=[d for d in upcoming if d.day <= today + timedelta(days=60)],
                       next_items=upcoming[:NEXT_ROWS], reminders=Reminder.query.order_by(Reminder.due).all(),
                       repeats=deadlines.REPEATS, notices=deadlines.NOTICES, edit=db.session.get(Reminder, request.args.get("edit", type=int) or 0),
                       fiscal=deadlines.fiscal_on())
    return render_template("deadlines/index.html", **context)


@deadlines_bp.route("/")
def index():
    return render_page()


@deadlines_bp.route("/layout", methods=["POST"])
def save_layout():
    """The blocks of the page: {"widgets": [{id, span, height, visible}]} or {"reset": true}."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error=_("Atteso un oggetto JSON.")), 400
    if data.get("reset"):
        return jsonify(layout=page_layout.reset(LAYOUT_SETTING, BLOCKS))
    if not isinstance(data.get("widgets"), list):
        return jsonify(error=_("Manca l'elenco dei blocchi.")), 400
    return jsonify(layout=page_layout.save(LAYOUT_SETTING, BLOCKS, data["widgets"]))


def _save(reminder: Reminder | None):
    form = request.form
    with flash_errors(rollback=True):
        saved = deadlines.save(reminder, title=form.get("title", ""), due=to_date(form.get("due")),
                               repeat=form.get("repeat", "none"), amount=to_decimal(form.get("amount")),
                               notes=form.get("notes"), notice_days=form.get("notice_days", type=int))
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
