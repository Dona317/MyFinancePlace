from flask import Blueprint, render_template, request, redirect, url_for

debt_bp = Blueprint("debt", __name__, url_prefix="/debt")


@debt_bp.route("/")
def index():
    # TODO: fetch debts, compute totals and amortization schedules
    debts = []
    return render_template("debt/index.html", debts=debts)


@debt_bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        # TODO: save new debt entry
        return redirect(url_for("debt.index"))
    return render_template("debt/form.html", debt=None)
