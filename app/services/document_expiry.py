"""
Warranties and documents that expire (F23): the receipt of the washing machine is covered for two years from the
purchase, the identity card, the driving licence and the passport have a date. A reminder comes 30 days before a
warranty ends and 60 days before a document expires; both are in the deadlines calendar.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.models.wealth import Document
from app.services import periods

WARRANTY_YEARS = 2       # the legal warranty for a consumer in the EU
WARRANTY_NOTICE = 30     # days before
DOCUMENT_NOTICE = 60
EXPIRING_MONTHS = 6      # the «In scadenza» page looks this far ahead


def suggested_warranty(document: Document) -> date | None:
    """Two years from the purchase: the date of the linked movement (the receipt)."""
    if document.transaction is None:
        return None
    return periods.add_months(document.transaction.date, 12 * WARRANTY_YEARS)


def warranties(today: date | None = None) -> list[Document]:
    """Warranties still running, the closest to its end first."""
    today = today or date.today()
    return Document.query.filter(Document.warranty_until >= today).order_by(Document.warranty_until).all()


def expiring(today: date | None = None, months: int = EXPIRING_MONTHS) -> list[Document]:
    """Documents expiring within `months` (or already expired), the soonest first."""
    today = today or date.today()
    until = periods.add_months(today, months)
    return Document.query.filter(Document.expires_on <= until).order_by(Document.expires_on).all()


def label(document: Document) -> str:
    return document.subject or document.filename


def reminders(today: date | None = None) -> list[tuple[Document, str, date]]:
    """(document, «warranty» | «expiry», day) for what needs a word now."""
    today = today or date.today()
    found = [(d, "warranty", d.warranty_until) for d in warranties(today)
             if d.warranty_until <= today + timedelta(days=WARRANTY_NOTICE)]
    found += [(d, "expiry", d.expires_on) for d in Document.query.filter(Document.expires_on.isnot(None))
              if d.expires_on <= today + timedelta(days=DOCUMENT_NOTICE)]
    return sorted(found, key=lambda item: item[2])
