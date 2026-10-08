from datetime import date

from apiflask import APIBlueprint
from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.routes.helpers import form_decimal, year_arg
from app.services import analytics, settings_store, wealth
from app.services.parsing import to_date

accounting_bp = APIBlueprint(
    "accounting",
    __name__,
    url_prefix="/accounting",
    tag="Accounting"
)

@accounting_bp.route("/")
def index():
    year = date.today().year
    return render_template(
        "accounting/index.html",
        trend=wealth.net_worth_trend(),
        monthly=analytics.monthly_series(year),
        month_count=date.today().month,
        year=year,
    )


@accounting_bp.route("/balance-sheet")
def balance_sheet():
    choices = wealth.month_ends()
    on = to_date(request.args.get("date")) or choices[0]
    on = min(on, choices[0])  # no balance sheet of the future
    if on not in choices:
        choices.append(on)
    return render_template(
        "accounting/balance_sheet.html",
        sheet=wealth.balance_sheet(on),
        choices=sorted(choices, reverse=True),
        opening_cash=wealth.opening_cash(),
        today=choices[0],
    )


@accounting_bp.route("/balance-sheet/opening", methods=["POST"])
def opening_cash():
    """Money on the accounts before the first transaction recorded in the app."""
    try:
        amount = form_decimal("opening_cash", _("Saldo iniziale"), allow_negative=True)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("accounting.balance_sheet"))
    settings_store.set(wealth.OPENING_CASH_SETTING, str(amount) if amount else None)
    flash(_("Saldo iniziale dei conti aggiornato."), "success")
    return redirect(url_for("accounting.balance_sheet"))


@accounting_bp.route("/income-statement")
def income_statement():
    years = analytics.available_years()
    year = year_arg(date.today().year)
    report = analytics.income_statement(year)
    return render_template("accounting/income_statement.html", report=report, years=years, year=year)


@accounting_bp.route("/cash-flow")
def cash_flow():
    years = analytics.available_years()
    year = year_arg(date.today().year)
    report = analytics.cash_flow(year)
    return render_template("accounting/cash_flow.html", report=report, years=years, year=year)
