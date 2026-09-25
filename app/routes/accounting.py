from datetime import date
from flask import render_template, request
from apiflask import APIBlueprint
from app.services import analytics

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
    years = analytics.available_years()
    year = request.args.get("year", type=int) or date.today().year
    report = analytics.income_statement(year)
    return render_template("accounting/income_statement.html", report=report, years=years, year=year)


@accounting_bp.route("/cash-flow")
def cash_flow():
    years = analytics.available_years()
    year = request.args.get("year", type=int) or date.today().year
    report = analytics.cash_flow(year)
    return render_template("accounting/cash_flow.html", report=report, years=years, year=year)
