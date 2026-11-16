"""
The shared period (decided 15 Nov 2026, F101): one period for the analysis pages — Dashboard, Entrate, Uscite,
Transazioni, Report and Budget. Chosen on any of them it holds on all the others, and it is kept for the signed-in
user (the archive's settings, one key per user), so the app reopens on the last one used. A link that carries a
period opens it and makes it the shared one: links stay exact and the period never changes behind the user's back.

A period is a year, or several years whole, or a part of a single year (a half, a quarter, a month), or the last
twelve months up to the current one. The yearly statements (Panoramica Finanziaria, Fisco), the portfolio (market
ranges) and the pages that look ahead (Previsioni, Ricorrenti) keep periods of their own.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit

from flask import flash, has_request_context, request
from flask_babel import gettext as _

from app.services import settings_store
from app.services.periods import month_labels, shift_month

HALVES = ("H1", "H2")
QUARTERS = ("Q1", "Q2", "Q3", "Q4")
MONTHS = tuple(f"M{m:02d}" for m in range(1, 13))
LAST_12 = "last12"
PARTS = ("year", *HALVES, *QUARTERS, *MONTHS, LAST_12)
SETTING = "period.shared.{user}"
# what an address says about the period (dropped when a page keeps its own parameters for the period box)
ADDRESS_KEYS = ("year", "year_to", "part", "period", "start", "end", "page")


@dataclass(frozen=True)
class Period:
    year: int
    year_to: int
    part: str = "year"

    def bounds(self, today: date | None = None) -> tuple[date, date]:
        """[first day, the day after the last)."""
        today = today or date.today()
        if self.part == LAST_12:
            start = date(*shift_month(today.year, today.month, -11), 1)
            return start, date(*shift_month(today.year, today.month, 1), 1)
        if self.year != self.year_to or self.part == "year":
            return date(self.year, 1, 1), date(self.year_to + 1, 1, 1)
        if self.part in MONTHS:
            month = int(self.part[1:])
            return date(self.year, month, 1), date(*shift_month(self.year, month, 1), 1)
        first = 1 if self.part == "H1" else 7 if self.part == "H2" else (int(self.part[1]) - 1) * 3 + 1
        length = 6 if self.part in HALVES else 3
        return date(self.year, first, 1), date(*shift_month(self.year, first, length), 1)

    def label(self) -> str:
        """Short name: «2026», «2024–2026», «1H26», «2Q26 (Apr–Giu)», «Mar 2026», «Ultimi 12 mesi»."""
        if self.part == LAST_12:
            return _("Ultimi 12 mesi")
        if self.year != self.year_to:
            return f"{self.year}–{self.year_to}"
        if self.part == "year":
            return str(self.year)
        names = month_labels()
        if self.part in MONTHS:
            return f"{names[int(self.part[1:]) - 1]} {self.year}"
        number, kind = self.part[1], self.part[0]
        if kind == "H":
            return f"{number}H{self.year % 100:02d}"
        first = (int(number) - 1) * 3
        return f"{number}Q{self.year % 100:02d} ({names[first]}–{names[first + 2]})"

    def args(self) -> dict:
        """The period as the address carries it."""
        return {"year": self.year, "year_to": self.year_to, "part": self.part}

    def as_dict(self) -> dict:
        return self.args()


def default(today: date | None = None) -> Period:
    year = (today or date.today()).year
    return Period(year, year)


def clean(year, year_to=None, part=None, today: date | None = None) -> Period | None:
    """A period from loose values (the address, the saved setting, a preset); None when the years are not years."""
    if part == LAST_12:
        today = today or date.today()
        return Period(today.year, today.year, LAST_12)
    try:
        year = int(year)
        year_to = int(year_to) if year_to not in (None, "") else year
    except (TypeError, ValueError):
        return None
    if not (1900 < year < 3000 and 1900 < year_to < 3000):
        return None
    year, year_to = min(year, year_to), max(year, year_to)
    part = part if part in PARTS and part != LAST_12 and year == year_to else "year"
    return Period(year, year_to, part)


def _from_legacy(args, today: date) -> Period | None:
    """The old addresses of Entrate, Uscite and Report (period=this_month, custom with start and end)."""
    key = args.get("period")
    if key == "this_month":
        return Period(today.year, today.year, f"M{today.month:02d}")
    if key == "last_month":
        year, month = shift_month(today.year, today.month, -1)
        return Period(year, year, f"M{month:02d}")
    if key in ("last_3", "last_6", "last_12"):
        return Period(today.year, today.year, LAST_12)
    if key == "this_year":
        return default(today)
    if key == "last_year":
        return Period(today.year - 1, today.year - 1)
    if key == "custom":
        try:
            start, end = date.fromisoformat(args.get("start", "")), date.fromisoformat(args.get("end", ""))
        except ValueError:
            return None
        return _closest(start, end)
    return None


def _closest(start: date, end: date) -> Period:
    """The period that matches the dates (end included): a part of a year, or the years they span."""
    if start.year == end.year:
        for part in PARTS[1:-1]:
            candidate = Period(start.year, start.year, part)
            first, after = candidate.bounds()
            if first == start and (after - end).days == 1:
                return candidate
    return Period(start.year, end.year)


def _key() -> str:
    return settings_store.user_key(SETTING)


def saved(today: date | None = None) -> Period:
    stored = settings_store.get_json(_key(), None, expect=dict)
    found = clean(stored.get("year"), stored.get("year_to"), stored.get("part"), today) if stored else None
    return found or default(today)


def save(period: Period) -> Period:
    settings_store.set_json(_key(), period.as_dict())
    return period


def current(today: date | None = None, args=None) -> Period:
    """The shared period: the one the address carries (it becomes the shared one), else the saved one."""
    today = today or date.today()
    args = request.args if args is None else args
    found = None
    if args.get("part") == LAST_12 or args.get("year"):
        found = clean(args.get("year"), args.get("year_to"), args.get("part"), today)
    elif args.get("part"):  # back from «Ultimi 12 mesi»: the years were switched off, the saved ones hold
        before = saved(today)
        year = before.year if before.part != LAST_12 else today.year
        found = clean(year, year if before.part == LAST_12 else before.year_to, args.get("part"), today)
    elif args.get("period"):
        found = _from_legacy(args, today)
    if found is not None:
        return _share(found, today)
    return saved(today)


def _share(found: Period, today: date) -> Period:
    """The period the address carries becomes the shared one. When it changes arriving from another page (a month
    clicked on a chart, a link kept among the bookmarks) a short notice says so: the change is no longer silent. The
    box on top of the page itself needs none — the page is asked again from itself."""
    if found != saved(today):
        save(found)
        if has_request_context() and urlsplit(request.referrer or "").path != request.path:
            flash(_("Periodo: %(label)s", label=found.label()), "info")
    return found


def from_register(args, today: date | None = None) -> Period:
    """The register's period: a link with a month (month=2025-03) or with dates (start, end) opens that period and
    makes it the shared one — a link from a chart stays exact; otherwise the shared period."""
    today = today or date.today()
    month = args.get("month", "")
    found = None
    if len(month) == 7 and month[4] == "-" and month[:4].isdigit() and month[5:].isdigit() and 1 <= int(month[5:]) <= 12:
        found = Period(int(month[:4]), int(month[:4]), f"M{int(month[5:]):02d}")
    elif args.get("start") and args.get("end") and not (args.get("year") or args.get("part")):
        try:
            found = _closest(date.fromisoformat(args["start"]), date.fromisoformat(args["end"]))
        except ValueError:
            found = None
    if found is not None and 1900 < found.year < 3000:
        return _share(found, today)
    return current(today, args)


def month_of(period: Period, today: date | None = None) -> date:
    """The month a monthly page (Budget) shows for the shared period: the month itself, else the current month when
    the period holds it, else the period's last month."""
    today = today or date.today()
    if period.part in MONTHS:
        return date(period.year, int(period.part[1:]), 1)
    start, end = period.bounds(today)
    if start <= today < end:
        return today.replace(day=1)
    year, month = shift_month(end.year, end.month, -1)
    return date(year, month, 1)


def years(with_data: list[int], today: date | None = None) -> list[int]:
    """The years offered: from the next one down to three before the first with data (as on the dashboard)."""
    year = (today or date.today()).year
    return list(range(max(with_data + [year]) + 1, min(with_data + [year]) - 4, -1))


def part_choices(period: Period) -> list[tuple[str, list[tuple[str, str]]]]:
    """The groups of the «part» select: halves, quarters, months of the year chosen."""
    names = month_labels()
    single = Period(period.year, period.year)
    return [
        (_("Semestri"), [(p, Period(single.year, single.year, p).label()) for p in HALVES]),
        (_("Trimestri"), [(p, Period(single.year, single.year, p).label()) for p in QUARTERS]),
        (_("Mesi"), [(p, names[int(p[1:]) - 1]) for p in MONTHS]),
    ]
