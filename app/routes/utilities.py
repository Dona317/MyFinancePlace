"""Bollette (F23): bills with their consumption, cost per unit, seasons, another offer, reading a bill with the AI."""
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.transaction import Transaction
from app.models.utility import UtilityReading
from app.models.wealth import Document
from app.routes.helpers import flash_errors
from app.services import ai_extraction, utilities
from app.services.parsing import to_date, to_decimal

utilities_bp = Blueprint("utilities", __name__, url_prefix="/utilities")


def _utility() -> str:
    chosen = request.args.get("utility", "")
    if chosen in utilities.UTILITIES:
        return chosen
    used = [r.utility for r in utilities.readings()]
    return max(set(used), key=used.count) if used else "power"


@utilities_bp.route("/")
def index():
    utility = _utility()
    offer, offer_values = None, {k: request.args.get(k, "") for k in ("unit_price", "fixed")}
    if request.args.get("unit_price"):
        with flash_errors():
            offer = utilities.with_offer(utility, to_decimal(offer_values["unit_price"]), to_decimal(offer_values["fixed"]))
    edit = db.session.get(UtilityReading, request.args.get("edit", type=int) or 0)
    read = {k: request.args.get(k) for k in ("supplier", "start", "end", "document_id")}
    read.update(consumption=to_decimal(request.args.get("consumption")), amount=to_decimal(request.args.get("amount")))
    documents = (Document.query.filter((Document.mimetype == "application/pdf") | Document.mimetype.like("image/%"))
                 .order_by(Document.uploaded_at.desc()).limit(50).all())
    return render_template("utilities/index.html", utility=utility, utilities=utilities.UTILITIES,
                           summaries=[utilities.summary(key) for key in utilities.UTILITIES],
                           summary=utilities.summary(utility), readings=list(reversed(utilities.readings(utility))),
                           seasons=utilities.seasons(utility), chart=utilities.chart(utility),
                           candidates=utilities.candidates(), offer=offer, offer_values=offer_values, edit=edit,
                           read=read if read["end"] else None, documents=documents, ai_on=ai_extraction.provider() is not None,
                           helpers=utilities, today=date.today())


def _values(form) -> dict:
    return dict(utility=form.get("utility", ""), start=to_date(form.get("start")), end=to_date(form.get("end")),
                amount=to_decimal(form.get("amount")), consumption=to_decimal(form.get("consumption")),
                supplier=form.get("supplier"), notes=form.get("notes"))


@utilities_bp.route("/new", methods=["POST"])
def create():
    form = request.form
    transaction = db.session.get(Transaction, form.get("transaction_id", type=int) or 0)
    with flash_errors(rollback=True):
        reading = utilities.save(None, **_values(form), transaction=transaction,
                                 document_id=form.get("document_id", type=int))
        db.session.commit()
        flash(_("Bolletta registrata."), "success")
        return redirect(url_for("utilities.index", utility=reading.utility))
    return redirect(url_for("utilities.index", utility=form.get("utility")))


@utilities_bp.route("/<int:reading_id>/edit", methods=["POST"])
def edit(reading_id):
    reading = db.get_or_404(UtilityReading, reading_id)
    with flash_errors(rollback=True):
        utilities.save(reading, **_values(request.form))
        db.session.commit()
        flash(_("Bolletta aggiornata."), "success")
    return redirect(url_for("utilities.index", utility=reading.utility))


@utilities_bp.route("/<int:reading_id>/delete", methods=["POST"])
def delete(reading_id):
    reading = db.get_or_404(UtilityReading, reading_id)
    utility = reading.utility
    db.session.delete(reading)
    db.session.commit()
    flash(_("Bolletta eliminata."), "success")
    return redirect(url_for("utilities.index", utility=utility))


@utilities_bp.route("/read", methods=["POST"])
def read():
    """A bill in Documents read by the AI: its fields go into the form, to check and save."""
    document = db.get_or_404(Document, request.form.get("document_id", type=int))
    with flash_errors():
        found = utilities.read_bill(document)
        flash(_("Dati letti dalla bolletta: controllali e salva."), "success")
        return redirect(url_for("utilities.index", utility=found["utility"] or None, supplier=found["supplier"],
                                start=found["start"].isoformat(), end=found["end"].isoformat(),
                                consumption=found["consumption"], amount=found["amount"], document_id=document.id)
                        + "#reading-form")
    return redirect(url_for("utilities.index"))
