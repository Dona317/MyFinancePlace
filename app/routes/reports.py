import csv as csv_module
import io
from datetime import date, timedelta

from flask import Blueprint, Response, render_template, request
from flask_babel import gettext as _

from app.services import accounts, analytics, categories, i18n, reports, transfer
from app.services.analytics import UNCATEGORIZED
from app.services.display import number

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")

LEGEND_SHOWN = 12  # categories listed next to the chart before «Mostra tutte»


def _day(name: str) -> date | None:
    try:
        return date.fromisoformat(request.args.get(name, ""))
    except ValueError:
        return None


def _filters() -> dict:
    """The choices in the query string, checked, with the period they give."""
    args = request.args
    tab = args.get("tab") if args.get("tab") in reports.TABS else "spending"
    period = args.get("period") if args.get("period") in reports.PERIODS else reports.DEFAULT_PERIOD
    custom_start, custom_end = _day("start"), _day("end")
    if period == "custom" and not (custom_start and custom_end):
        period = reports.DEFAULT_PERIOD
    start, end = reports.period_range(period, custom_start, custom_end)
    account = args.get("account", "").strip()
    return {
        "tab": tab, "period": period, "start": start, "end": end, "last_day": end - timedelta(days=1),
        "account": account if account == "none" or account.isdigit() else "",
        "category": args.get("category", "").strip() if tab != "cashflow" else "",
        "sort": args.get("sort") if args.get("sort") in reports.SORTS else "date",
    }


def _rows(filters: dict):
    query = reports.base_query(filters["start"], filters["end"], filters["account"])
    tx_type = reports.TAB_TYPE.get(filters["tab"])
    return query, tx_type, reports.transactions(query, tx_type, filters["category"] or None, filters["sort"])


@reports_bp.route("/")
def index():
    filters = _filters()
    query, tx_type, rows = _rows(filters)
    context = {"filters": filters, "rows": rows, "days": reports.by_day(rows) if filters["sort"] == "date" else None,
               "summary": reports.summary(rows) if tx_type else None}
    if tx_type:
        chosen = filters["category"]
        # a main category with subcategories (or one of them) chosen: the split by subcategory
        within = (chosen if categories.children(chosen) else categories.parents().get(chosen)) if chosen else None
        items = reports.breakdown(query, tx_type, within)
        prev_start, prev_end = reports.previous_range(filters["start"], filters["end"])
        previous = reports.total(reports.base_query(prev_start, prev_end, filters["account"]), tx_type)
        context.update(items=items, previous=previous, legend_shown=LEGEND_SHOWN, within=within,
                       total=sum(item["amount"] for item in items))
    else:
        context["flow"] = reports.cash_flow(query, filters["start"], filters["end"])
    account_list = accounts.active()
    return render_template(
        "reports/index.html", **context, tabs=reports.TABS, periods=reports.PERIODS, sorts=reports.SORTS,
        accounts=account_list, account_names={a.id: a.name for a in account_list},
        uncategorized=UNCATEGORIZED, query_args=request.args.to_dict(),
    )


@reports_bp.route("/csv")
def csv():
    """The transactions listed on the page, with the same filters."""
    filters = _filters()
    rows = sorted(_rows(filters)[2], key=lambda tx: (tx.date, tx.id))
    name = f"report_{filters['tab']}_{filters['start']:%Y-%m-%d}_{filters['last_day']:%Y-%m-%d}.csv"
    return Response("\ufeff" + transfer.to_csv(rows), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _summary_year() -> int:
    years = analytics.available_years()
    year = request.args.get("year", type=int)
    return year if year in years else max(years)


@reports_bp.route("/summary")
def summary():
    """The year as a category × month table, each cell shaded by its share of the row's busiest month."""
    year = _summary_year()
    table = analytics.summary_table(year, analytics.months_to_show(year))
    return render_template("reports/summary.html", table=table, year=year, years=analytics.available_years(),
                           tabs=reports.TABS, uncategorized=UNCATEGORIZED)


@reports_bp.route("/summary.csv")
def summary_csv():
    """The same table as a spreadsheet: one line per category (subcategories after their main one)."""
    year = _summary_year()
    table = analytics.summary_table(year, analytics.months_to_show(year))
    buffer = io.StringIO()
    writer = csv_module.writer(buffer, delimiter=";")
    writer.writerow([_("Sezione"), _("Categoria"), *table["labels"], _("Totale"), _("Media mensile"),
                     _("Anno prima"), _("Variazione %")])

    def line(section, name, item, previous=True):
        writer.writerow([section, name, *(number(v) for v in item["months"]), number(item["total"]),
                         number(item["average"]), number(item["previous"]) if previous else "",
                         number(item["change"], 1) if previous and item["change"] is not None else ""])

    for key, section in (("income", _("Entrate")), ("expense", _("Uscite"))):
        for item in table[key]["rows"]:
            line(section, i18n.tr(item["name"]), item)
            for child in item["children"]:
                line(section, f"{item['name']}{categories.SEPARATOR}{child['name']}", child)
        line(section, _("Totale"), table[key]["total"])
    line(_("Netto"), _("Netto"), table["net"] | {"previous": 0, "change": None}, previous=False)
    writer.writerow([_("Tasso di risparmio"), _("Tasso di risparmio"),
                     *("" if v is None else number(v, 1) for v in table["savings"]["months"]),
                     "" if table["savings"]["total"] is None else number(table["savings"]["total"], 1)])
    return Response("\ufeff" + buffer.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="riepilogo_{year}.csv"'})
