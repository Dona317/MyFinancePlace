"""Calendar helpers shared by the reports and the forecast: months as [start, end) ranges and as indexes."""
import calendar
from datetime import date

from app.services.i18n import N_, tr

MONTH_LABELS = [N_("Gen"), N_("Feb"), N_("Mar"), N_("Apr"), N_("Mag"), N_("Giu"),
                N_("Lug"), N_("Ago"), N_("Set"), N_("Ott"), N_("Nov"), N_("Dic")]  # Italian, see month_labels()


def month_labels() -> list[str]:
    """Short month names in the interface language."""
    return [tr(name) for name in MONTH_LABELS]


def year_bounds(year: int) -> tuple[date, date]:
    """Return [1 January, 1 January of the next year)."""
    return date(year, 1, 1), date(year + 1, 1, 1)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Return [first day of month, first day of next month)."""
    return date(year, month, 1), month_start(month_index(date(year, month, 1)) + 1)


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def month_index(d: date) -> int:
    """Months since year 0: consecutive months have consecutive indexes."""
    return d.year * 12 + d.month - 1


def month_start(index: int) -> date:
    return date(index // 12, index % 12 + 1, 1)


def month_label(index: int) -> str:
    """ "Set 26" """
    return f"{tr(MONTH_LABELS[index % 12])} {str(index // 12)[2:]}"


def add_months(d: date, months: int) -> date:
    """Same day `months` later, clamped to the month's length (31 January + 1 → 28/29 February)."""
    y, m = shift_month(d.year, d.month, months)
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))
