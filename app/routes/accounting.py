from flask import render_template
from apiflask import APIBlueprint

accounting_bp = APIBlueprint(
    "accounting",
    __name__,
    url_prefix="/accounting",
    tag="Accounting"
)

@accounting_bp.route("/")
def index():
    return render_template("accounting/index.html")


@accounting_bp.route("/balance-sheet")
def balance_sheet():
    # TODO: pass assets, liabilities, equity data
    return render_template("accounting/balance_sheet.html")


@accounting_bp.route("/income-statement")
def income_statement():
    # TODO: pass revenue, expenses, net income data
    return render_template("accounting/income_statement.html")


@accounting_bp.route("/cash-flow")
def cash_flow():
    # TODO: pass operating, investing, financing cash flow data
    return render_template("accounting/cash_flow.html")
