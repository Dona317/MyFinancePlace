"""The transaction form: reading what was typed into a Transaction, and the values the form shows."""
from decimal import Decimal

from flask import request
from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.wealth import Debt, Holding
from app.routes.helpers import form_choice, form_date, form_decimal, form_text
from app.schemas.transaction import RECURRENCES
from app.services import broker, display, money, splits
from app.services import currency as currency_service
from app.services.ai_classification import AI_TAG
from app.services.parsing import to_decimal, valid_amount
from app.services.tags import parse_tags

# ── Reading the form ────────────────────────────────────────────────────────────────────

def tx_from_form(tx: Transaction) -> Transaction:
    """Fill the transaction from the form; a ValueError says which field is wrong (nothing crashes)."""
    tx.date = form_date("date", _("Data"), required=True)
    units, unit_price = _trade_from_form()
    if units is not None and not (request.form.get("amount") or "").strip():  # the amount follows units × price
        gross = money.cents(abs(units) * unit_price)
        amount = -gross if units > 0 else gross
    else:
        amount = form_decimal("amount", _("Importo"), required=True, allow_negative=True)
    if not valid_amount(amount):
        raise ValueError(_("Importo: deve essere diverso da zero."))
    tx.type = type_from(amount)
    tx.amount = abs(amount)
    tx.description = form_text("description", _("Descrizione"), required=True)
    currency = request.form.get("currency") or "EUR"
    tx.currency = currency if currency in currency_service.CURRENCIES else "EUR"
    tx.category = form_text("category", _("Categoria"))
    tx.tags = parse_tags(request.form.get("tags", ""))
    # the counterparty is now the first tag (kept in its own column for rules, search and the AI)
    tx.counterparty = next((t for t in tx.tags if t != AI_TAG), None)
    tx.is_recurring = "is_recurring" in request.form
    # frequency and end date only mean something for a recurring transaction
    if tx.is_recurring:
        tx.recurrence = form_choice("recurrence", _("Frequenza"), RECURRENCES)
        tx.recurrence_end = form_date("recurrence_end", _("Fine ricorrenza"))
        if tx.recurrence_end and tx.recurrence_end < tx.date:
            raise ValueError(_("Fine ricorrenza: non può essere prima della data."))
    else:
        tx.recurrence = tx.recurrence_end = None
    tx.notes = form_text("notes", _("Note"))
    tx.account_id = linked_id("account_id", Account)
    # a transfer between two own accounts: where the money arrives
    tx.counter_account_id = linked_id("counter_account_id", Account) if tx.type == "transfer" else None
    if tx.counter_account_id and tx.counter_account_id == tx.account_id:
        raise ValueError(_("Verso il conto: deve essere diverso dal conto di partenza."))
    # in another currency than the account's: what the bank charged / credited in the account's currency
    tx.account_amount = _bank_amount("account_amount", _("Importo sul conto"), tx.account_id, tx.currency)
    tx.counter_amount = _bank_amount("counter_amount", _("Importo sul conto d'arrivo"), tx.counter_account_id, tx.currency)
    # what the money is for, in the cash-flow statement: an investment or a debt (one of the two)
    tx.holding_id = linked_id("holding_id", Holding)
    tx.debt_id = linked_id("debt_id", Debt) if not tx.holding_id else None
    # units × price only mean something for a trade of a holding
    tx.units, tx.unit_price = (units, unit_price) if tx.holding_id and units is not None else (None, None)
    if tx.units is not None:
        # a trade moves money between the account and the investment: not an expense nor an income (the savings rate
        # stays right); a purchase leaves the account, a sale arrives on it (wealth.cash_balance / accounts.balance)
        tx.type, tx.category = "transfer", tx.category or "Investimenti"
        broker_account = tx.account_id or tx.counter_account_id
        tx.account_id, tx.counter_account_id = (broker_account, None) if tx.units > 0 else (None, broker_account)
        tx.splits = []
    _splits_from_form(tx)
    return tx


def _trade_from_form() -> tuple[Decimal | None, Decimal | None]:
    """Units and price per unit of an investment trade (both or neither); sold units are negative."""
    units = form_decimal("units", _("Quote"))
    price = form_decimal("unit_price", _("Prezzo per quota"))
    if units is None and price is None:
        return None, None
    if units is None or price is None or units <= 0 or price <= 0:
        raise ValueError(_("Operazione: indica quote e prezzo per quota, entrambi maggiori di zero."))
    return (-units if request.form.get("trade_side") == "sell" else units), price


def after_trade(tx: Transaction) -> list[Transaction]:
    """A new trade entered in units: the confirmed commission as its own expense, and the holding moved by it."""
    created = []
    fee = form_decimal("fee_amount", _("Commissione")) if "record_fee" in request.form else None
    if fee:
        account_id = tx.account_id or tx.counter_account_id
        created.append(broker.fee_transaction(tx, fee, db.session.get(Account, account_id) if account_id else None))
        db.session.add(created[-1])
    if tx.holding_id and tx.units is not None and "update_holding" in request.form:
        holding = db.session.get(Holding, tx.holding_id)
        broker.apply_trade(holding, tx.units, tx.unit_price, fee if fee and tx.units > 0 else Decimal(0), tx.date)
    return created


def _split_rows() -> list[tuple[str, str]]:
    """The (category, amount) rows of the «Suddividi» box as typed, empty rows left out."""
    rows = zip(request.form.getlist("split_category"), request.form.getlist("split_amount"))
    return [(c.strip(), a.strip()) for c, a in rows if c.strip() or a.strip()]


def _splits_from_form(tx: Transaction) -> None:
    """The «Suddividi» rows; one row or none: an ordinary transaction (the box was opened and closed again)."""
    parts = []
    for number, (category, raw) in enumerate(_split_rows(), start=1):
        amount = to_decimal(raw)
        if raw and amount is None:
            raise ValueError(_("Suddivisione, riga %(n)s: «%(raw)s» non è un importo.", n=number, raw=raw))
        parts.append((category, amount))
    splits.apply(tx, parts)


def type_from(amount) -> str:
    """Minus = expense, no sign = income; the «transfer» box (or an explicit type=transfer) makes it a transfer.
    An explicit type=expense with a positive amount (older forms) stays an expense."""
    if "transfer" in request.form or request.form.get("type") == "transfer":
        return "transfer"
    if amount < 0 or request.form.get("type") == "expense":
        return "expense"
    return "income"


def linked_id(field: str, model) -> int | None:
    value = request.form.get(field, type=int)
    return value if value and db.session.get(model, value) else None


def _bank_amount(field: str, label: str, account_id: int | None, tx_currency: str) -> Decimal | None:
    """The amount typed for the account's currency; nothing when the account is in the transaction's currency."""
    account = db.session.get(Account, account_id) if account_id else None
    if account is None or (account.currency or "EUR") == tx_currency:
        return None
    value = form_decimal(field, label, allow_negative=True)
    return abs(value) if value else None


def form_values(tx: Transaction | None = None) -> dict:
    """What the form fields show: the stored transaction, what was typed (after an error), or a blank form."""
    if request.method == "POST":
        form = request.form
        return {key: form.get(key, "") for key in (
            "date", "amount", "currency", "description", "category", "tags",
            "recurrence", "recurrence_end", "notes", "account_id", "counter_account_id", "holding_id", "debt_id",
            "account_amount", "counter_amount", "units", "unit_price", "trade_side", "fee_amount")} | {
            "is_recurring": "is_recurring" in form, "transfer": "transfer" in form, "splits": _split_rows(),
            "record_fee": "record_fee" in form, "update_holding": "update_holding" in form}
    if tx is None:
        return {"currency": "EUR", "is_recurring": False, "transfer": False, "splits": [],
                "account_id": request.args.get("account", ""), "trade_side": "buy", "record_fee": True,
                "update_holding": True}
    sign = "-" if tx.type == "expense" else ""
    return {
        "transfer": tx.type == "transfer", "date": tx.date.isoformat() if tx.date else "",
        "amount": sign + f"{abs(tx.amount):.2f}".replace(".", ","), "currency": tx.currency or "EUR",
        "description": tx.description, "category": tx.category or "",
        "tags": ", ".join(tx.tags or []), "is_recurring": bool(tx.is_recurring), "recurrence": tx.recurrence or "",
        "recurrence_end": tx.recurrence_end.isoformat() if tx.recurrence_end else "", "notes": tx.notes or "",
        "account_id": str(tx.account_id or ""), "counter_account_id": str(tx.counter_account_id or ""),
        "holding_id": str(tx.holding_id or ""), "debt_id": str(tx.debt_id or ""),
        "account_amount": _plain(tx.account_amount), "counter_amount": _plain(tx.counter_amount),
        "splits": [(s.category or "", _plain(s.amount)) for s in tx.splits],
        "units": display.plain(abs(tx.units)) if tx.units is not None else "",
        "unit_price": display.plain(tx.unit_price),
        "trade_side": "sell" if tx.units is not None and tx.units < 0 else "buy",
    }


def _plain(value) -> str:
    """An amount as a form value with two decimals: 12.5 → '12,50'."""
    return f"{value:.2f}".replace(".", ",") if value is not None else ""
