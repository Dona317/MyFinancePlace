from flask import Blueprint, render_template, request, redirect, url_for

transactions_bp = Blueprint("transactions", __name__, url_prefix="/transactions")


@transactions_bp.route("/")
def index():
    # TODO: fetch and filter transactions from DB
    transactions = []
    return render_template("transactions/index.html", transactions=transactions)


@transactions_bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        # TODO: save new transaction
        return redirect(url_for("transactions.index"))
    return render_template("transactions/form.html", transaction=None, action="new")


@transactions_bp.route("/<int:tx_id>/edit", methods=["GET", "POST"])
def edit(tx_id):
    # TODO: fetch transaction by id
    transaction = None
    if request.method == "POST":
        # TODO: update transaction
        return redirect(url_for("transactions.index"))
    return render_template("transactions/form.html", transaction=transaction, action="edit")


@transactions_bp.route("/<int:tx_id>/delete", methods=["POST"])
def delete(tx_id):
    # TODO: delete transaction
    return redirect(url_for("transactions.index"))
