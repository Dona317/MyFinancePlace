"""
Utility bills and consumption (F23): each bill with the period it covers, how much was used (kWh, Smc, m³) and what
it cost. From them: the cost per month and per unit over time, the use by season against the year before, and what
the last twelve months would have cost with another offer.

Bills are proposed from the expenses in the Bollette subcategories (only the consumption is left to write), and a
PDF or photo in Documents can be read by the configured AI model, the result shown to confirm.
"""
from __future__ import annotations

import base64
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from flask_babel import gettext as _

from app.extensions import db
from app.models.transaction import Transaction
from app.models.utility import UtilityReading
from app.services import ai_extraction, document_store, money, periods
from app.services.i18n import N_
from app.services.statement_readers import is_image, is_pdf


@dataclass(frozen=True)
class Utility:
    key: str
    label: str
    unit: str | None        # None: a flat fee (internet, waste), no consumption to write
    icon: str
    category: str | None    # the Bollette subcategory its expenses go to


UTILITIES = {u.key: u for u in (
    Utility("power", N_("Luce"), "kWh", "lightning-charge", "Luce"),
    Utility("gas", N_("Gas"), "Smc", "fire", "Gas"),
    Utility("water", N_("Acqua"), "m³", "droplet", "Acqua"),
    Utility("internet", N_("Internet e telefono"), None, "wifi", "Internet e telefono"),
    Utility("waste", N_("Rifiuti (TARI)"), None, "recycle", None),
)}
SEASONS = ((N_("Inverno"), (1, 2, 12)), (N_("Primavera"), (3, 4, 5)), (N_("Estate"), (6, 7, 8)), (N_("Autunno"), (9, 10, 11)))
DAYS_PER_MONTH = Decimal("30.44")
DEFAULT_PERIOD_MONTHS = 2  # a bill usually covers two months


# ── Saving ─────────────────────────────────────────────────────────────────────

def save(reading: UtilityReading | None, *, utility: str, start: date | None, end: date | None, amount: Decimal | None,
         consumption: Decimal | None = None, supplier: str | None = None, notes: str | None = None,
         transaction: Transaction | None = None, document_id: int | None = None) -> UtilityReading:
    if utility not in UTILITIES:
        raise ValueError(_("Scegli l'utenza."))
    if start is None or end is None:
        raise ValueError(_("Scrivi il periodo della bolletta (dal, al)."))
    if end < start:
        raise ValueError(_("Il periodo finisce prima di cominciare."))
    if amount is None or amount <= 0:
        raise ValueError(_("L'importo deve essere positivo."))
    if consumption is not None and consumption < 0:
        raise ValueError(_("Il consumo non può essere negativo."))
    reading = reading or UtilityReading()
    reading.utility, reading.period_start, reading.period_end = utility, start, end
    reading.amount, reading.consumption = money.cents(amount), consumption
    reading.supplier = " ".join((supplier or "").split())[:120] or None
    reading.notes = (notes or "").strip() or None
    if transaction is not None:
        reading.transaction_id = transaction.id
    if document_id is not None:
        reading.document_id = document_id
    db.session.add(reading)
    return reading


def readings(utility: str | None = None) -> list[UtilityReading]:
    query = UtilityReading.query
    if utility:
        query = query.filter_by(utility=utility)
    return query.order_by(UtilityReading.period_end, UtilityReading.id).all()


def days(reading: UtilityReading) -> int:
    return (reading.period_end - reading.period_start).days + 1


def unit_cost(reading: UtilityReading) -> Decimal | None:
    """€ per kWh, Smc or m³ (everything in the bill: energy, transport, taxes, fixed fees)."""
    if not reading.consumption:
        return None
    return (Decimal(reading.amount) / Decimal(reading.consumption)).quantize(Decimal("0.0001"))


def monthly_cost(reading: UtilityReading) -> Decimal:
    return money.cents(Decimal(reading.amount) / days(reading) * DAYS_PER_MONTH)


# ── From the movements ─────────────────────────────────────────────────────────

def utility_of_category(category: str | None) -> str | None:
    return next((u.key for u in UTILITIES.values() if u.category and u.category == category), None)


def candidates(since_days: int = 730) -> list[tuple[Transaction, str, date]]:
    """Bill expenses not recorded yet: (movement, utility, proposed start of the period)."""
    linked = {tx_id for (tx_id,) in db.session.query(UtilityReading.transaction_id).filter(
        UtilityReading.transaction_id.isnot(None))}
    names = [u.category for u in UTILITIES.values() if u.category]
    rows = (Transaction.query.filter(Transaction.type == "expense", Transaction.category.in_(names),
                                     Transaction.date >= date.today() - timedelta(days=since_days))
            .order_by(Transaction.date.desc()).all())
    return [(tx, utility_of_category(tx.category), proposed_start(utility_of_category(tx.category), tx.date))
            for tx in rows if tx.id not in linked]


def proposed_start(utility: str, end: date) -> date:
    """The day after the previous bill, or two months before."""
    previous = (UtilityReading.query.filter(UtilityReading.utility == utility, UtilityReading.period_end < end)
                .order_by(UtilityReading.period_end.desc()).first())
    return previous.period_end + timedelta(days=1) if previous else periods.add_months(end, -DEFAULT_PERIOD_MONTHS)


# ── Over time ──────────────────────────────────────────────────────────────────

def by_month(utility: str) -> dict[tuple[int, int], dict[str, Decimal]]:
    """Each bill spread day by day over the months it covers: {(year, month): {"cost", "use"}}."""
    found: dict[tuple[int, int], dict[str, Decimal]] = defaultdict(lambda: {"cost": Decimal(0), "use": Decimal(0)})
    for reading in readings(utility):
        span = Decimal(days(reading))
        day = reading.period_start
        while day <= reading.period_end:
            month_end = periods.add_months(periods.first_of_month(day), 1) - timedelta(days=1)
            share = Decimal((min(month_end, reading.period_end) - day).days + 1) / span
            slot = found[(day.year, day.month)]
            slot["cost"] += Decimal(reading.amount) * share
            slot["use"] += Decimal(reading.consumption or 0) * share
            day = month_end + timedelta(days=1)
    return dict(found)


def last_months(utility: str, today: date | None = None, months: int = 12) -> list[tuple[date, Decimal, Decimal]]:
    """(month, cost, use) for the last `months` complete months with a bill."""
    today = today or date.today()
    data = by_month(utility)
    first = periods.add_months(periods.first_of_month(today), -months)
    return [(m, money.cents(data[(m.year, m.month)]["cost"]), data[(m.year, m.month)]["use"].quantize(Decimal("0.1")))
            for m in (periods.add_months(first, i) for i in range(months)) if (m.year, m.month) in data]


@dataclass
class Summary:
    utility: Utility
    count: int
    year_cost: Decimal          # the last 12 months
    year_use: Decimal
    monthly: Decimal
    unit_cost: Decimal | None   # over the last 12 months
    last: UtilityReading | None


def summary(utility: str, today: date | None = None) -> Summary:
    rows = last_months(utility, today)
    cost = sum((c for _, c, _ in rows), Decimal(0))
    use = sum((u for _, _, u in rows), Decimal(0))
    found = readings(utility)
    return Summary(UTILITIES[utility], len(found), cost, use, money.cents(cost / len(rows)) if rows else Decimal(0),
                   (cost / use).quantize(Decimal("0.0001")) if use else None, found[-1] if found else None)


def seasons(utility: str, today: date | None = None) -> list[dict]:
    """Use and cost by season, this year against the one before (a season is counted in the calendar year)."""
    today = today or date.today()
    data = by_month(utility)
    rows = []
    for name, months in SEASONS:
        values = {}
        for year in (today.year - 1, today.year):
            slots = [data[(year, m)] for m in months if (year, m) in data]
            values[year] = ({"use": sum((s["use"] for s in slots), Decimal(0)).quantize(Decimal("0.1")),
                             "cost": money.cents(sum((s["cost"] for s in slots), Decimal(0)))} if slots else None)
        before, now = values[today.year - 1], values[today.year]
        change = (round(float((now["use"] - before["use"]) / before["use"] * 100), 1)
                  if before and now and before["use"] else None)
        rows.append({"season": name, "before": before, "now": now, "change": change})
    return rows


def chart(utility: str) -> dict:
    found = readings(utility)
    return {"labels": [f"{r.period_end:%m/%y}" for r in found],
            "unit": [float(unit_cost(r)) if unit_cost(r) is not None else None for r in found],
            "monthly": [float(monthly_cost(r)) for r in found]}


def with_offer(utility: str, unit_price: Decimal | None, fixed_monthly: Decimal | None,
               today: date | None = None) -> dict | None:
    """What the last twelve months would have cost with another price per unit and fixed monthly fee."""
    if unit_price is None or unit_price < 0 or (fixed_monthly is not None and fixed_monthly < 0):
        raise ValueError(_("Scrivi il prezzo per unità (e la quota fissa al mese) dell'altra offerta."))
    rows = last_months(utility, today)
    if not rows:
        return None
    actual = sum((c for _, c, _ in rows), Decimal(0))
    other = money.cents(sum((u * unit_price + (fixed_monthly or 0) for _, _, u in rows), Decimal(0)))
    return {"months": len(rows), "actual": actual, "other": other, "difference": other - actual}


# ── Reading a bill with the AI model ───────────────────────────────────────────

BILL_SCHEMA = {
    "type": "object",
    "properties": {
        "utility": {"type": "string", "enum": list(UTILITIES)},
        "supplier": {"type": "string"},
        "period_start": {"type": "string", "description": "YYYY-MM-DD"},
        "period_end": {"type": "string", "description": "YYYY-MM-DD"},
        "consumption": {"type": ["number", "null"]},
        "amount": {"type": "number"},
    },
    "required": ["utility", "supplier", "period_start", "period_end", "consumption", "amount"],
    "additionalProperties": False,
}
BILL_PROMPT = ("Questa è una bolletta italiana. Rispondi con l'utenza (power = luce, gas, water = acqua, internet, "
               "waste = rifiuti), il fornitore, il periodo di fatturazione (date ISO), il consumo fatturato nel periodo "
               "(kWh per la luce, Smc per il gas, m³ per l'acqua; null se non c'è) e il totale da pagare in euro.")
BILL_SYSTEM = "Leggi documenti italiani con precisione. Usa solo i dati scritti nel documento."


def read_bill(document) -> dict:
    """The fields of a bill in Documents, read by the configured model; the user checks them before saving."""
    provider = ai_extraction.provider()
    if provider is None:
        raise ValueError(_("La lettura con intelligenza artificiale non è attiva: scrivi i dati a mano."))
    raw = document_store.read(document.stored_name)
    if not raw or not (is_pdf(raw) or is_image(raw)):
        raise ValueError(_("Si leggono solo bollette in PDF o in foto."))
    model = ai_extraction.model_name()
    if provider == "anthropic":
        if is_pdf(raw):
            first = ai_extraction.split_pdf(raw, 6)[0]
            part = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                    "data": base64.standard_b64encode(first).decode()}}
        else:
            data, media_type = ai_extraction._normalize_image(raw)
            part = {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                                 "data": base64.standard_b64encode(data).decode()}}
        payload = ai_extraction.anthropic_json(model, BILL_SYSTEM, [part, {"type": "text", "text": BILL_PROMPT}],
                                               BILL_SCHEMA, max_tokens=2000)
    else:
        pages = ai_extraction._pdf_page_images(raw)[:2] if is_pdf(raw) else [ai_extraction._normalize_image(raw)[0]]
        payload = ai_extraction.ollama_json(model, BILL_SYSTEM, BILL_PROMPT, BILL_SCHEMA, pages)
    try:
        found = json.loads(payload or "")
        return {"utility": found["utility"] if found.get("utility") in UTILITIES else "",
                "supplier": str(found.get("supplier") or ""), "start": date.fromisoformat(found["period_start"]),
                "end": date.fromisoformat(found["period_end"]),
                "consumption": Decimal(str(found["consumption"])) if found.get("consumption") is not None else None,
                "amount": Decimal(str(found["amount"]))}
    except (ValueError, KeyError, TypeError, ArithmeticError):
        raise ValueError(_("Il modello non ha letto la bolletta: scrivi i dati a mano.")) from None
