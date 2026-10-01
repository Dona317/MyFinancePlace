"""Small helpers shared by the HTML routes."""
import re
from datetime import date
from decimal import Decimal

from flask import flash, redirect, request

from app.extensions import db
from app.services.parsing import MAX_AMOUNT, to_date, to_decimal
from flask_babel import gettext as _


def safe_next() -> str | None:
    """Local path to go back to after an action (never an external URL)."""
    target = request.values.get("next") or ""
    return target if target.startswith("/") and not target.startswith("//") and "\\" not in target else None


def form_ids(name: str = "ids") -> set[int]:
    """Numeric ids posted under `name` (checkboxes, hidden fields); anything else is ignored."""
    return {int(i) for i in request.form.getlist(name) if i.isdigit()}


def save_form(obj, fill, render, message, target):
    """POST of a new/edit page: `fill(obj)` from the form, save, flash `message(obj)` and go to `target(obj)`;
    on a ValueError show the form again, as typed, with the error. `render(obj or None, values)` draws the form."""
    is_new = obj.id is None
    try:
        fill(obj)
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return render(None if is_new else obj, request.form)
    if is_new:
        db.session.add(obj)
    db.session.commit()
    flash(message(obj), "success")
    return redirect(target(obj))


def delete_and_redirect(obj, message: str, target: str):
    db.session.delete(obj)
    db.session.commit()
    flash(message, "success")
    return redirect(target)


# ── Reading form fields: a ValueError carries the message to show the user ────

ITALIAN_THOUSANDS = re.compile(r"[1-9]\d{0,2}(\.\d{3})+")


def form_text(name: str, label: str, required: bool = False) -> str | None:
    value = (request.form.get(name) or "").strip()
    if required and not value:
        raise ValueError(_("%(label)s: campo obbligatorio.", label=label))
    return value or None


def form_decimal(name: str, label: str, required: bool = False, allow_negative: bool = False) -> Decimal | None:
    """A number typed Italian- or English-style ("1.234,56" or "1234.56"); empty → None unless required."""
    raw = (request.form.get(name) or "").strip()
    if not raw:
        if required:
            raise ValueError(_("%(label)s: campo obbligatorio.", label=label))
        return None
    # "30.000" typed in Italy is thirty thousand, not thirty
    value = to_decimal(raw.replace(".", "") if ITALIAN_THOUSANDS.fullmatch(raw.lstrip("-")) else raw)
    if value is None or abs(value) > MAX_AMOUNT:
        raise ValueError(_("%(label)s: «%(raw)s» non è un numero valido.", label=label, raw=raw))
    if value < 0 and not allow_negative:
        raise ValueError(_("%(label)s: non può essere negativo.", label=label))
    return value


def form_date(name: str, label: str, required: bool = False) -> date | None:
    raw = (request.form.get(name) or "").strip()
    if not raw:
        if required:
            raise ValueError(_("%(label)s: campo obbligatorio.", label=label))
        return None
    value = to_date(raw)
    if value is None:
        raise ValueError(_("%(label)s: «%(raw)s» non è una data valida.", label=label, raw=raw))
    return value


def form_int(name: str, label: str, minimum: int = 0, maximum: int | None = None) -> int | None:
    raw = (request.form.get(name) or "").strip()
    if not raw:
        return None
    if not raw.isdigit() or int(raw) < minimum or (maximum is not None and int(raw) > maximum):
        limits = f"tra {minimum} e {maximum}" if maximum is not None else f"da {minimum} in su"
        raise ValueError(_("%(label)s: inserisci un numero intero %(limits)s.", label=label, limits=limits))
    return int(raw)


def form_choice(name: str, label: str, choices) -> str:
    value = (request.form.get(name) or "").strip()
    if value not in choices:
        raise ValueError(_("%(label)s: scelta non valida.", label=label))
    return value
