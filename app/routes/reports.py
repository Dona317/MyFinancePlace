from datetime import date, timedelta

from flask import Blueprint, Response, render_template, request

from app.services import accounts, categories, reports, transfer
from app.services.analytics import UNCATEGORIZED

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
