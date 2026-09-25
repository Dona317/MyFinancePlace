"""Small helpers shared by the HTML routes."""
from flask import request


def safe_next() -> str | None:
    """Local path to go back to after an action (never an external URL)."""
    target = request.values.get("next") or ""
    return target if target.startswith("/") and not target.startswith("//") and "\\" not in target else None


def form_ids(name: str = "ids") -> set[int]:
    """Numeric ids posted under `name` (checkboxes, hidden fields); anything else is ignored."""
    return {int(i) for i in request.form.getlist(name) if i.isdigit()}
