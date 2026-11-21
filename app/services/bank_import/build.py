"""A previewed row, as edited by the user, saved as a transaction."""
from __future__ import annotations

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.services import categories, money
from app.services.ai_classification import AI_TAG
from app.services.parsing import TRANSACTION_TYPES, clean_text, to_date, to_decimal, valid_amount

from .model import bank_causale


def build_transaction(base: dict, bank_key: str, fields: dict | None = None, ai: bool = False) -> Transaction:
    """
    Transaction from a statement row (a StatementRow.to_dict()). `fields` are the values as edited in the
    preview (default: the row as read); `base` is empty for rows added by hand. `ai` tags rows read by an
    AI model. Raises ValueError on invalid input.
    The original import_ref and the bank's causale are kept even when the user corrects the row:
    re-importing the same statement still recognizes it, and the bank's text stays on record.
    """
    fields = base if fields is None else fields
    tx_date = to_date(fields.get("date"))
    amount = to_decimal(fields.get("amount"))
    description = clean_text(fields.get("description"))
    tx_type = fields.get("type")
    if tx_date is None or not valid_amount(amount) or not description or tx_type not in TRANSACTION_TYPES:
        raise ValueError("incomplete row")
    counterparty = clean_text(fields.get("counterparty"))
    # the counterparty is the first tag (as in the transaction form)
    tags = ([counterparty] if counterparty else []) + ["importato", bank_key] + (["ai"] if ai else []) + ([] if base else ["manuale"])
    detail = clean_text(fields.get("aitag")) if fields.get("aicat") else None
    if detail and detail.casefold() not in {t.casefold() for t in tags}:
        tags.append(detail)  # the detail of a broad category (F32) the AI suggested with it
    if fields.get("aicat"):
        tags.append(AI_TAG)  # category suggested by the AI and accepted unchanged: worth a later review
    return Transaction(
        date=tx_date,
        description=description,
        amount=money.cents(abs(amount)),
        currency=base.get("currency") or "EUR",
        type=tx_type,
        category=clean_text(fields.get("category")) or categories.fallback(),
        counterparty=counterparty,
        tags=tags,
        is_recurring=False,
        notes=base.get("details"),
        import_ref=base.get("import_ref"),
        bank_description=bank_causale(base) if base else None,
    )


def is_outgoing(base: dict) -> bool:
    """The statement row moves money out of the account (the preview shows amounts without sign)."""
    return (to_decimal(base.get("amount")) or 0) <= 0


def assign_account(tx: Transaction, base: dict, account: Account) -> None:
    """Money coming in through a transfer arrives on `account`; everything else moves from it. The direction comes
    from the statement row as read; the IBAN of another own account in the row is the other side of the giroconto."""
    if tx.type == "transfer" and not is_outgoing(base):
        tx.counter_account_id = account.id
    else:
        tx.account_id = account.id
    other = base.get("own_account")
    if tx.type == "transfer" and other and other != account.id and db.session.get(Account, other) is not None:
        if is_outgoing(base):
            tx.counter_account_id = other
        else:
            tx.account_id = other
