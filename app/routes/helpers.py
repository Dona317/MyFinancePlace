"""Small helpers shared by the HTML routes."""
import csv
import io
import re
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

from flask import Response, flash, redirect, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.services.parsing import MAX_AMOUNT, to_date, to_decimal


def safe_next() -> str | None:
    """Local path to go back to after an action (never an external URL)."""
    target = request.values.get("next") or ""
    return target if target.startswith("/") and not target.startswith("//") and "\\" not in target else None


def back_to(endpoint: str, **values):
    """Redirect to the page the user came from (`next`), or to `endpoint`."""
    return redirect(safe_next() or url_for(endpoint, **values))


def year_arg(default: int, choices=None) -> int:
    """`?year=` as a number; `default` when missing, not a year, or (with `choices`) not one of them."""
    value = request.args.get("year", "")
    year = int(value) if value.isdigit() and 1900 < int(value) < 3000 else None
    return year if year is not None and (choices is None or year in choices) else default


def uploaded_file():
    """The file posted as `file`, or None when none was chosen."""
    upload = request.files.get("file")
    return upload if upload and upload.filename else None


def download(content, filename: str, mimetype: str) -> Response:
    """`content` as a file to save, named `filename`."""
    return Response(content, mimetype=mimetype, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def csv_text(rows) -> str:
    """Rows as a CSV that Excel opens right: semicolons, and a BOM so it reads the accents as UTF-8."""
    buffer = io.StringIO()
    csv.writer(buffer, delimiter=";").writerows(rows)
    return "\ufeff" + buffer.getvalue()


@contextmanager
def flash_errors(*kinds: type[Exception], rollback: bool = False):
    """Show the message of a ValueError (or of `kinds`) as an error instead of failing; the caller then
    goes on (usually to its redirect)."""
    try:
        yield
    except kinds or (ValueError,) as exc:
        if rollback:
            db.session.rollback()
        flash(str(exc), "error")


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
