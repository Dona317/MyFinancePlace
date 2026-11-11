"""
The investments on their own: an export of the Portfolio section, and its restore, without touching the rest of the
archive (current accounts, budgets, insurance…).

What belongs to the section:
- securities accounts, portfolios, the instruments held (every holding but the house and the car: those are wealth,
  and debts point to them), their prices and look-through exposures;
- model portfolios with their parts, rules, PACs and theoretical orders;
- the transactions of the investments: trades, dividends, coupons, commissions and taxes of a holding, everything
  placed in a securities account, and every movement of a securities account's liquidity (the money sent from the
  current account included), so that the liquidity comes back right.
The accounts those transactions move money on travel by name: on restore an account with the same name is reused,
a missing one is created.

The restore replaces the section: what was there is removed (a full backup of the archive is saved first by the
caller), the file's rows are inserted with new ids, every link between them kept. Links to things outside the
section (a debt, a spending event, a document) are not carried.
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from decimal import InvalidOperation

from flask_babel import gettext as _
from sqlalchemy import delete, insert, or_, select

from app.extensions import db
from app.models import (
    Account,
    Holding,
    HoldingExposure,
    HoldingPrice,
    InvestmentPlan,
    PlannedOrder,
    Portfolio,
    PortfolioRule,
    PortfolioTemplate,
    SecuritiesAccount,
    SlotHolding,
    TemplateSlot,
    Transaction,
)
from app.services import backup, securities

FORMAT = "myfinanceplace-investments"
VERSION = 1
DATA_FILE = "investimenti.json"
NOT_INVESTMENTS = ("Immobile", "Veicolo")  # wealth, not the portfolio: debts and the balance sheet point to them
# parents before the rows that point to them
MODELS = [SecuritiesAccount, Portfolio, Holding, HoldingPrice, HoldingExposure, PortfolioTemplate, TemplateSlot,
          SlotHolding, PortfolioRule, InvestmentPlan, Transaction, PlannedOrder]


class ArchiveError(ValueError):
    """The file cannot be restored; the message is shown to the user."""


# ── What belongs to the section ────────────────────────────────────────────────

def _holding_ids() -> list[int]:
    return [i for (i,) in db.session.execute(select(Holding.id).where(Holding.asset_class.not_in(NOT_INVESTMENTS)))]


def _transaction_ids(holding_ids: list[int]) -> list[int]:
    settlement = [i for (i,) in db.session.execute(select(SecuritiesAccount.settlement_account_id))
                  if i is not None]
    own = select(Transaction.id).where(or_(Transaction.holding_id.in_(holding_ids),
                                           Transaction.securities_account_id.isnot(None),
                                           Transaction.account_id.in_(settlement),
                                           Transaction.counter_account_id.in_(settlement)))
    ids = {i for (i,) in db.session.execute(own)}
    fees = select(Transaction.id).where(Transaction.fee_for_id.in_(ids)) if ids else None
    if fees is not None:
        ids |= {i for (i,) in db.session.execute(fees)}
    return sorted(ids)


def _rows(model, where=None) -> list[dict]:
    table = model.__table__
    query = select(table).order_by(*table.primary_key.columns)
    if where is not None:
        query = query.where(where)
    return [{c.name: backup._dump(row._mapping[c.name]) for c in table.columns}
            for row in db.session.execute(query)]


def _selection() -> dict:
    holdings = _holding_ids()
    transactions = _transaction_ids(holdings)
    templates = [i for (i,) in db.session.execute(select(PortfolioTemplate.id))]
    slots = [i for (i,) in db.session.execute(select(TemplateSlot.id))]
    return {
        SecuritiesAccount: None, Portfolio: None,
        Holding: Holding.id.in_(holdings),
        HoldingPrice: HoldingPrice.holding_id.in_(holdings),
        HoldingExposure: HoldingExposure.holding_id.in_(holdings),
        PortfolioTemplate: PortfolioTemplate.id.in_(templates),
        TemplateSlot: TemplateSlot.id.in_(slots),
        SlotHolding: SlotHolding.holding_id.in_(holdings),
        PortfolioRule: or_(PortfolioRule.holding_id.is_(None), PortfolioRule.holding_id.in_(holdings)),
        InvestmentPlan: None,
        Transaction: Transaction.id.in_(transactions),
        PlannedOrder: PlannedOrder.holding_id.in_(holdings),
    }


# ── Export ─────────────────────────────────────────────────────────────────────

def export_data() -> dict:
    tables = {model.__tablename__: _rows(model, where) for model, where in _selection().items()}
    used = set()
    for name, column in (("transactions", "account_id"), ("transactions", "counter_account_id"),
                         ("securities_accounts", "settlement_account_id"), ("investment_plans", "account_id"),
                         ("planned_orders", "account_id")):
        used |= {row[column] for row in tables[name] if row.get(column)}
    tables["accounts"] = _rows(Account, Account.id.in_(sorted(used))) if used else []
    return {"format": FORMAT, "version": VERSION, "created_at": datetime.now().isoformat(timespec="seconds"),
            "tables": tables}


def create_archive() -> bytes:
    data = export_data()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(DATA_FILE, json.dumps(data, ensure_ascii=False, indent=1))
    return buffer.getvalue()


def counts(data: dict) -> dict[str, int]:
    return {name: len(rows) for name, rows in data.get("tables", {}).items()}


# ── Restore ────────────────────────────────────────────────────────────────────

def read_upload(raw: bytes) -> dict:
    try:
        if raw[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                raw = archive.read(DATA_FILE)
        data = json.loads(raw.decode("utf-8-sig"))
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError):
        raise ArchiveError(_("Il file non è un export degli investimenti di MyFinancePlace.")) from None
    if not isinstance(data, dict) or data.get("format") != FORMAT or not isinstance(data.get("tables"), dict):
        raise ArchiveError(_("Il file non è un export degli investimenti di MyFinancePlace."))
    return data


def _clear() -> None:
    """Remove the section as it is now (the rows the export would take)."""
    selection = _selection()
    for model in reversed(MODELS):
        where = selection[model]
        if model in (Transaction,):
            ids = [i for (i,) in db.session.execute(select(Transaction.id).where(where))]
            if ids:
                db.session.execute(delete(Transaction).where(Transaction.fee_for_id.in_(ids)))
                db.session.execute(delete(Transaction).where(Transaction.id.in_(ids)))
            continue
        db.session.execute(delete(model) if where is None else delete(model).where(where))
    db.session.flush()


def _accounts(records: list[dict]) -> dict[int, int]:
    """File account id → archive account id: the account with the same name, or a new one."""
    found = {}
    for record in records:
        name = (record.get("name") or "").strip()
        if not name:
            continue
        account = Account.query.filter(db.func.lower(Account.name) == name.lower()).first()
        if account is None:
            values = backup._row(Account, record)
            values.pop("id", None)
            values.pop("fixed", None)
            account = Account(**values)
            db.session.add(account)
            db.session.flush()
        found[int(record["id"])] = account.id
    return found


def restore(data: dict) -> dict[str, int]:
    """Replace the investments with the file's. All or nothing: on error nothing changes."""
    tables = data["tables"]
    try:
        _clear()
        ids: dict[str, dict[int, int]] = {"accounts": _accounts(tables.get("accounts", []))}
        added = {}
        for model in MODELS:
            table = model.__table__
            ids[table.name] = {}
            pending_fees = []
            rows = tables.get(table.name, [])
            for record in rows:
                values = backup._row(model, record)
                old = values.pop("id", None)
                for column in table.columns:
                    for fk in column.foreign_keys:
                        target = fk.column.table.name
                        value = values.get(column.name)
                        if value is None:
                            continue
                        if target == table.name:  # a commission → its trade: inserted after it
                            pending_fees.append(column.name)
                            continue
                        values[column.name] = ids.get(target, {}).get(value)
                        if values[column.name] is None and not column.nullable:
                            raise ArchiveError(_("Il file ha un collegamento rotto (%(table)s.%(column)s).",
                                                 table=table.name, column=column.name))
                new = db.session.execute(insert(table).values(
                    **{k: v for k, v in values.items() if k not in pending_fees})).inserted_primary_key[0]
                if old is not None:
                    ids[table.name][int(old)] = new
            for record in rows:  # self links (a commission and its trade)
                for column_name in set(pending_fees):
                    if record.get(column_name) is not None:
                        db.session.execute(table.update().where(table.c.id == ids[table.name][int(record["id"])])
                                           .values({column_name: ids[table.name].get(int(record[column_name]))}))
            added[table.name] = len(rows)
        if securities.ensure_assigned():
            db.session.flush()
        if not Portfolio.query.filter_by(is_default=True).first() and Portfolio.query.first():
            securities.set_default(Portfolio.query.order_by(Portfolio.position, Portfolio.id).first())
        db.session.commit()
    except ArchiveError:
        db.session.rollback()
        raise
    except (ValueError, TypeError, KeyError, InvalidOperation, backup.BackupError) as exc:
        db.session.rollback()
        raise ArchiveError(_("Il file contiene un valore non valido (%(exc)s).", exc=exc)) from None
    except Exception as exc:  # database constraints
        db.session.rollback()
        raise ArchiveError(_("Il database ha rifiutato il file: %(value)s", value=str(exc).splitlines()[0])) from None
    return added
