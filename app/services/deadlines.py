"""
The deadlines of the household in one calendar (F23): what the app already knows — recurring movements, loan
installments, insurance renewals, PAC instalments, goals with a date, money between people, the deductible room
left in the year — plus the fixed Italian tax dates and the deadlines written by hand. As a month grid, a list of the
weeks ahead, and an .ics file for Google Calendar or Outlook.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from flask import url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.event import SpendingEvent
from app.models.portfolio_model import InvestmentPlan
from app.models.reminder import Reminder
from app.models.transaction import Transaction
from app.models.wealth import Debt, Document, Goal, InsurancePolicy
from app.services import (
    cards,
    contribution_limits,
    document_expiry,
    forecast,
    investment_plans,
    periods,
    personal_loans,
    sections,
    settings_store,
    wealth,
)
from app.services.i18n import N_, tr

FISCAL_SETTING = "deadlines.fiscal"
REPEATS = {"none": N_("Una volta"), "monthly": N_("Ogni mese"), "yearly": N_("Ogni anno")}
# how long before its date a reminder is announced (the bell): days → label
NOTICES = {0: N_("Il giorno stesso"), 1: N_("Il giorno prima"), 3: N_("3 giorni prima"), 7: N_("Una settimana prima"),
           14: N_("Due settimane prima"), 30: N_("Un mese prima")}
DEFAULT_NOTICE = 7
# (month, day, title, note): the usual dates; when one falls on a holiday it moves to the next working day
FISCAL_DATES = (
    (6, 16, N_("IMU: acconto"), N_("Prima rata dell'IMU sulle case diverse dall'abitazione principale")),
    (12, 16, N_("IMU: saldo"), N_("Seconda rata dell'IMU")),
    (6, 30, N_("Saldo IRPEF e primo acconto"), N_("Per chi presenta il modello Redditi o ha imposte da versare con il 730")),
    (9, 30, N_("Invio del 730"), N_("Ultimo giorno per presentare il 730")),
    (11, 30, N_("Secondo acconto IRPEF"), N_("Trattenuto in busta paga con il 730, altrimenti con F24")),
    (10, 31, N_("Invio del modello Redditi"), N_("Per chi non usa il 730; anche bollo e IVAFE dei conti all'estero")),
)


@dataclass
class Deadline:
    day: date
    kind: str            # recurring | installment | policy | plan | goal | loan | limit | fiscal | reminder | document
    title: str
    detail: str = ""
    amount: Decimal | None = None
    outgoing: bool = True
    url: str = ""
    key: str = ""        # stable, for the .ics UID
    # a repeating deadline (a recurring movement, a PAC, a repeating reminder): the series it belongs to and its
    # RFC 5545 rule, so the calendar gets one recurring event instead of a copy of each date
    series: str = ""
    rrule: str = ""

    @property
    def icon(self) -> str:
        return ICONS.get(self.kind, "calendar-event")

    @property
    def google_url(self) -> str:
        """Google Calendar's «new event» page filled with this deadline (an all-day event): opened in the browser,
        where the user is signed in, it only needs «Salva»."""
        summary = self.title + (f" — {self.amount:.2f} €".replace(".", ",") if self.amount else "")
        query = {"action": "TEMPLATE", "text": summary, "details": self.detail or "",
                 "dates": f"{self.day:%Y%m%d}/{self.day + timedelta(days=1):%Y%m%d}"}
        if self.rrule:
            query["recur"] = f"RRULE:{self.rrule}"
        return GOOGLE_NEW_EVENT + urlencode(query)


def rrule(frequency: str, anchor: date, until: date | None = None, day: int | None = None) -> str:
    """The RFC 5545 rule of a series that starts on `anchor`: weekly, monthly, every three months or yearly, on
    `day` of the month (the anchor's when not given). A day past the 28th falls on the last day of the shorter
    months, as the app counts (add_months): 31 → 30 April, 28 or 29 February."""
    day = day or anchor.day
    if frequency == "weekly":
        parts = ["FREQ=WEEKLY"]
    elif frequency == "yearly":
        parts = ["FREQ=YEARLY", f"BYMONTH={anchor.month}"]
        parts += ["BYMONTHDAY=28,29", "BYSETPOS=-1"] if (anchor.month, day) == (2, 29) else [f"BYMONTHDAY={day}"]
    else:
        parts = ["FREQ=MONTHLY"] + (["INTERVAL=3"] if frequency == "quarterly" else [])
        if day > 28:
            parts += ["BYMONTHDAY=" + ",".join(str(d) for d in range(28, day + 1)), "BYSETPOS=-1"]
        else:
            parts.append(f"BYMONTHDAY={day}")
    if until is not None:
        parts.append(f"UNTIL={until:%Y%m%d}")
    return ";".join(parts)


GOOGLE_NEW_EVENT = "https://calendar.google.com/calendar/render?"
GOOGLE_IMPORT = "https://calendar.google.com/calendar/r/settings/export"  # Impostazioni → Importa ed esporta
ICONS = {"recurring": "arrow-repeat", "installment": "credit-card", "policy": "shield-check", "plan": "piggy-bank",
         "goal": "trophy", "loan": "arrow-left-right", "limit": "piggy-bank", "fiscal": "percent",
         "reminder": "calendar-check", "document": "file-earmark-text", "warranty": "shield-check",
         "card": "credit-card"}


def fiscal_on() -> bool:
    return settings_store.get(FISCAL_SETTING) != "0"


def set_fiscal(on: bool) -> None:
    settings_store.set(FISCAL_SETTING, "1" if on else "0")


# ── Hand-written ones ──────────────────────────────────────────────────────────

def save(reminder: Reminder | None, *, title: str, due: date | None, repeat: str, amount: Decimal | None,
         notes: str | None, notice_days: int | None = None) -> Reminder:
    title = " ".join((title or "").split())[:200]
    if not title:
        raise ValueError(_("Scrivi cosa scade."))
    if due is None:
        raise ValueError(_("Scrivi la data."))
    if amount is not None and amount < 0:
        raise ValueError(_("L'importo non può essere negativo."))
    reminder = reminder or Reminder()
    reminder.title, reminder.due, reminder.repeat = title, due, repeat if repeat in REPEATS else "none"
    reminder.amount, reminder.notes = amount, (notes or "").strip() or None
    reminder.notice_days = notice_days if notice_days in NOTICES else DEFAULT_NOTICE
    db.session.add(reminder)
    return reminder


# ── Reminders and spending events, tied both ways (F33) ───────────────────────

def event_from_reminder(reminder: Reminder) -> SpendingEvent | None:
    """A one-off reminder with an amount has its spending event (the name, the day, the amount as its budget): made
    the first time, brought up to date afterwards. A repeating one or one without an amount makes none."""
    event = reminder.event
    if event is None and (reminder.repeat != "none" or not reminder.amount):
        return None
    if event is None:
        event = SpendingEvent()
        db.session.add(event)
        reminder.event = event
    event.name, event.start, event.budget = reminder.title, reminder.due, reminder.amount
    if event.end is not None and event.end < event.start:
        event.end = None
    event.notes = event.notes or reminder.notes
    return event


def reminder_from_event(event: SpendingEvent) -> Reminder:
    """Every spending event has its reminder on its first day (the budget as its amount): made the first time,
    brought up to date afterwards."""
    db.session.flush()
    reminder = Reminder.query.filter_by(event_id=event.id).first()
    if reminder is None:
        reminder = Reminder(repeat="none", notice_days=DEFAULT_NOTICE, event_id=event.id, notes=event.notes)
        db.session.add(reminder)
    reminder.title, reminder.due, reminder.amount = event.name[:200], event.start, event.budget
    return reminder


def occurrences(reminder: Reminder, start: date, end: date) -> list[date]:
    """The dates of a hand-written deadline in [start, end]."""
    if reminder.repeat == "none":
        return [reminder.due] if not reminder.done and start <= reminder.due <= end else []
    step = 1 if reminder.repeat == "monthly" else 12
    found, k = [], 0
    while True:
        day = periods.add_months(reminder.due, step * k)
        if day > end:
            return found
        if day >= start:
            found.append(day)
        k += 1


# ── Every source ───────────────────────────────────────────────────────────────

def _recurring(start: date, end: date) -> list[Deadline]:
    templates = forecast.scheduled_templates(Transaction.query.filter(Transaction.is_recurring.is_(True)).all())
    found = []
    for tx in templates:
        frequency = tx.recurrence if tx.recurrence in forecast.FREQUENCIES else "monthly"
        for day in forecast.occurrences(tx, start, end + timedelta(days=1)):
            found.append(Deadline(day, "recurring", tx.description, amount=Decimal(str(tx.magnitude)),
                                  outgoing=tx.type == "expense", url=url_for("transactions.edit", tx_id=tx.id),
                                  key=f"tx{tx.id}", series=f"tx{tx.id}",
                                  rrule=rrule(frequency, day, tx.recurrence_end, day=tx.date.day)))
    return found


def _installments(start: date, end: date) -> list[Deadline]:
    found = []
    for debt in Debt.query.all():
        for row in wealth.schedule(debt):
            if row.due > end:
                break
            if row.due >= start:
                found.append(Deadline(row.due, "installment", _("Rata %(name)s", name=debt.name),
                                      _("rata %(n)s", n=row.number), Decimal(str(round(row.payment, 2))),
                                      url=url_for("debt.detail", debt_id=debt.id), key=f"debt{debt.id}-{row.number}"))
    return found


def _policies(start: date, end: date) -> list[Deadline]:
    rows = InsurancePolicy.query.filter(InsurancePolicy.expiry_date.between(start, end))
    return [Deadline(p.expiry_date, "policy", _("Polizza %(type)s · %(company)s", type=tr(p.type), company=p.company),
                     _("scadenza o rinnovo"), Decimal(p.premium) if p.premium else None,
                     url=url_for("insurance.edit", policy_id=p.id), key=f"policy{p.id}") for p in rows]


def _plans(start: date, end: date) -> list[Deadline]:
    found = []
    for plan in InvestmentPlan.query.all():
        month = periods.first_of_month(start)
        while month <= end:
            day = investment_plans.due_date(plan, month)
            if (day and start <= day <= end and day >= plan.start and not (plan.end and day > plan.end)):
                found.append(Deadline(day, "plan", _("PAC «%(name)s»", name=plan.name), amount=Decimal(plan.amount),
                                      url=url_for("portfolio.plan_run", plan_id=plan.id), key=f"plan{plan.id}-{day:%Y%m}",
                                      series=f"plan{plan.id}",
                                      rrule=rrule(plan.frequency, day, plan.end, day=plan.day)))
            month = periods.add_months(month, 1)
    return found


def _goals(start: date, end: date) -> list[Deadline]:
    rows = Goal.query.filter(Goal.target_date.between(start, end))
    return [Deadline(g.target_date, "goal", _("Obiettivo «%(name)s»", name=g.name),
                     _("raggiunto") if g.completed else _("ancora da mettere da parte"),
                     None if g.completed else Decimal(str(round(g.remaining, 2))), outgoing=False,
                     url=url_for("lifestyle.goals"), key=f"goal{g.id}") for g in rows]


def _loans(start: date, end: date) -> list[Deadline]:
    found = []
    for person in personal_loans.people():
        if person.balance and person.due and start <= person.due <= end:
            owes_me = person.balance > 0
            found.append(Deadline(person.due, "loan",
                                  _("%(person)s ti restituisce", person=person.name) if owes_me
                                  else _("Restituisci a %(person)s", person=person.name),
                                  amount=abs(person.balance), outgoing=not owes_me, url=url_for("loans.index"),
                                  key=f"loan-{person.name}"))
    return found


def _limits(start: date, end: date) -> list[Deadline]:
    found = []
    for year in range(start.year, end.year + 1):
        last = date(year, 12, 31)
        if not start <= last <= end:
            continue
        for s in contribution_limits.all_standings(year):
            if s.deductible and s.left > 0:
                found.append(Deadline(last, "limit", _("%(name)s: ultimo giorno", name=s.limit.name),
                                      _("ancora deducibili"), s.left, outgoing=False, url=url_for("tax.limits", year=year),
                                      key=f"limit{s.limit.id}-{year}"))
    return found


def _documents(start: date, end: date) -> list[Deadline]:
    """Warranties ending and documents expiring (F23b)."""
    found = []
    for doc in Document.query.filter(Document.warranty_until.between(start, end)):
        found.append(Deadline(doc.warranty_until, "warranty", _("Fine garanzia: %(what)s", what=document_expiry.label(doc)),
                              url=url_for("documents.edit", doc_id=doc.id), key=f"warranty{doc.id}"))
    for doc in Document.query.filter(Document.expires_on.between(start, end)):
        found.append(Deadline(doc.expires_on, "document", _("Scade: %(what)s", what=document_expiry.label(doc)),
                              url=url_for("documents.edit", doc_id=doc.id), key=f"document{doc.id}"))
    return found


def _cards(start: date, end: date) -> list[Deadline]:
    """F41: an active card's last day (the end of its expiry month): time to ask for the new one."""
    found = []
    for card in cards.every():
        last = cards.expiry_date(card)
        if last and start <= last <= end:
            found.append(Deadline(last, "card", _("Scade la carta %(name)s", name=card.name), cards.masked(card),
                                  url=url_for("accounts.card_edit", card_id=card.id), key=f"card{card.id}-{last:%Y%m}"))
    return found


def _fiscal(start: date, end: date) -> list[Deadline]:
    if not fiscal_on():
        return []
    found = []
    for year in range(start.year, end.year + 1):
        for month, day, title, note in FISCAL_DATES:
            on = date(year, month, day)
            if start <= on <= end:
                found.append(Deadline(on, "fiscal", _(title), _(note), key=f"fiscal{month:02d}{day:02d}-{year}"))
    return found


def _reminders(start: date, end: date) -> list[Deadline]:
    found = []
    for r in Reminder.query.order_by(Reminder.due):
        repeating = r.repeat in ("monthly", "yearly")
        for day in occurrences(r, start, end):
            found.append(Deadline(day, "reminder", r.title, r.notes or "",
                                  Decimal(r.amount) if r.amount is not None else None,
                                  url=url_for("deadlines.index", month=f"{day:%Y-%m}") + f"#reminder-{r.id}",
                                  key=f"reminder{r.id}-{day}", series=f"reminder{r.id}" if repeating else "",
                                  rrule=rrule(r.repeat, day, day=r.due.day) if repeating else ""))
    return found


# Each kind of deadline and the section it belongs to: none from a section switched off or blocked for the user
# (as for the reminders); the fiscal dates and the hand-written ones belong to the page itself
SOURCES = [(_recurring, "transactions"), (_installments, "debt"), (_policies, "insurance"), (_plans, "portfolio"),
           (_goals, "goals"), (_loans, "loans"), (_limits, "tax"), (_documents, "documents"), (_cards, "accounts"),
           (_fiscal, None),
           (_reminders, None)]


def between(start: date, end: date) -> list[Deadline]:
    """Every deadline in [start, end], by day."""
    shown = [source for source, section in SOURCES
             if section is None or not (sections.switched_off(section) or sections.blocked(section))]
    return sorted((d for source in shown for d in source(start, end)), key=lambda d: (d.day, d.kind, d.title))


def month_grid(month: date) -> dict:
    """Weeks (Monday first) of a month, each day with its deadlines; the month's total to pay."""
    first = periods.first_of_month(month)
    last = periods.add_months(first, 1) - timedelta(days=1)
    items = between(first, last)
    by_day: dict[date, list[Deadline]] = {}
    for item in items:
        by_day.setdefault(item.day, []).append(item)
    weeks, day = [], first - timedelta(days=first.weekday())
    while day <= last:
        weeks.append([(day if day.month == first.month else None, by_day.get(day, [])) for day in
                      (day + timedelta(days=i) for i in range(7))])
        day += timedelta(days=7)
    to_pay = sum((i.amount for i in items if i.amount and i.outgoing), Decimal(0))
    return {"month": first, "weeks": weeks, "items": items, "to_pay": to_pay,
            "previous": periods.add_months(first, -1), "next": periods.add_months(first, 1)}


# ── Calendar file (RFC 5545) ───────────────────────────────────────────────────

def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """Lines longer than 75 octets go on, indented by one space, on the next ones (RFC 5545 §3.1: the space tells
    the calendar the line goes on; without it the rest would be read as a line of its own)."""
    out, current = [], ""
    for char in line:
        if len((current + char).encode()) > 75:
            out.append(current)
            current = " " + char
        else:
            current += char
    return out + [current]


def ics(start: date, end: date, now: datetime | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%dT%H%M%S")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//MyFinancePlace//Scadenze//IT", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:MyFinancePlace"]
    series = set()
    for item in between(start, end):
        if item.series and item.series in series:
            continue  # a repeating deadline: one event with its rule, from the first date in the window
        summary = item.title + (f" — {item.amount:.2f} €".replace(".", ",") if item.amount else "")
        uid = f"{item.kind}-{item.series}" if item.series else f"{item.kind}-{item.key or item.day}"
        lines += ["BEGIN:VEVENT", f"UID:{uid}@myfinanceplace", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{item.day:%Y%m%d}", f"DTEND;VALUE=DATE:{item.day + timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{_escape(summary)}"]
        if item.series:
            series.add(item.series)
            lines.append(f"RRULE:{item.rrule}")
        if item.detail:
            lines.append(f"DESCRIPTION:{_escape(item.detail)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in _fold(line)) + "\r\n"


def upcoming(today: date | None = None, days: int = 60) -> list[Deadline]:
    today = today or date.today()
    return between(today, today + timedelta(days=days))


def due_reminders(today: date) -> list[tuple[Reminder, date]]:
    """Hand-written deadlines to announce today: each one from as many days before its date as it asks (a week if
    not said), until the day itself."""
    return [(r, day) for r in Reminder.query.order_by(Reminder.due)
            for day in occurrences(r, today, today + timedelta(days=r.notice_days if r.notice_days in NOTICES else DEFAULT_NOTICE))]
