from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.transaction import Transaction
from app.services import forecast, settings_store, subscriptions

subscriptions_bp = Blueprint("subscriptions", __name__, url_prefix="/subscriptions")

KINDS = ("expense", "income")


@subscriptions_bp.route("/")
def index():
    kind = request.args.get("kind") if request.args.get("kind") in KINDS else "expense"
    # F99: the tab of Transazioni — its list is the register, held to the recurring movements of this kind
    from app.routes.transactions import register_context

    register = register_context(locked={"recurring": "1", "type": kind},
                                title=_("Transazioni ricorrenti in uscita") if kind == "expense" else _("Transazioni ricorrenti in entrata"))
    days = request.args.get("horizon", type=int)
    if days in subscriptions.HORIZONS:
        settings_store.set(subscriptions.HORIZON_SETTING, str(days))
    saved = settings_store.get(subscriptions.HORIZON_SETTING, str(subscriptions.UPCOMING_DAYS))
    days = int(saved) if saved.isdigit() and int(saved) in subscriptions.HORIZONS else subscriptions.UPCOMING_DAYS
    return render_template("subscriptions/index.html", data=subscriptions.overview(kind, date.today(), days),
                           kind=kind, frequencies=forecast.FREQUENCIES, horizon=days, horizons=subscriptions.HORIZONS,
                           register_html=render_template("transactions/_register.html", **register),
                           register_js=render_template("transactions/_register_js.html", **register))


def _back(tx: Transaction):
    return redirect(url_for("subscriptions.index", kind=tx.type if tx.type in KINDS else None))


@subscriptions_bp.route("/<int:tx_id>/stop", methods=["POST"])
def stop(tx_id):
    """No longer active: the series ends with its latest payment."""
    tx = db.get_or_404(Transaction, tx_id)
    subscriptions.stop(tx)
    db.session.commit()
    flash(_("«%(description)s» segnato come non più attivo: non compare più nelle previsioni.", description=tx.description), "success")
    return _back(tx)


@subscriptions_bp.route("/<int:tx_id>/resume", methods=["POST"])
def resume(tx_id):
    tx = db.get_or_404(Transaction, tx_id)
    subscriptions.resume(tx)
    db.session.commit()
    flash(_("«%(description)s» di nuovo attivo.", description=tx.description), "success")
    return _back(tx)
