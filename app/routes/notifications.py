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
    items = notifications.collect()
    hidden = [n for n in notifications.collect(include_dismissed=True) if n.key in set(notifications.dismissed())]
    return render_template("notifications/index.html", items=items, hidden=hidden)


@notifications_bp.route("/dismiss", methods=["POST"])
def dismiss():
    """Hide one reminder (key) or all those currently shown."""
    keys = request.form.getlist("key")
    if request.form.get("all"):
        keys = [n.key for n in notifications.collect()]
    notifications.dismiss(keys)
    return back_to("notifications.index")


@notifications_bp.route("/api")
def api():
    """Current reminders as JSON (e.g. for a phone widget)."""
    return {"notifications": [n.to_dict() for n in notifications.collect()]}
