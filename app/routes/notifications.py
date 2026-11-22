from apiflask import APIBlueprint
from flask import render_template, request

from app.routes.helpers import back_to
from app.services import notifications

notifications_bp = APIBlueprint(
    "notifications",
    __name__,
    url_prefix="/notifications",
    tag="Notifications"
)


@notifications_bp.route("/")
def index():
    """The reminders, with the deadlines under them (one page: Promemoria)."""
    from app.routes.deadlines import render_page
    return render_page()


PEEK = 6  # reminders in the bell's window


@notifications_bp.route("/peek")
def peek():
    """F100: the latest reminders, most urgent first, for the bell's window (a fragment, fetched when it opens)."""
    items = notifications.collect()
    back = request.args.get("back", "")
    return render_template("notifications/_peek.html", items=items[:PEEK], more=max(0, len(items) - PEEK), total=len(items),
                           back=back if back.startswith("/") and not back.startswith("//") else "")


@notifications_bp.route("/dismiss", methods=["POST"])
def dismiss():
    """Hide one reminder (key) or all those currently shown."""
    keys = request.form.getlist("key")
    if request.form.get("all"):
        keys = [n.key for n in notifications.collect()]
    notifications.dismiss(keys)
    if request.headers.get("X-Requested-With") == "fetch":  # the bell's window: it stays open and reloads its list
        return "", 204
    return back_to("notifications.index")


@notifications_bp.route("/api")
def api():
    """Current reminders as JSON (e.g. for a phone widget)."""
    return {"notifications": [n.to_dict() for n in notifications.collect()]}
