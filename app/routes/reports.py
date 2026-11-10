import re
from datetime import date, timedelta

from flask import Blueprint, render_template, request
from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.client import ClientGroup
from app.models.transaction import Transaction
from app.routes.helpers import csv_text, download, year_arg
from app.services import (
    accounts,
    analytics,
    analytics_clusters,
    annual_review,
    categories,
    forecast,
    groups,
    i18n,
    pdf_report,
    periods,
    reports,
    spending_rhythm,
    studio,
    transfer,
)
from app.services.analytics import UNCATEGORIZED
from app.services.display import money, number
from app.services.totals import analysed, excluded_total

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")

LEGEND_SHOWN = 12  # categories listed next to the chart before «Mostra tutte»


def _day(name: str) -> date | None:
    try:
        return date.fromisoformat(request.args.get(name, ""))
    except ValueError:
        return None


def _filters(tab: str | None = None) -> dict:
    """The choices in the query string, checked, with the period they give; `tab` fixed by the page (Entrate, Uscite)."""
    args = request.args
    tab = tab or (args.get("tab") if args.get("tab") in reports.TABS else "spending")
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


OUTLOOK_MONTHS = 3  # the months the forecast of Entrate and Uscite looks ahead, after the current one


def _outlook(kind: str) -> dict | None:
    """The forecast of the income or the expenses: the current month and the next ones, with the method of the
    Previsioni page; None without enough history (3 complete months)."""
    prefs = forecast.preferences()
    fc = forecast.load(prefs["method"], prefs["window"], OUTLOOK_MONTHS, prefs["recurring"])
    if fc.history_months < 3 or not fc.months:
        return None
    rows = [{"label": r["label"], "value": r[kind]} for r in fc.months[:OUTLOOK_MONTHS + 1]]
    return {"rows": rows, "total": round(sum(r["value"] for r in rows[1:]), 2), "method": str(forecast.METHODS[prefs["method"]][0])}


@reports_bp.route("/income")
def income():
    """Entrate: a section of its own, the income of the period by category, its transactions and the net."""
    return index("income")


@reports_bp.route("/spending")
def spending():
    """Uscite: a section of its own, the expenses of the period by category, its transactions and the net."""
    return index("spending")


@reports_bp.route("/")
def index(tab: str | None = None):
    filters = _filters(tab)
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
        context["flow"] = flow = reports.cash_flow(query, filters["start"], filters["end"])
        # F65: the expenses of the period just before, month by month on the same positions (dashed on the chart)
        prev_start, prev_end = reports.previous_range(filters["start"], filters["end"])
        before = reports.cash_flow(reports.base_query(prev_start, prev_end, filters["account"]), prev_start, prev_end)
        flow["previous_expenses"] = (before["expenses"] + [None] * len(flow["labels"]))[:len(flow["labels"])]
        flow["previous_label"] = f"{prev_start:%m/%Y} – {prev_end - timedelta(days=1):%m/%Y}"
    if not filters["category"]:
        types = [tx_type] if tx_type else ["income", "expense"]
        context["excluded"] = excluded_total(Transaction.type.in_(types), Transaction.date >= filters["start"],
                                             Transaction.date < filters["end"])
    # the net of the period (income − expenses = saved), with the way to the cash flow of the same year
    context["net"] = analytics.totals(filters["start"], filters["end"])
    if tab in ("income", "spending"):
        context["outlook"] = _outlook("income" if tab == "income" else "expenses")
    if tab == "spending":  # «Spese e tendenze», for the year of the period
        year = filters["start"].year
        context.update(trend_report=analytics.lifestyle_report(year), year=year,
                       groups=analytics_clusters.cluster_breakdown(*analytics.year_bounds(year)))
    account_list = accounts.active()
    return render_template(
        "reports/index.html", **context, section=tab, tabs=reports.TABS, periods=reports.PERIODS, sorts=reports.SORTS,
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


@reports_bp.route("/report.pdf")
def report_pdf():
    """The page as a PDF with the same filters (tab, period, account, category): figures, categories, transactions.
    In the desktop app the download asks where to save it."""
    filters = _filters()
    query, tx_type, rows = _rows(filters)
    rows = sorted(rows, key=lambda tx: (tx.date, tx.id))
    tab = str(reports.TABS[filters["tab"]])
    period = f"{filters['start']:%d/%m/%Y} – {filters['last_day']:%d/%m/%Y}"
    subtitle = " · ".join(part for part in (period, filters["category"],
                                             accounts_name(filters["account"])) if part)
    if tx_type:
        items = reports.breakdown(query, tx_type, None)
        total = sum(item["amount"] for item in items)
        kpis = [(_("Totale"), money(total)), (_("Transazioni"), str(len(rows)))]
    else:
        items = []
        income = sum(tx.magnitude for tx in rows if tx.type == "income")
        expenses = sum(tx.magnitude for tx in rows if tx.type == "expense")
        kpis = [(_("Entrate"), money(income)), (_("Uscite"), money(expenses)),
                (_("Netto"), money(income - expenses))]
    data = pdf_report.build_filtered(f"Report — {tab}", subtitle, kpis, items, rows)
    name = f"report_{filters['tab']}_{filters['start']:%Y-%m-%d}_{filters['last_day']:%Y-%m-%d}.pdf"
    return download(data, name, "application/pdf")


def accounts_name(account: str) -> str:
    if account == "none":
        return _("senza conto")
    found = db.session.get(Account, int(account)) if account.isdigit() else None
    return found.name if found else ""


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
