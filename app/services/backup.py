"""
Full backup and restore: every table plus the files of the document archive, in one .zip
(backup.json + documents/…). A restore replaces all current data; a copy of it is saved first
under <instance>/backups, so a mistaken restore can be undone.

The older "JSON" export (transactions only) can be imported too: its transactions are added to
the existing ones, skipping those already present.
"""
import io
import json
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import current_app
from sqlalchemy import delete, insert, text
from sqlalchemy.types import ARRAY, JSON, Boolean, Date, DateTime, Integer, Numeric

from app.extensions import db
from app.models import (
    Account, AppSetting, Budget, Category, CategoryRule, Debt, ExchangeRate, Document, DuplicateDismissal, Goal, Holding, InsurancePolicy, Snapshot,
    Transaction, TransactionSplit,
)
from app.services import currency, document_store
from flask_babel import gettext as _

FORMAT = "myfinanceplace-backup"
VERSION = 2
DATA_FILE = "backup.json"
DOCUMENTS_DIR = "documents/"
KEEP_SAFETY_COPIES = 10
SAFETY_NAME = re.compile(r"^prima-del-ripristino_\d{8}-\d{6}\.zip$")

# Insertion order: a table comes after the tables it points to (documents and dismissals → transactions)
MODELS = [AppSetting, Account, Category, CategoryRule, ExchangeRate, Holding, Debt, Transaction, TransactionSplit, DuplicateDismissal,
          InsurancePolicy, Goal, Budget, Document, Snapshot]  # parents before the rows that point to them


class BackupError(Exception):
    """The file is not a usable backup; the message is shown to the user."""


# ── Values ─────────────────────────────────────────────────────────────────────

def _dump(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _load(column, value):
    if value is None:
        return None
    kind = column.type
    if isinstance(kind, DateTime):
        return datetime.fromisoformat(value)
    if isinstance(kind, Date):
        return date.fromisoformat(value[:10])
    if isinstance(kind, Numeric):
        return Decimal(str(value))
    if isinstance(kind, Boolean):
        return bool(value)
    if isinstance(kind, Integer):
        return int(value)
    if isinstance(kind, ARRAY):
        return [str(item) for item in value]
    if isinstance(kind, JSON):
        return value
    return str(value)


def _row(model, record: dict) -> dict:
    """A stored record as column values; unknown keys (from newer versions) are ignored."""
    values = {}
    for column in model.__table__.columns:
        if column.name in record:
            values[column.name] = _load(column, record[column.name])
        elif not column.nullable and column.default is None and not column.primary_key:
            raise BackupError(_("Tabella %(tablename__)s: manca il campo obbligatorio «%(name)s».", tablename__=model.__tablename__, name=column.name))
    return values


# ── Backup ─────────────────────────────────────────────────────────────────────

def export_data() -> dict:
    tables = {}
    for model in MODELS:
        columns = [c.name for c in model.__table__.columns]
        rows = db.session.execute(db.select(model.__table__).order_by(*model.__table__.primary_key.columns)).all()
        tables[model.__tablename__] = [{name: _dump(row._mapping[name]) for name in columns} for row in rows]
    return {"format": FORMAT, "version": VERSION, "created_at": datetime.now().isoformat(timespec="seconds"),
            "tables": tables}


def create_archive() -> bytes:
    data = export_data()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(DATA_FILE, json.dumps(data, ensure_ascii=False, indent=1))
        for record in data["tables"]["documents"]:
            content = document_store.read(record["stored_name"])
            if content is not None:
                archive.writestr(DOCUMENTS_DIR + record["stored_name"], content)
    return buffer.getvalue()


def counts(data: dict) -> dict:
    return {name: len(rows) for name, rows in data.get("tables", {}).items()}


# ── Reading an uploaded file ───────────────────────────────────────────────────

def read_upload(raw: bytes) -> tuple[dict, dict[str, bytes]]:
    """(data, document files) from a .zip backup or a .json file; BackupError when it is neither."""
    files = {}
    if zipfile.is_zipfile(io.BytesIO(raw)):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                data = json.loads(archive.read(DATA_FILE).decode("utf-8"))
                for name in archive.namelist():
                    stored = name[len(DOCUMENTS_DIR):]
                    if name.startswith(DOCUMENTS_DIR) and stored and "/" not in stored and not stored.startswith("."):
                        files[stored] = archive.read(name)
        except KeyError:
            raise BackupError(_("Nel file .zip manca %(DATA_FILE)s: non è un backup di MyFinancePlace.", DATA_FILE=DATA_FILE)) from None
        except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError):
            raise BackupError(_("Il file .zip è danneggiato o non è un backup di MyFinancePlace.")) from None
    else:
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise BackupError(_("Il file non è un backup (.zip) né un export JSON di MyFinancePlace.")) from None
    if not isinstance(data, dict):
        raise BackupError(_("Il file non è un backup di MyFinancePlace."))
    if data.get("format") == FORMAT:
        if not isinstance(data.get("tables"), dict):
            raise BackupError(_("Backup incompleto: mancano le tabelle."))
        if int(data.get("version") or 0) > VERSION:
            raise BackupError(_("Il backup viene da una versione più recente dell'app: aggiorna l'app prima di ripristinarlo."))
    elif not isinstance(data.get("transactions"), list):
        raise BackupError(_("Il file non è un backup di MyFinancePlace."))
    return data, files


def is_full_backup(data: dict) -> bool:
    return data.get("format") == FORMAT


# ── Restore ────────────────────────────────────────────────────────────────────

def restore(data: dict, files: dict[str, bytes]) -> dict:
    """Replace every table with the backup's content. All or nothing: on error nothing changes."""
    tables = data["tables"]
    try:
        prepared = [(model, [_row(model, record) for record in tables.get(model.__tablename__, [])]) for model in MODELS]
        for model in reversed(MODELS):
            db.session.execute(delete(model))
        for model, rows in prepared:
            if rows:
                db.session.execute(insert(model.__table__), rows)
        _reset_sequences()
        # backups made before multi-currency have no value in euro: compute it
        db.session.execute(text("UPDATE transactions SET amount_base = amount WHERE amount_base IS NULL"))
        # backups made before the counterparty became a tag: the same conversion as the migration b7c1d2e3f4a5
        db.session.execute(text("""
            UPDATE transactions SET tags = array_replace(tags, 'categoria-ai', 'da confermare (AI)')
            WHERE 'categoria-ai' = ANY(tags)"""))
        db.session.execute(text("""
            UPDATE transactions
            SET tags = ARRAY[btrim(counterparty)]::varchar[] || COALESCE(tags, ARRAY[]::varchar[])
            WHERE counterparty IS NOT NULL AND btrim(counterparty) <> ''
              AND NOT EXISTS (SELECT 1 FROM unnest(COALESCE(tags, ARRAY[]::varchar[])) AS t(tag)
                              WHERE lower(t.tag) = lower(btrim(counterparty)))"""))
        db.session.commit()
        currency.recompute()
    except BackupError:
        db.session.rollback()
        raise
    except (ValueError, TypeError, InvalidOperation, KeyError) as exc:
        db.session.rollback()
        raise BackupError(_("Il backup contiene un valore non valido (%(exc)s).", exc=exc)) from None
    except Exception as exc:  # database constraints (duplicates, broken links)
        db.session.rollback()
        raise BackupError(_("Il database ha rifiutato il backup: %(value)s", value=str(exc).splitlines()[0])) from None

    kept = {record["stored_name"] for record in tables.get("documents", [])}
    for stored, content in files.items():
        if stored in kept:
            document_store.write(stored, content)
    for path in document_store.folder().iterdir():  # files of documents that no longer exist
        if path.is_file() and path.name not in kept:
            path.unlink(missing_ok=True)
    return {model.__tablename__: len(rows) for model, rows in prepared}


def _reset_sequences() -> None:
    """After inserting explicit ids, new rows must continue from the highest one."""
    if db.engine.dialect.name != "postgresql":
        return
    for model in MODELS:
        table = model.__tablename__
        if "id" in model.__table__.columns and isinstance(model.__table__.columns["id"].type, Integer):
            db.session.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table}"
            ))


def import_transactions(data: dict) -> tuple[int, int]:
    """The older JSON export: add its transactions, skipping those already present. Returns (added, skipped)."""
    existing = {(t.date, t.description, Decimal(t.amount).quantize(Decimal("0.01")), t.type)
                for t in Transaction.query.all()}
    added = skipped = 0
    try:
        for record in data["transactions"]:
            record = {k: v for k, v in record.items() if k != "id"}
            values = _row(Transaction, record)
            if "date" not in values or "description" not in values or "amount" not in values:
                raise BackupError(_("Una transazione del file non ha data, descrizione o importo."))
            values["amount"] = abs(values["amount"])
            key = (values["date"], values["description"], values["amount"].quantize(Decimal("0.01")), values.get("type"))
            if key in existing:
                skipped += 1
                continue
            existing.add(key)
            values.pop("import_ref", None)
            db.session.add(Transaction(**values))
            added += 1
        db.session.commit()
    except BackupError:
        db.session.rollback()
        raise
    except (ValueError, TypeError, InvalidOperation, AttributeError) as exc:
        db.session.rollback()
        raise BackupError(_("Il file contiene un valore non valido (%(exc)s).", exc=exc)) from None
    return added, skipped


# ── Automatic copies taken before a restore ────────────────────────────────────

def safety_folder() -> Path:
    path = Path(current_app.instance_path) / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_safety_copy() -> str:
    name = f"prima-del-ripristino_{datetime.now():%Y%m%d-%H%M%S}.zip"
    (safety_folder() / name).write_bytes(create_archive())
    for old in list_safety_copies()[KEEP_SAFETY_COPIES:]:
        (safety_folder() / old["name"]).unlink(missing_ok=True)
    return name


def list_safety_copies() -> list[dict]:
    copies = [p for p in safety_folder().iterdir() if SAFETY_NAME.match(p.name)]
    copies.sort(key=lambda p: p.name, reverse=True)
    return [{"name": p.name, "size": p.stat().st_size,
             "created": datetime.strptime(p.name[21:36], "%Y%m%d-%H%M%S")} for p in copies]


def safety_copy_path(name: str) -> Path:
    if not SAFETY_NAME.match(name or ""):
        raise FileNotFoundError(name)
    return safety_folder() / name
