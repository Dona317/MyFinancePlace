"""Prestiti tra persone (F22): who owes what, sharing an expense, money given back."""
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.personal_loan import PersonalLoan
from app.models.transaction import Transaction
from app.routes.helpers import flash_errors
from app.services import display, personal_loans
from app.services.parsing import to_date, to_decimal

loans_bp = Blueprint("loans", __name__, url_prefix="/loans")


@loans_bp.route("/")
def index():
    return render_template("loans/index.html", people=personal_loans.people(), totals=personal_loans.totals(),
                           kinds=personal_loans.KINDS, expenses=personal_loans.recent("expense"),
                           incomes=personal_loans.recent("income"), today=date.today())


@loans_bp.route("/new", methods=["POST"])
def create():
    form = request.form
    with flash_errors(rollback=True):
        entry = personal_loans.add(form.get("person", ""), form.get("kind", ""), to_decimal(form.get("amount")),
                                   to_date(form.get("date")), form.get("description"), to_date(form.get("due")))
        db.session.commit()
        flash(_("Registrato per %(person)s.", person=entry.person), "success")
    return redirect(url_for("loans.index"))


@loans_bp.route("/share", methods=["POST"])
def share():
    """An expense paid for others too: equal parts, or the amount of each one."""
    form = request.form
    tx = db.get_or_404(Transaction, form.get("transaction_id", type=int))
    with flash_errors(rollback=True):
        names = [n.strip() for n in (form.get("people") or "").split(",") if n.strip()]
        each = to_decimal(form.get("each"))
        shares = {n: each for n in names} if each else personal_loans.equal_shares(abs(tx.amount), names)
        made = personal_loans.share_expense(tx, shares)
        db.session.commit()
        flash(_("«%(description)s» divisa: %(people)s ti devono %(amount)s in tutto.", description=tx.description,
                people=", ".join(e.person for e in made), amount=display.money(sum(e.amount for e in made))), "success")
    return redirect(url_for("loans.index"))


@loans_bp.route("/repaid", methods=["POST"])
def repaid():
    tx = db.get_or_404(Transaction, request.form.get("transaction_id", type=int))
    with flash_errors(rollback=True):
        entry = personal_loans.repayment(tx, request.form.get("person", ""))
        db.session.commit()
        flash(_("Restituzione di %(person)s registrata.", person=entry.person), "success")
    return redirect(url_for("loans.index"))


@loans_bp.route("/<int:entry_id>/delete", methods=["POST"])
def delete(entry_id):
    db.session.delete(db.get_or_404(PersonalLoan, entry_id))
    db.session.commit()
    flash(_("Voce eliminata."), "success")
    return redirect(url_for("loans.index"))
