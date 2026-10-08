import json
import math
from datetime import date, datetime

from apiflask import APIBlueprint
from flask import abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_babel import gettext as _
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.account import Account
from app.routes.helpers import download, form_ids, uploaded_file, year_arg
from app.services import (
    accounts,
    ai_classification,
    ai_extraction,
    ai_jobs,
    ai_models,
    analytics,
    backup,
    bank_import,
    column_guess,
    pdf_report,
    statement_readers,
    transfer,
    upload_store,
)
from app.services.categories import known_categories
from app.services.parsing import to_decimal
from app.services.periods import year_bounds
from app.services.tags import all_tags

export_bp = APIBlueprint(
    "export",
    __name__,
    url_prefix="/export",
    tag="Export"
)


def _preview_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(current_app.secret_key, salt="bank-import-preview")


@export_bp.route("/")
def index():
    return render_template(
        "export/index.html",
        years=analytics.available_years(),
        banks=bank_import.BANKS,
        ai_reader=ai_extraction.describe(),
        **ai_classification.template_context(),
        safety_copies=backup.list_safety_copies(),
    )


# ── Full backup and restore ────────────────────────────────────────────────────

@export_bp.route("/backup")
def download_backup():
    """Everything in one .zip: all the tables and the files of the document archive."""
    return download(backup.create_archive(), f"myfinanceplace_backup_{datetime.now():%Y-%m-%d_%H%M}.zip",
                    "application/zip")


@export_bp.route("/restore", methods=["POST"])
def restore():
    upload = uploaded_file()
    if upload is None:
        flash(_("Scegli il file di backup da ripristinare."), "error")
        return redirect(url_for("export.index") + "#backup")
    try:
        data, files = backup.read_upload(upload.read())
        if not backup.is_full_backup(data):
            added, skipped = backup.import_transactions(data)
            flash(_("Export JSON importato: %(added)s transazioni aggiunte, %(skipped)s già presenti ignorate.", added=added, skipped=skipped), "success")
            return redirect(url_for("transactions.index"))
        if not request.form.get("confirm"):
            flash(_("Per ripristinare un backup completo conferma che i dati attuali verranno sostituiti."), "error")
            return redirect(url_for("export.index") + "#backup")
        safety = backup.save_safety_copy()
        restored = backup.restore(data, files)
    except backup.BackupError as exc:
        flash(str(exc), "error")
        return redirect(url_for("export.index") + "#backup")
    flash(
        _("Backup ripristinato: %(transactions)s transazioni, %(holdings)s posizioni, %(debts)s debiti, %(policies)s polizze, %(goals)s obiettivi, %(documents)s documenti, %(snapshots)s istantanee. I dati di prima sono salvati in «%(safety)s» (vedi Backup automatici).", transactions=restored['transactions'], holdings=restored['holdings'], debts=restored['debts'], policies=restored['insurance_policies'], goals=restored['goals'], documents=restored['documents'], snapshots=restored['snapshots'], safety=safety),
        "success",
    )
    return redirect(url_for("export.index") + "#backup")


@export_bp.route("/backup/automatic/<name>")
def download_safety_copy(name):
    try:
        path = backup.safety_copy_path(name)
    except FileNotFoundError:
        abort(404)
    if not path.exists():
        abort(404)
    return send_file(path, mimetype="application/zip", as_attachment=True, download_name=name)


@export_bp.route("/csv")
def export_csv():
    period = request.args.get("period", "all")
    start, end = transfer.period_bounds(period)
    transactions = transfer.query_transactions(start, end)
    # BOM so Excel detects UTF-8 correctly
    content = "\ufeff" + transfer.to_csv(transactions)
    return download(content, f"transazioni_{period}_{date.today().isoformat()}.csv", "text/csv; charset=utf-8")


@export_bp.route("/json")
def export_json():
    transactions = transfer.query_transactions()
    payload = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "version": 1,
        "transactions": [transfer.tx_to_dict(tx) for tx in transactions],
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    return download(content, f"myfinanceplace_backup_{date.today().isoformat()}.json", "application/json")


@export_bp.route("/pdf")
def export_pdf():
    """Print-ready report page ("Stampa dal browser"); /pdf/download gives the same report as a real PDF."""
    year = year_arg(date.today().year)
    return render_template(
        "export/report.html",
        year=year,
        statement=analytics.income_statement(year),
        cash_flow=analytics.cash_flow(year),
        generated_at=datetime.now(),
    )


@export_bp.route("/pdf/download")
def export_pdf_download():
    """The yearly report as a PDF file generated on the server."""
    year = year_arg(date.today().year)
    content = pdf_report.build_report(year, analytics.income_statement(year), analytics.cash_flow(year))
    return download(content, f"report_finanziario_{year}.pdf", "application/pdf")


@export_bp.route("/tax/<int:year>")
def export_tax(year):
    transactions = [
        tx for tx in transfer.query_transactions(*year_bounds(year))
        if transfer.is_tax_relevant(tx)
    ]
    content = "\ufeff" + transfer.to_csv(transactions)
    return download(content, f"fiscale_{year}.csv", "text/csv; charset=utf-8")


@export_bp.route("/import/columns", methods=["POST"])
def import_columns():
    """Column names of an uploaded CSV / Excel / .ods file, for the mapping selects (JSON); nothing is saved."""
    upload = uploaded_file()
    if upload is None:
        return jsonify({"error": _("Seleziona un file.")}), 400
    try:
        headers, rows, first_line = transfer.read_table(upload.filename, upload.read())
    except transfer.TableError as exc:
        return jsonify({"error": str(exc)}), 400
    guessed = column_guess.guess(headers, rows)
    return jsonify({"headers": headers, "rows": len(rows), "header_line": first_line - 1,
                    "guess": guessed.mapping, "sure": guessed.sure})


@export_bp.route("/import/columns/ai", methods=["POST"])
def import_columns_ai():
    """Ask the AI which column is what, sending only the titles and the first rows (the user clicked for it)."""
    upload = uploaded_file()
    if upload is None:
        return jsonify({"error": _("Seleziona un file.")}), 400
    try:
        headers, rows, _first_line = transfer.read_table(upload.filename, upload.read())
        guessed = column_guess.ask_ai(headers, rows)
    except (transfer.TableError, ai_extraction.AIExtractionError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"guess": guessed.mapping, "notes": guessed.notes, "model": ai_classification.model_name()})


@export_bp.route("/import", methods=["POST"])
def import_csv():
    """Manual column-mapping import of a CSV or spreadsheet (.xlsx, .xls, .ods)."""
    upload = uploaded_file()
    if upload is None:
        flash(_("Seleziona un file CSV o Excel da importare."), "error")
        return redirect(url_for("export.index"))
    try:
        headers, rows, first_line = transfer.read_table(upload.filename, upload.read())
    except transfer.TableError as exc:
        flash(str(exc), "error")
        return redirect(url_for("export.index"))

    # the chosen columns are checked against the values, then the rows open in the editable preview
    mapping = {field: request.form.get(f"col_{field}") or None for field in column_guess.FIELDS}
    try:
        preview = bank_import.preview_from_mapping(headers, rows, mapping, first_line)
    except bank_import.StatementImportError as exc:
        flash(str(exc), "error")
        return redirect(url_for("export.index"))
    return _render_preview(preview, upload.filename)


# ── Bank statement import (Fineco, Intesa Sanpaolo, generic) ───────────────────
#
#  upload ──▶ rule-based reading ──ok──▶ editable preview ──▶ confirm (save)
#                   │ fails
#                   ▼
#          "Read it with AI?" (user decides, picks the model) ──yes──▶ waiting page ──▶ editable preview ──▶ confirm
#                                                                     (background job, see ai_jobs)

def _render_preview(preview, filename: str, ai_retry: str | None = None):
    payload = _preview_serializer().dumps({
        "bank": preview.bank.key,
        "ai": bool(preview.ai_model),
        "rows": [row.to_dict() for row in preview.rows],
    })
    return render_template(
        "export/bank_preview.html",
        preview=preview,
        payload=payload,
        filename=filename,
        categories=known_categories(),
        tag_pool=all_tags(),
        accounts=accounts.active(),
        suggested_account=_suggested_account(preview.bank.name),
        ai_retry=ai_retry,
        **ai_classification.template_context(),
    )


def _suggested_account(bank_name: str) -> int | None:
    """The account whose name contains the bank's (e.g. "Fineco" for a Fineco statement), if exactly one."""
    matches = [a for a in accounts.active() if bank_name.split()[0].lower() in a.name.lower()]
    return matches[0].id if len(matches) == 1 else None


@export_bp.route("/bank", methods=["POST"])
def bank_preview():
    """Step 1: parse the uploaded statement and show an editable preview (or ask about AI reading)."""
    upload = uploaded_file()
    if upload is None:
        flash(_("Seleziona l'estratto conto da importare."), "error")
        return redirect(url_for("export.index"))

    bank = request.form.get("bank", bank_import.AUTO)
    raw = upload.read()
    try:
        preview = bank_import.analyze_statement(upload.filename, raw, bank)
    except bank_import.AIRequired as exc:
        token = upload_store.save(upload.filename, raw, bank=bank, reason=exc.reason, kind=exc.kind)
        return redirect(url_for("export.bank_ai", token=token))
    except bank_import.StatementImportError as exc:
        flash(str(exc), "error")
        return redirect(url_for("export.index"))
    retry = None
    if preview.ocr and ai_extraction.provider():
        # read by the light OCR: the AI is the backup, offered on the preview or straight away when OCR missed rows
        kind = "scan" if statement_readers.is_pdf(raw) else "photo"
        retry = upload_store.save(upload.filename, raw, bank=bank, kind=kind, ocr_rows=len(preview.rows),
                                  reason=_("La lettura OCR sembra incompleta."))
        if preview.ocr_doubtful:
            return redirect(url_for("export.bank_ai", token=retry))
    return _render_preview(preview, upload.filename, ai_retry=retry)


def _ai_choices(needs_vision: bool) -> dict:
    """Models the user can pick on the confirmation page, with why some are not usable."""
    provider = ai_extraction.provider()
    choices = {"provider": provider, "label": ai_extraction.describe(), "current": ai_extraction.model_name(),
               "models": [], "ollama": None}
    if provider == "ollama":
        ollama = ai_models.status(ai_extraction.base_url())
        choices["ollama"] = ollama
        for name in sorted(ollama["installed"]):
            vision = ai_models.is_vision(name)
            choices["models"].append({"name": name, "usable": vision or not needs_vision, "vision": vision})
    elif provider == "anthropic":
        choices["models"] = [{"name": n, "usable": True, "vision": True}
                             for n in dict.fromkeys([choices["current"], *ai_extraction.ANTHROPIC_MODELS])]
    return choices


def _load_upload(token: str):
    """(raw, meta) of a pending upload, or None after flashing why it is gone."""
    try:
        return upload_store.load(token)
    except KeyError:
        flash(_("Il file non è più disponibile: caricalo di nuovo."), "error")
        return None


@export_bp.route("/bank/ai/<token>", methods=["GET", "POST"])
def bank_ai(token):
    """Ask before reading an unreadable file with AI; on POST, start reading it with the chosen model."""
    upload = _load_upload(token)
    if upload is None:
        return redirect(url_for("export.index"))
    raw, meta = upload

    job = ai_jobs.get(token)
    if request.method == "GET" and job and (ai_jobs.is_active(job) or job["state"] == "done"):
        return redirect(url_for("export.bank_ai_wait", token=token))

    needs_vision = meta.get("kind") in ("scan", "photo")
    choices = _ai_choices(needs_vision)
    error = None
    if request.method == "POST":
        model = (request.form.get("model") or "").strip() or None
        usable = {m["name"] for m in choices["models"] if m["usable"]}
        if choices["provider"] is None:
            error = _("La lettura AI non è configurata.")
        elif model and model not in usable:
            error = _("Il modello %(model)s non può leggere questo file.", model=model)
        else:
            job = ai_jobs.start(token, meta["filename"], raw, meta.get("bank", bank_import.AUTO), model)
            if job["state"] == "done":  # AI_JOBS_SYNC: already read
                return _render_ai_result(token, meta)
            if job["state"] == "error":
                error = job["error"]  # stay on this page: the user can try another model
            else:
                return redirect(url_for("export.bank_ai_wait", token=token))

    return render_template(
        "export/ai_confirm.html", token=token, meta=meta, needs_vision=needs_vision,
        choices=choices, error=error, size_kb=len(raw) // 1024,
    )


@export_bp.route("/bank/ai/<token>/wait")
def bank_ai_wait(token):
    """Waiting page of a reading in progress; it polls bank_ai_status (or reloads itself without JavaScript)."""
    upload = _load_upload(token)
    if upload is None:
        return redirect(url_for("export.index"))
    job = ai_jobs.get(token)
    if job is None:
        return redirect(url_for("export.bank_ai", token=token))
    if job["state"] == "done":
        return redirect(url_for("export.bank_ai_result", token=token))
    return render_template("export/bank_ai_wait.html", token=token, meta=upload[1], job=job,
                           active=ai_jobs.is_active(job))


@export_bp.route("/bank/ai/<token>/status")
def bank_ai_status(token):
    """State of the AI reading, polled by the waiting page."""
    job = ai_jobs.get(token)
    if job is None:
        return jsonify({"state": "missing", "url": url_for("export.bank_ai", token=token)}), 404
    data = {key: job[key] for key in ("state", "model", "label", "done", "total", "unit", "elapsed", "error",
                                      "cancel_requested", "rows", "progress")}
    if job["state"] == "done":
        data["url"] = url_for("export.bank_ai_result", token=token)
    return jsonify(data)


@export_bp.route("/bank/ai/<token>/result")
def bank_ai_result(token):
    """The editable preview of a finished reading."""
    upload = _load_upload(token)
    if upload is None:
        return redirect(url_for("export.index"))
    if ai_jobs.result(token) is None:
        return redirect(url_for("export.bank_ai_wait", token=token))
    return _render_ai_result(token, upload[1])


def _render_ai_result(token: str, meta: dict):
    try:
        preview = bank_import.preview_from_ai(meta["filename"], ai_jobs.result(token), meta.get("bank", bank_import.AUTO))
    except bank_import.StatementImportError as exc:
        flash(str(exc), "error")
        return redirect(url_for("export.bank_ai", token=token))
    ai_jobs.discard(token)  # the rows now travel in the signed preview payload
    return _render_preview(preview, meta["filename"])


@export_bp.route("/bank/ai/<token>/cancel", methods=["POST"])
def bank_ai_cancel(token):
    """Stop the reading ("Annulla" on the waiting page, the file is kept) or drop the whole import."""
    if request.form.get("scope") == "job":
        ai_jobs.cancel(token)
        return redirect(url_for("export.bank_ai_wait", token=token))
    ai_jobs.discard(token)
    flash(_("Importazione annullata."), "success")
    return redirect(url_for("export.index"))


PREVIEW_FIELDS = ("date", "description", "amount", "type", "category", "counterparty", "aicat")


def _assign_account(tx, base: dict, account: Account) -> None:
    """Money coming in through a transfer arrives on `account`; everything else moves from it. The preview shows
    amounts without sign: the direction comes from the statement row as read."""
    if tx.type == "transfer" and (to_decimal(base.get("amount")) or 0) > 0:
        tx.counter_account_id = account.id
    else:
        tx.account_id = account.id


def _collect_rows(data: dict, account: Account | None) -> tuple[list, list[int], int]:
    """The rows the user kept, as transactions: (created, invalid row numbers, skipped as already imported)."""
    rows = data["rows"]
    selected = sorted(form_ids("include"))
    existing = bank_import.already_imported([rows[i]["import_ref"] for i in selected if i < len(rows)])
    created, invalid, skipped = [], [], 0
    for index in selected:
        base = rows[index] if index < len(rows) else {}  # indexes past the payload are rows added by hand
        if base.get("import_ref") in existing:
            skipped += 1
            continue
        fields = {name: request.form.get(f"{name}-{index}", "") for name in PREVIEW_FIELDS}
        try:
            tx = bank_import.build_transaction(base, data["bank"], fields, ai=data.get("ai", False))
        except ValueError:
            invalid.append(index + 1)
            continue
        if account is not None:
            _assign_account(tx, base, account)
        created.append(tx)
    return created, invalid, skipped


def _import_message(count: int, bank_key: str, account: Account | None, skipped: int) -> str:
    bank_name = bank_import.layout_named(bank_key).name
    if account:
        message = _("%(count)s movimenti importati da %(bank)s sul conto «%(account)s».",
                    count=count, bank=bank_name, account=account.name)
    else:
        message = _("%(count)s movimenti importati da %(bank)s.", count=count, bank=bank_name)
    if skipped:
        message += " " + _("%(count)s già presenti sono stati ignorati.", count=skipped)
    return message


@export_bp.route("/bank/confirm", methods=["POST"])
def bank_confirm():
    """Step 2: save the rows the user kept, with every field as edited in the preview."""
    try:
        data = _preview_serializer().loads(request.form.get("payload", ""))
    except BadSignature:
        flash(_("Anteprima non valida o scaduta: carica di nuovo il file."), "error")
        return redirect(url_for("export.index"))

    account = db.session.get(Account, request.form.get("account_id", type=int) or 0)
    created, invalid, skipped = _collect_rows(data, account)
    db.session.add_all(created)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash(_("Alcuni movimenti risultano già importati: ricarica il file e riprova."), "error")
        return redirect(url_for("export.index"))

    flash(_import_message(len(created), data["bank"], account, skipped), "success")
    if invalid:
        flash(_("Righe non salvate perché incomplete o non valide: %(value)s.", value=', '.join(map(str, invalid))), "warning")
    return redirect(url_for("transactions.index"))


@export_bp.route("/bank/classify", methods=["POST"])
def bank_classify():
    """Suggest category and counterparty for preview rows (JSON in, JSON out); nothing is saved here."""
    body = request.get_json(silent=True)
    rows = body.get("rows") if isinstance(body, dict) else None
    items = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            amount = float(row.get("amount") or 0)
            items.append({"id": int(row["index"]), "text": str(row.get("text") or ""),
                          "amount": amount if math.isfinite(amount) else 0.0})
        except (KeyError, TypeError, ValueError):
            continue
    if not items:
        return jsonify({"error": _("Nessun movimento da classificare.")}), 400
    try:
        suggestions = ai_classification.classify(items, known_categories())
    except ai_extraction.AIExtractionError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({
        "model": ai_classification.model_name(),
        "suggestions": {str(i): s.to_dict() for i, s in suggestions.items()},
    })
