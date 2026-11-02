"""Lavoretti (F22): the register of odd jobs and occasional work, collecting them, the INPS threshold."""
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.gig import Gig
from app.models.transaction import Transaction
from app.routes.helpers import flash_errors, year_arg
from app.services import accounts, cash, family, gigs
from app.services.parsing import to_date, to_decimal

gigs_bp = Blueprint("gigs", __name__, url_prefix="/gigs")


def _gig(gig_id: int) -> Gig:
    return db.get_or_404(Gig, gig_id)


def _save(gig: Gig) -> None:
    form = request.form
    hours = to_decimal(form.get("hours")) if (form.get("hours") or "").strip() else None
    expenses = to_decimal(form.get("expenses")) if (form.get("expenses") or "").strip() else None
    gigs.save(gig, client=form.get("client", ""), description=form.get("description", ""), owner=family.from_form(),
              on=to_date(form.get("date")), hours=hours, gross=to_decimal(form.get("gross")),
              withholding_agent="withholding" in form, expenses=expenses, method=form.get("method", "transfer"),
              notes=form.get("notes"))


@gigs_bp.route("/")
def index():
    year = year_arg(date.today().year)
    wallet = cash.wallet()
    return render_template("gigs/index.html", data=gigs.year(year), year=year, years=gigs.years(),
                           clients=gigs.clients(), methods=gigs.METHODS, accounts=accounts.active(),
                           wallet_id=wallet.id if wallet else None, today=date.today(), gigs_service=gigs,
                           threshold=gigs.INPS_THRESHOLD)


@gigs_bp.route("/new", methods=["POST"])
def create():
    with flash_errors(rollback=True):
        gig = Gig()
        _save(gig)
        db.session.commit()
        flash(_("Lavoro «%(job)s» registrato.", job=gig.description), "success")
    return redirect(url_for("gigs.index", year=(to_date(request.form.get("date")) or date.today()).year))


@gigs_bp.route("/<int:gig_id>/edit", methods=["POST"])
def edit(gig_id):
    gig = _gig(gig_id)
    with flash_errors(rollback=True):
        _save(gig)
        db.session.commit()
        flash(_("Lavoro aggiornato."), "success")
    return redirect(url_for("gigs.index", year=gig.date.year))


@gigs_bp.route("/<int:gig_id>/delete", methods=["POST"])
def delete(gig_id):
    gig = _gig(gig_id)
    year = gig.date.year
    db.session.delete(gig)
    db.session.commit()
    flash(_("Lavoro eliminato: un incasso già registrato resta tra le transazioni."), "success")
    return redirect(url_for("gigs.index", year=year))


@gigs_bp.route("/<int:gig_id>/collect", methods=["POST"])
def collect(gig_id):
    gig = _gig(gig_id)
    tx_id = request.form.get("transaction_id", type=int)
    with flash_errors(rollback=True):
        if tx_id:
            gigs.link(gig, db.get_or_404(Transaction, tx_id))
        else:
            account_id = request.form.get("account_id", type=int)
            account = db.session.get(Account, account_id) if account_id else None
            if gig.method == "cash" and account is None:
                account = cash.wallet(create=True)
            gigs.collect(gig, account, to_date(request.form.get("on")) or date.today())
        db.session.commit()
        flash(_("Incassato: %(amount)s.", amount=gigs.net(gig)), "success")
    return redirect(url_for("gigs.index", year=gig.date.year))


@gigs_bp.route("/<int:gig_id>/unpay", methods=["POST"])
def unpay(gig_id):
    gig = _gig(gig_id)
    gigs.unpay(gig)
    db.session.commit()
    flash(_("Il lavoro torna da incassare."), "success")
    return redirect(url_for("gigs.index", year=gig.date.year))
