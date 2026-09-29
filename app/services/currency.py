"""
Several currencies: every transaction keeps its original amount and currency, and gets `amount_base`,
its value in the base currency (Settings → Visualizzazione, euro by default) on its date. Totals, reports
and forecasts add up `amount_base`, so a spending in USD is no longer summed as if it were in euro.

Rates are stored against the euro: 1 unit of the currency = `rate` EUR, on a date; the rate of a date is
the latest one on or before it (else the first one after). Another base currency is converted through the
euro. Without any rate for a currency, its amounts count 1:1 and the Currencies page says so.
"""
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal

from sqlalchemy import event, select, text

from app.extensions import db
from app.models.currency import ExchangeRate
from app.models.transaction import Transaction

BASE = "EUR"  # the currency the rates are expressed in
CURRENCIES = {  # code: (symbol, name)
    "EUR": ("€", "Euro"), "USD": ("$", "Dollaro USA"), "GBP": ("£", "Sterlina"), "CHF": ("CHF", "Franco svizzero"),
    "JPY": ("¥", "Yen"), "CAD": ("C$", "Dollaro canadese"), "AUD": ("A$", "Dollaro australiano"),
    "SEK": ("kr", "Corona svedese"), "NOK": ("kr", "Corona norvegese"), "DKK": ("kr", "Corona danese"),
    "PLN": ("zł", "Złoty"), "CZK": ("Kč", "Corona ceca"), "HUF": ("Ft", "Fiorino"), "RON": ("lei", "Leu"),
    "CNY": ("¥", "Renminbi"), "TRY": ("₺", "Lira turca"), "BRL": ("R$", "Real"), "INR": ("₹", "Rupia"),
}
ECB_DAILY = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
ECB_90_DAYS = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"


def symbol(code: str | None) -> str:
    return CURRENCIES.get(code or BASE, (code or BASE, ""))[0]


def base(connection=None) -> str:
    """The currency totals are shown in (Settings → Visualizzazione → Valuta)."""
    if connection is None:
        from app.routes.settings import current_settings  # settings live with their page

        code = current_settings().get("currency")
    else:  # inside a flush: read the saved preferences with the same connection
        raw = connection.execute(text("SELECT value FROM app_settings WHERE key = 'ui.settings'")).scalar()
        try:
            code = json.loads(raw).get("currency") if raw else None
        except (ValueError, AttributeError):
            code = None
    return code if code in CURRENCIES else BASE


# ── Rates ──────────────────────────────────────────────────────────────────────

_RATE_SQL = text("""
    SELECT rate FROM (
        (SELECT rate, 0 AS pref, "on" FROM exchange_rates WHERE currency = :c AND "on" <= :d ORDER BY "on" DESC LIMIT 1)
        UNION ALL
        (SELECT rate, 1 AS pref, "on" FROM exchange_rates WHERE currency = :c AND "on" > :d ORDER BY "on" LIMIT 1)
    ) AS candidates ORDER BY pref LIMIT 1
""")


def rate_on(currency: str | None, on: date, connection=None) -> Decimal | None:
    """Value in euro of one unit of `currency` on a date; None when no rate is known."""
    if not currency or currency == BASE:
        return Decimal(1)
    runner = connection or db.session
    value = runner.execute(_RATE_SQL, {"c": currency, "d": on}).scalar()
    return Decimal(value) if value is not None else None


def to_base(amount, currency: str | None, on: date, connection=None, target: str | None = None) -> Decimal:
    """`amount` in `currency` expressed in the base currency (or `target`), through the euro."""
    target = target or base(connection)
    currency = currency or BASE
    if currency == target:
        return Decimal(amount or 0).quantize(Decimal("0.01"))
    in_euro = Decimal(amount or 0) * (rate_on(currency, on, connection) or Decimal(1))
    return (in_euro / (rate_on(target, on, connection) or Decimal(1))).quantize(Decimal("0.01"))


@event.listens_for(Transaction, "before_insert")
@event.listens_for(Transaction, "before_update")
def _fill_amount_base(mapper, connection, tx: Transaction) -> None:
    if tx.amount is None or tx.date is None:
        return
    tx.amount_base = to_base(abs(Decimal(tx.amount)), tx.currency, tx.date, connection)


def recompute(currency: str | None = None) -> int:
    """
    Refresh amount_base after rates or the base currency changed: the transactions in `currency`, or
    (without it) every transaction not in the base currency. Returns how many were updated.
    """
    target = base()
    query = Transaction.query
    if currency and currency != target and target == BASE:
        query = query.filter(Transaction.currency == currency)
    rows = query.all()
    for tx in rows:
        tx.amount_base = to_base(abs(Decimal(tx.amount)), tx.currency, tx.date, target=target)
    db.session.commit()
    return len([tx for tx in rows if (tx.currency or BASE) != target])


def save_rate(currency: str, on: date, rate: Decimal, source: str = "manual") -> ExchangeRate:
    if currency not in CURRENCIES or currency == BASE:
        raise ValueError("Valuta: scegline una diversa dall'euro.")
    if rate is None or rate <= 0:
        raise ValueError("Cambio: deve essere maggiore di zero.")
    row = ExchangeRate.query.filter_by(currency=currency, on=on).first()
    if row is None:
        row = ExchangeRate(currency=currency, on=on, rate=rate, source=source)
        db.session.add(row)
    else:
        row.rate, row.source = rate, source
    db.session.commit()
    return row


# ── ECB reference rates (optional, needs internet) ─────────────────────────────

def parse_ecb(xml_bytes: bytes) -> list[tuple[date, str, Decimal]]:
    """(date, currency, value of 1 unit in EUR) from an ECB eurofxref XML (which gives units per 1 EUR)."""
    root = ET.fromstring(xml_bytes)
    rates = []
    for day in root.iter():
        when = day.attrib.get("time")
        if not when:
            continue
        for cube in day:
            code, per_euro = cube.attrib.get("currency"), cube.attrib.get("rate")
            if code in CURRENCIES and per_euro and Decimal(per_euro) > 0:
                rates.append((date.fromisoformat(when), code, (Decimal(1) / Decimal(per_euro)).quantize(Decimal("0.00000001"))))
    return rates


def download_ecb(history: bool = True, timeout: int = 20) -> int:
    """Store the ECB rates (last 90 days, or today's). Raises OSError/ValueError when it can't be read."""
    with urllib.request.urlopen(ECB_90_DAYS if history else ECB_DAILY, timeout=timeout) as response:  # noqa: S310 - fixed https URL
        rates = parse_ecb(response.read())
    if not rates:
        raise ValueError("nessun cambio nel file della BCE")
    existing = {(r.currency, r.on): r for r in ExchangeRate.query.filter(
        ExchangeRate.on >= min(d for d, _, _ in rates)).all()}
    for on, code, rate in rates:
        row = existing.get((code, on))
        if row is None:
            db.session.add(ExchangeRate(currency=code, on=on, rate=rate, source="ecb"))
        elif row.source == "ecb":
            row.rate = rate
    db.session.commit()
    recompute()
    return len(rates)


# ── For the Currencies page ────────────────────────────────────────────────────

def foreign_usage() -> list[dict]:
    """Currencies used by transactions other than the euro, with how many transactions and whether rates exist."""
    rows = db.session.execute(select(Transaction.currency, db.func.count()).where(
        Transaction.currency.isnot(None), Transaction.currency != BASE).group_by(Transaction.currency)).all()
    with_rates = {c for (c,) in db.session.query(ExchangeRate.currency).distinct()}
    return [{"currency": c, "count": n, "has_rates": c in with_rates} for c, n in sorted(rows)]
