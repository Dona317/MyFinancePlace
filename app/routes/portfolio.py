from flask import Blueprint, render_template, request, redirect, url_for

portfolio_bp = Blueprint("portfolio", __name__, url_prefix="/portfolio")


@portfolio_bp.route("/")
def index():
    # TODO: fetch holdings, compute totals, P&L
    holdings = []
    return render_template("portfolio/index.html", holdings=holdings)


@portfolio_bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        # TODO: save new holding
        return redirect(url_for("portfolio.index"))
    return render_template("portfolio/form.html", holding=None)


@portfolio_bp.route("/<int:holding_id>/delete", methods=["POST"])
def delete(holding_id):
    # TODO: delete holding
    return redirect(url_for("portfolio.index"))
