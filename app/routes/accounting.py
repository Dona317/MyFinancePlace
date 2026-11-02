import json
from datetime import date

from apiflask import APIBlueprint
from flask import Response, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.year_close import YearClose
from app.routes.helpers import form_decimal, year_arg
from app.services import analytics, family, net_worth_growth, owners, settings_store, wealth, year_close
from app.services.parsing import to_date
from app.services.ui_settings import current_settings

accounting_bp = APIBlueprint(
    "accounting",
    __name__,
    url_prefix="/accounting",
    tag="Accounting"
)

# Contabilità: the tabs in their order, each with the setting that switches it off (none: always there)
TABS = (("accounting.balance_sheet", "accounting_balance_sheet"), ("accounting.income_statement", "accounting_income_statement"),
        ("accounting.cash_flow", "accounting_cash_flow"), ("accounting.growth", None), ("accounting.closes", None))


@accounting_bp.route("/")
def index():
    """Contabilità opens on its first tab (the balance sheet, unless switched off)."""
    settings = current_settings()
    return redirect(url_for(next(endpoint for endpoint, setting in TABS if setting is None or settings.get(setting, True))))


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
        financed=wealth.financed_assets(on),
        people=family.by_person(on) if owners.holders() else [],
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


@accounting_bp.route("/growth")
def growth():
    """Where the net worth growth comes from: saving, markets, debt repaid, new assets."""
    months = request.args.get("months", 12, type=int)
    months = months if months in (6, 12, 24, 36) else 12
    rows = net_worth_growth.months(months)
    return render_template("accounting/growth.html", rows=rows, velocity=net_worth_growth.velocity(rows), months=months,
                           labels=[r.end.strftime("%m/%y") for r in rows])


@accounting_bp.route("/closes")
def closes():
    """The statements of each closed year: saved on 1 January, again on request when its transactions changed."""
    return render_template("accounting/closes.html", years=year_close.overview(), this_year=date.today().year)


@accounting_bp.route("/closes/<int:year>", methods=["POST"])
def close_year(year: int):
    """Save the statements of a past year again (a new version), with the transactions as they are now."""
    if not 1900 < year < date.today().year:
        flash(_("Si chiudono solo gli anni passati."), "warning")
        return redirect(url_for("accounting.closes"))
    row = year_close.close(year)
    flash(_("Bilanci %(year)s salvati (versione %(version)s).", year=year, version=row.version), "success")
    return redirect(url_for("accounting.closes"))


@accounting_bp.route("/closes/<int:close_id>.json")
def close_file(close_id: int):
    """A saved version, as a file to keep."""
    row = db.get_or_404(YearClose, close_id)
    body = json.dumps({"year": row.year, "version": row.version, "closed_at": row.closed_at.isoformat(), **row.data},
                      ensure_ascii=False, indent=2)
    return Response(body, mimetype="application/json",
                    headers={"Content-Disposition": f'attachment; filename="bilanci-{row.year}-v{row.version}.json"'})
