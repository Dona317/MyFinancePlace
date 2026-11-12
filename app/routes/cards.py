"""
Payment cards (F41), on the accounts' blueprint: a card is added from its account, changed, deleted; its movements
are the transactions filtered by card (services.cards).
"""
from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.card import Card
from app.routes.accounts import accounts_bp
from app.services import accounts, cards, field_crypto, owners
from app.services.parsing import to_decimal


def _input() -> cards.CardInput:
    form = request.form
    return cards.CardInput(
        name=form.get("name", ""), kind=form.get("kind", "debit"), network=form.get("network") or None,
        number=form.get("number"), expiry=form.get("expiry"), holder=form.get("holder"),
        account_id=form.get("account_id", type=int), credit_limit=to_decimal(form.get("credit_limit")),
        statement_day=form.get("statement_day", type=int), contactless=bool(form.get("contactless")),
        notes=form.get("notes"), active="1" in form.getlist("active") if "active" in form else True,
        forget_number=bool(form.get("forget_number")))


def _page(card: Card | None, values: dict, account_id: int | None = None):
    return render_template("accounts/card_form.html", card=card, values=values, kinds=cards.KINDS,
                           networks=cards.NETWORKS, accounts=accounts.active(), holders=owners.holders(),
                           account_id=account_id if account_id is not None else (card.account_id if card else None))


def _save(card: Card | None):
    if request.method == "GET":
        return _page(card, {}, request.args.get("account", type=int))
    try:
        card, whole = cards.save(card, _input())
    except (cards.CardError, ValueError) as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return _page(card, request.form.to_dict())
    db.session.commit()
    flash(_("Carta «%(name)s» salvata.", name=card.name), "success")
    if whole:
        flash(_("Il numero intero è salvato cifrato: lo vedi solo con «Mostra il numero» nella pagina della carta."),
              "info")
    return redirect(url_for("accounts.detail", account_id=card.account_id) + "#cards" if card.account_id
                    else url_for("accounts.index"))


@accounts_bp.route("/cards/new", methods=["GET", "POST"])
def card_new():
    return _save(None)


@accounts_bp.route("/cards/<int:card_id>/edit", methods=["GET", "POST"])
def card_edit(card_id):
    return _save(db.get_or_404(Card, card_id))


@accounts_bp.route("/cards/<int:card_id>/number", methods=["POST"])
def card_number(card_id):
    """The whole number, decrypted only when asked for (the eye on the card's page); never in a page's HTML."""
    card = db.get_or_404(Card, card_id)
    try:
        number = cards.full_number(card)
    except field_crypto.Unreadable:
        return jsonify(error=_("Il numero è stato cifrato con un'altra chiave (un backup di un altro computer): "
                               "riscrivilo per salvarlo di nuovo.")), 409
    if number is None:
        return jsonify(error=_("Il numero intero di questa carta non è salvato.")), 404
    return jsonify(number=number)


@accounts_bp.route("/cards/<int:card_id>/delete", methods=["POST"])
def card_delete(card_id):
    card = db.get_or_404(Card, card_id)
    back = (url_for("accounts.detail", account_id=card.account_id) + "#cards") if card.account_id else url_for("accounts.index")
    cards.delete(card)
    db.session.commit()
    flash(_("Carta «%(name)s» eliminata: i suoi movimenti restano, senza carta.", name=card.name), "success")
    return redirect(back)


def account_cards(account: Account) -> list[dict]:
    """The cards of an account with what they paid this month, for its page."""
    return [{"card": c, "month": cards.month_spending(c), "count": cards.movements_count(c),
             "expiry": cards.expiry_date(c), "soon": cards.expires_soon(c)} for c in cards.of_account(account)]
