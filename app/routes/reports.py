import re
from datetime import date, timedelta

from flask import Blueprint, render_template, request
from flask_babel import gettext as _

from app.extensions import db
from app.models.client import ClientGroup
from app.models.transaction import Transaction
from app.routes.helpers import csv_text, download, year_arg
from app.services import (
    accounts,
    analytics,
    annual_review,
    categories,
    groups,
    i18n,
    periods,
    reports,
    spending_rhythm,
    studio,
    transfer,
)
from app.services.analytics import UNCATEGORIZED
from app.services.display import number
from app.services.totals import analysed, excluded_total

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
    if filters["category"] not in categories.excluded_names():  # F22: unless an excluded one is asked for
        query = query.filter(analysed())
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
    if not filters["category"]:
        types = [tx_type] if tx_type else ["income", "expense"]
        context["excluded"] = excluded_total(Transaction.type.in_(types), Transaction.date >= filters["start"],
                                             Transaction.date < filters["end"])
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
    return download("\ufeff" + transfer.to_csv(rows), name, "text/csv")


def _summary_year() -> int:
    years = analytics.available_years()
    return year_arg(max(years), choices=years)


@reports_bp.route("/summary")
def summary():
    """The year as a category × month table, each cell shaded by its share of the row's busiest month."""
    year = _summary_year()
    table = analytics.summary_table(year, analytics.months_to_show(year))
    return render_template("reports/summary.html", table=table, year=year, years=analytics.available_years(),
                           tabs=reports.TABS, uncategorized=UNCATEGORIZED,
                           natures=categories.natures(), nature_labels=categories.NATURES)


@reports_bp.route("/summary.csv")
def summary_csv():
    """The same table as a spreadsheet: one line per category (subcategories after their main one)."""
    year = _summary_year()
    table = analytics.summary_table(year, analytics.months_to_show(year))
    rows = [[_("Sezione"), _("Categoria"), *table["labels"], _("Totale"), _("Media mensile"),
             _("Anno prima"), _("Variazione %")]]

    def line(section, name, item, previous=True):
        rows.append([section, name, *(number(v) for v in item["months"]), number(item["total"]),
                         number(item["average"]), number(item["previous"]) if previous else "",
                         number(item["change"], 1) if previous and item["change"] is not None else ""])

    for key, section in (("income", _("Entrate")), ("expense", _("Uscite"))):
        for item in table[key]["rows"]:
            line(section, i18n.tr(item["name"]), item)
            for child in item["children"]:
                line(section, f"{item['name']}{categories.SEPARATOR}{child['name']}", child)
        line(section, _("Totale"), table[key]["total"])
    line(_("Netto"), _("Netto"), table["net"] | {"previous": 0, "change": None}, previous=False)
    rows.append([_("Tasso di risparmio"), _("Tasso di risparmio"),
                     *("" if v is None else number(v, 1) for v in table["savings"]["months"]),
                     "" if table["savings"]["total"] is None else number(table["savings"]["total"], 1)])
    return download(csv_text(rows), f"riepilogo_{year}.csv", "text/csv")


@reports_bp.route("/rhythm")
def rhythm():
    """When the money goes out: the calendar of the year, the weekdays, and what changed last month."""
    today = date.today()
    year = _summary_year()
    start = date(year, 1, 1)
    return render_template("reports/rhythm.html", year=year, years=analytics.available_years(), tabs=reports.TABS,
                           calendar=spending_rhythm.calendar(year, today),
                           weekdays=spending_rhythm.weekdays(start, min(date(year, 12, 31), today)),
                           changes=spending_rhythm.changes(today), month_labels=periods.month_labels())


@reports_bp.route("/year")
def year_review():
    """The year in review (F23): net worth, where its change came from, spending against the year before, and more."""
    year = _summary_year()
    return render_template("reports/year_review.html", data=annual_review.review(year), year=year,
                           years=analytics.available_years(), tabs=reports.TABS,
                           groups=groups.of(studio.current()))


@reports_bp.route("/year.pdf")
def year_review_pdf():
    year = _summary_year()
    return download(annual_review.build_pdf(annual_review.review(year)), f"bilancio_{year}.pdf", "application/pdf")


@reports_bp.route("/year/group/<int:group_id>.pdf")
def year_review_group_pdf(group_id):
    """The same review for every archive of a group (F21), with the group's totals first."""
    group = db.get_or_404(ClientGroup, group_id)
    year = _summary_year()
    slug = re.sub(r"[^a-z0-9]+", "_", group.name.lower()).strip("_") or "gruppo"
    return download(annual_review.build_group_pdf(group, year), f"bilancio_{year}_{slug}.pdf", "application/pdf")
