import json
import math
from datetime import date, datetime
from flask import render_template, request, redirect, url_for, flash, Response, current_app, jsonify, send_file, abort
from apiflask import APIBlueprint
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models.account import Account
from app.services.parsing import to_decimal
from app.routes.helpers import form_ids
from app.services import (
    accounts, analytics, transfer, bank_import, ai_classification, ai_extraction, ai_jobs, ai_models, upload_store, backup,
    pdf_report,
)
from app.services.categories import known_categories
from flask_babel import gettext as _

export_bp = APIBlueprint(
    "export",
    __name__,
    url_prefix="/export",
    tag="Export"
)


def _download(content: str, filename: str, mimetype: str) -> Response:
    return Response(
        content,
        mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
        safety_copies=backup.list_safety_copies(),
    )


# ── Full backup and restore ────────────────────────────────────────────────────

@export_bp.route("/backup")
def download_backup():
    """Everything in one .zip: all the tables and the files of the document archive."""
    content = backup.create_archive()
    return Response(content, mimetype="application/zip", headers={
        "Content-Disposition": f'attachment; filename="myfinanceplace_backup_{datetime.now():%Y-%m-%d_%H%M}.zip"',
    })


@export_bp.route("/restore", methods=["POST"])
def restore():
    upload = request.files.get("file")
    if not upload or not upload.filename:
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
    return _download(content, f"transazioni_{period}_{date.today().isoformat()}.csv", "text/csv; charset=utf-8")


@export_bp.route("/json")
def export_json():
    transactions = transfer.query_transactions()
    payload = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "version": 1,
        "transactions": [transfer.tx_to_dict(tx) for tx in transactions],
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    return _download(content, f"myfinanceplace_backup_{date.today().isoformat()}.json", "application/json")


@export_bp.route("/pdf")
def export_pdf():
    """Print-ready report page ("Stampa dal browser"); /pdf/download gives the same report as a real PDF."""
    year = request.args.get("year", type=int) or date.today().year
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
    year = request.args.get("year", type=int) or date.today().year
    content = pdf_report.build_report(year, analytics.income_statement(year), analytics.cash_flow(year))
    return Response(content, mimetype="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="report_finanziario_{year}.pdf"',
    })


@export_bp.route("/tax/<int:year>")
def export_tax(year):
    transactions = [
        tx for tx in transfer.query_transactions(date(year, 1, 1), date(year + 1, 1, 1))
        if transfer.is_tax_relevant(tx)
    ]
    content = "\ufeff" + transfer.to_csv(transactions)
    return _download(content, f"fiscale_{year}.csv", "text/csv; charset=utf-8")


@export_bp.route("/import/columns", methods=["POST"])
def import_columns():
    """Column names of an uploaded CSV / Excel / .ods file, for the mapping selects (JSON); nothing is saved."""
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": "Seleziona un file."}), 400
    try:
        headers, rows, first_line = transfer.read_table(upload.filename, upload.read())
    except transfer.TableError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"headers": headers, "rows": len(rows), "header_line": first_line - 1})


@export_bp.route("/import", methods=["POST"])
def import_csv():
    """Manual column-mapping import of a CSV or spreadsheet (.xlsx, .xls, .ods)."""
    upload = request.files.get("file")
    if not upload or not upload.filename:
        flash(_("Seleziona un file CSV o Excel da importare."), "error")
        return redirect(url_for("export.index"))
    try:
        headers, rows, first_line = transfer.read_table(upload.filename, upload.read())
    except transfer.TableError as exc:
        flash(str(exc), "error")
        return redirect(url_for("export.index"))

    mapping = {
        field: request.form.get(f"col_{field}") or None
        for field in ("date", "amount", "description", "category", "type", "counterparty")
    }
    missing = [f for f in ("date", "amount", "description") if mapping[f] not in headers]
    if missing:
        flash(_("Colonne obbligatorie non mappate: %(value)s.", value=', '.join(missing)), "error")
        return redirect(url_for("export.index"))

    transactions, errors = transfer.rows_to_transactions(rows, mapping, first_line)
    if errors:
        preview = "; ".join(errors[:5]) + (" …" if len(errors) > 5 else "")
        flash(_("Importazione annullata, %(count)s righe non valide — %(preview)s", count=len(errors), preview=preview), "error")
        return redirect(url_for("export.index"))

    db.session.add_all(transactions)
    db.session.commit()
    flash(_("%(count)s transazioni importate con successo.", count=len(transactions)), "success")
    return redirect(url_for("transactions.index"))


# ── Bank statement import (Fineco, Intesa Sanpaolo, generic) ───────────────────
#
#  upload ──▶ rule-based reading ──ok──▶ editable preview ──▶ confirm (save)
#                   │ fails
#                   ▼
#          "Read it with AI?" (user decides, picks the model) ──yes──▶ waiting page ──▶ editable preview ──▶ confirm
#                                                                     (background job, see ai_jobs)

def _render_preview(preview, filename: str):
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
        accounts=accounts.active(),
        suggested_account=_suggested_account(preview.bank.name),
        **ai_classification.template_context(),
    )


def _suggested_account(bank_name: str) -> int | None:
    """The account whose name contains the bank's (e.g. "Fineco" for a Fineco statement), if exactly one."""
    matches = [a for a in accounts.active() if bank_name.split()[0].lower() in a.name.lower()]
    return matches[0].id if len(matches) == 1 else None


@export_bp.route("/bank", methods=["POST"])
def bank_preview():
    """Step 1: parse the uploaded statement and show an editable preview (or ask about AI reading)."""
    upload = request.files.get("file")
    if not upload or not upload.filename:
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
    return _render_preview(preview, upload.filename)


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
            error = "La lettura AI non è configurata."
        elif model and model not in usable:
            error = f"Il modello {model} non può leggere questo file."
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


@export_bp.route("/bank/confirm", methods=["POST"])
def bank_confirm():
    """Step 2: save the rows the user kept, with every field as edited in the preview."""
    try:
        data = _preview_serializer().loads(request.form.get("payload", ""))
    except BadSignature:
        flash(_("Anteprima non valida o scaduta: carica di nuovo il file."), "error")
        return redirect(url_for("export.index"))

    rows = data["rows"]
    selected = sorted(form_ids("include"))
    existing = bank_import.already_imported([rows[i]["import_ref"] for i in selected if i < len(rows)])

    created, invalid, skipped = [], [], 0
    account = db.session.get(Account, request.form.get("account_id", type=int) or 0)
    for index in selected:
        base = rows[index] if index < len(rows) else {}  # indexes past the payload are rows added by hand
        if base.get("import_ref") in existing:
            skipped += 1
            continue
        fields = {name: request.form.get(f"{name}-{index}", "") for name in
                  ("date", "description", "amount", "type", "category", "counterparty", "aicat")}
        try:
            tx = bank_import.build_transaction(base, data["bank"], fields, ai=data.get("ai", False))
        except ValueError:
            invalid.append(index + 1)
            continue
        if account is not None:
            # money coming in through a transfer arrives on this account; everything else moves from it.
            # The preview shows amounts without sign: the direction comes from the statement row as read.
            incoming = tx.type == "transfer" and (to_decimal(base.get("amount")) or 0) > 0
            if incoming:
                tx.counter_account_id = account.id
            else:
                tx.account_id = account.id
        created.append(tx)

    db.session.add_all(created)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash(_("Alcuni movimenti risultano già importati: ricarica il file e riprova."), "error")
        return redirect(url_for("export.index"))

    message = f"{len(created)} movimenti importati da {bank_import.BANKS[data['bank']].name}"
    message += f" sul conto «{account.name}»." if account else "."
    if skipped:
        message += f" {skipped} già presenti sono stati ignorati."
    flash(message, "success")
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
        return jsonify({"error": "Nessun movimento da classificare."}), 400
    try:
        suggestions = ai_classification.classify(items, known_categories())
    except ai_extraction.AIExtractionError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({
        "model": ai_classification.model_name(),
        "suggestions": {str(i): s.to_dict() for i, s in suggestions.items()},
    })
