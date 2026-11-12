"""
Payment cards (F41): debit, credit and prepaid cards charged on an account, with the details that make them clear
(circuit, last four digits, expiry, holder, limit, the day a credit card's month is charged) and the movements each
one paid.

The full number is kept only encrypted (services.field_crypto, AES-256-GCM): the list and the pages show «•••• 4821»,
the whole number appears only when asked for, on the card's page. Never kept: the CVV and the PIN.

A movement gets its card from the form, or — imported from a statement — from its bank text: «CARTA *4821»,
«carta n. ****4821», «PAGAMENTO POS ... 4821» match the active card of that account ending in 4821.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from flask_babel import gettext as _
from sqlalchemy import func

from app.extensions import db
from app.models.account import Account
from app.models.card import Card
from app.models.transaction import Transaction
from app.services import field_crypto, periods
from app.services.i18n import _l

KINDS = {"debit": _l("Carta di debito"), "credit": _l("Carta di credito"), "prepaid": _l("Carta prepagata")}
NETWORKS = {"visa": "Visa", "mastercard": "Mastercard", "maestro": "Maestro", "amex": "American Express",
            "bancomat": "Bancomat / PagoBANCOMAT", "other": _l("Altro")}
ICONS = {"debit": "credit-card", "credit": "credit-card-2-front", "prepaid": "wallet2"}
EXPIRY_WARNING_DAYS = 60
# the last four digits in a bank's text, after a word that says «card» or after masking stars / x
_IN_TEXT = re.compile(r"(?:cart[ae]|card|carta n\.?|pan)\D{0,12}?(?:[*x•]+\s*)?(\d{4})\b|[*x•]{3,}\s*(\d{4})\b", re.I)


class CardError(ValueError):
    """The card cannot be saved as it is; the message is shown to the user."""


@dataclass
class CardInput:
    name: str
    kind: str
    network: str | None
    number: str | None          # what was typed: only the last four digits are kept
    expiry: str | None          # «MM/AA», «MM/AAAA» or «AAAA-MM»
    holder: str | None
    account_id: int | None
    credit_limit: Decimal | None
    statement_day: int | None
    contactless: bool
    notes: str | None
    active: bool = True
    forget_number: bool = False   # remove the saved full number


def last_four(number: str | None) -> tuple[str | None, bool]:
    """The last four digits of what was typed, and whether the whole number was typed (12 to 19 digits)."""
    digits = re.sub(r"\D", "", number or "")
    if not digits:
        return None, False
    if len(digits) < 4:
        raise CardError(_("Scrivi le ultime 4 cifre della carta."))
    if len(digits) > 4 and not 12 <= len(digits) <= 19:
        raise CardError(_("Il numero della carta ha da 12 a 19 cifre: scrivilo intero o solo le ultime 4."))
    return digits[-4:], len(digits) > 4


def full_number(card: Card) -> str | None:
    """The whole number, decrypted and grouped by four; None when not saved. Raises field_crypto.Unreadable when it
    was saved with another key (a backup restored on another computer)."""
    digits = field_crypto.decrypt(card.number_enc)
    return " ".join(digits[i:i + 4] for i in range(0, len(digits), 4)) if digits else None


def parse_expiry(text: str | None) -> tuple[int | None, int | None]:
    text = (text or "").strip()
    if not text:
        return None, None
    found = re.fullmatch(r"(\d{1,2})\s*[/.-]\s*(\d{2}|\d{4})", text) or None
    if found:
        month, year = int(found.group(1)), int(found.group(2))
    else:
        found = re.fullmatch(r"(\d{4})-(\d{1,2})", text)
        if not found:
            raise CardError(_("Scadenza non valida: scrivila come MM/AA."))
        year, month = int(found.group(1)), int(found.group(2))
    year = year + 2000 if year < 100 else year
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise CardError(_("Scadenza non valida: scrivila come MM/AA."))
    return month, year


def save(card: Card | None, data: CardInput) -> tuple[Card, bool]:
    """Create or change a card; True when the whole number was typed (and saved encrypted)."""
    name = " ".join((data.name or "").split())[:120]
    if not name:
        raise CardError(_("Dai un nome alla carta (es. «Visa Fineco»)."))
    if data.kind not in KINDS:
        raise CardError(_("Tipo di carta sconosciuto."))
    if data.network and data.network not in NETWORKS:
        raise CardError(_("Circuito sconosciuto."))
    last4, whole = last_four(data.number)
    month, year = parse_expiry(data.expiry)
    if data.statement_day is not None and not 1 <= data.statement_day <= 31:
        raise CardError(_("Il giorno di addebito va da 1 a 31."))
    if data.credit_limit is not None and data.credit_limit < 0:
        raise CardError(_("Il plafond non può essere negativo."))
    account = db.session.get(Account, data.account_id) if data.account_id else None
    card = card or Card()
    card.name, card.kind, card.network = name, data.kind, data.network or None
    if whole:
        card.number_enc = field_crypto.encrypt(re.sub(r"\D", "", data.number))
    elif data.forget_number or last4 != card.last4:
        card.number_enc = None  # removed, or another card's last digits: the old number no longer belongs to it
    card.last4 = last4
    card.expiry_month, card.expiry_year = month, year
    card.holder = (data.holder or "").strip()[:80] or None
    card.account_id = account.id if account else None
    card.credit_limit = data.credit_limit if data.kind != "debit" else None
    card.statement_day = data.statement_day if data.kind == "credit" else None
    card.contactless, card.notes, card.active = data.contactless, (data.notes or "").strip() or None, data.active
    db.session.add(card)
    db.session.flush()
    return card, whole


def delete(card: Card) -> None:
    """The movements stay, without their card."""
    Transaction.query.filter_by(card_id=card.id).update({"card_id": None})
    db.session.delete(card)


# ── Reading them ───────────────────────────────────────────────────────────────

def expiry_date(card: Card) -> date | None:
    """The last day the card works: the end of its expiry month."""
    if not card.expiry_month or not card.expiry_year:
        return None
    return periods.add_months(date(card.expiry_year, card.expiry_month, 1), 1) - timedelta(days=1)


def expires_soon(card: Card, today: date | None = None) -> bool:
    end = expiry_date(card)
    today = today or date.today()
    return end is not None and card.active and end - today <= timedelta(days=EXPIRY_WARNING_DAYS)


def masked(card: Card) -> str:
    return f"•••• {card.last4}" if card.last4 else "••••"


def of_account(account: Account, active_only: bool = False) -> list[Card]:
    query = Card.query.filter_by(account_id=account.id)
    if active_only:
        query = query.filter_by(active=True)
    return query.order_by(Card.active.desc(), Card.name).all()


def every(active_only: bool = True) -> list[Card]:
    query = Card.query.filter_by(active=True) if active_only else Card.query
    return query.order_by(Card.name).all()


def month_spending(card: Card, today: date | None = None) -> Decimal:
    """What the card paid this month (expenses only): for a credit card, what the next charge will be about."""
    start = (today or date.today()).replace(day=1)
    total = (db.session.query(func.coalesce(func.sum(Transaction.amount), 0))
             .filter(Transaction.card_id == card.id, Transaction.type == "expense",
                     Transaction.date >= start, Transaction.date < periods.add_months(start, 1)).scalar())
    return Decimal(total)


def movements_count(card: Card) -> int:
    return Transaction.query.filter_by(card_id=card.id).count()


# ── Recognized in a statement ──────────────────────────────────────────────────

def digits_in(text: str | None) -> set[str]:
    return {a or b for a, b in _IN_TEXT.findall(text or "")}


def match(tx: Transaction, cards: list[Card] | None = None) -> Card | None:
    """The card a movement was paid with, from its bank text: an active card ending with the digits the text names,
    preferring one of the movement's account."""
    found = digits_in(" ".join(filter(None, (tx.bank_description, tx.description, tx.notes))))
    if not found:
        return None
    cards = every() if cards is None else cards
    candidates = [c for c in cards if c.last4 in found]
    own = [c for c in candidates if c.account_id in (tx.account_id, tx.counter_account_id)]
    chosen = own or candidates
    return chosen[0] if len(chosen) == 1 else None


def assign(transactions: list[Transaction]) -> int:
    """Give the card to movements without one, from their bank text; how many got one."""
    cards = every()
    if not cards:
        return 0
    given = 0
    for tx in transactions:
        if tx.card_id is None:
            card = match(tx, cards)
            if card is not None:
                tx.card_id = card.id
                given += 1
    return given
