import json
import math
from datetime import date, datetime
from flask import render_template, request, redirect, url_for, flash, Response, current_app, jsonify
from apiflask import APIBlueprint
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models.transaction import Transaction
from app.services import analytics, transfer, bank_import, ai_classification, ai_extraction, ai_models, upload_store
from app.services.categories import known_categories

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
    )


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
    """Print-ready report; the browser's "Save as PDF" produces the final file."""
    year = request.args.get("year", type=int) or date.today().year
    return render_template(
        "export/report.html",
        year=year,
        statement=analytics.income_statement(year),
        cash_flow=analytics.cash_flow(year),
        generated_at=datetime.now(),
    )


@export_bp.route("/tax/<int:year>")
def export_tax(year):
    transactions = [
        tx for tx in transfer.query_transactions(date(year, 1, 1), date(year + 1, 1, 1))
        if transfer.is_tax_relevant(tx)
    ]
    content = "\ufeff" + transfer.to_csv(transactions)
    return _download(content, f"fiscale_{year}.csv", "text/csv; charset=utf-8")


@export_bp.route("/import", methods=["POST"])
def import_csv():
    upload = request.files.get("file")
    if not upload or not upload.filename:
        flash("Seleziona un file CSV da importare.", "error")
        return redirect(url_for("export.index"))
    if not upload.filename.lower().endswith(".csv"):
        flash("Formato non supportato: carica un file .csv (da Excel: File → Salva come → CSV).", "error")
        return redirect(url_for("export.index"))

    raw = upload.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("latin-1")

    headers, rows = transfer.read_csv(content)
    mapping = {
        field: request.form.get(f"col_{field}") or None
        for field in ("date", "amount", "description", "category", "type", "counterparty")
    }
    missing = [f for f in ("date", "amount", "description") if mapping[f] not in headers]
    if missing:
        flash(f"Colonne obbligatorie non mappate: {', '.join(missing)}.", "error")
        return redirect(url_for("export.index"))

    transactions, errors = transfer.rows_to_transactions(rows, mapping)
    if errors:
        preview = "; ".join(errors[:5]) + (" …" if len(errors) > 5 else "")
        flash(f"Importazione annullata, {len(errors)} righe non valide — {preview}", "error")
        return redirect(url_for("export.index"))

    db.session.add_all(transactions)
    db.session.commit()
    flash(f"{len(transactions)} transazioni importate con successo.", "success")
    return redirect(url_for("transactions.index"))


# ── Bank statement import (Fineco, Intesa Sanpaolo, generic) ───────────────────
#
#  upload ──▶ rule-based reading ──ok──▶ editable preview ──▶ confirm (save)
#                   │ fails
#                   ▼
#          "Read it with AI?" (user decides, picks the model) ──yes──▶ editable preview ──▶ confirm

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
        ai_classifier=ai_classification.describe(),
        ai_cloud=ai_extraction.provider() == "anthropic",
    )


@export_bp.route("/bank", methods=["POST"])
def bank_preview():
    """Step 1: parse the uploaded statement and show an editable preview (or ask about AI reading)."""
    upload = request.files.get("file")
    if not upload or not upload.filename:
        flash("Seleziona l'estratto conto da importare.", "error")
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
                             for n in dict.fromkeys([choices["current"], "claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"])]
    return choices


@export_bp.route("/bank/ai/<token>", methods=["GET", "POST"])
def bank_ai(token):
    """Ask before reading an unreadable file with AI; on POST, read it with the chosen model."""
    try:
        raw, meta = upload_store.load(token)
    except KeyError:
        flash("Il file non è più disponibile: caricalo di nuovo.", "error")
        return redirect(url_for("export.index"))

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
            try:
                preview = bank_import.analyze_with_ai(meta["filename"], raw, meta.get("bank", bank_import.AUTO), model)
            except bank_import.StatementImportError as exc:
                error = str(exc)  # stay on this page: the user can try another model
            else:
                upload_store.delete(token)
                return _render_preview(preview, meta["filename"])

    return render_template(
        "export/ai_confirm.html", token=token, meta=meta, needs_vision=needs_vision,
        choices=choices, error=error, size_kb=len(raw) // 1024,
    )


@export_bp.route("/bank/ai/<token>/cancel", methods=["POST"])
def bank_ai_cancel(token):
    upload_store.delete(token)
    flash("Importazione annullata.", "success")
    return redirect(url_for("export.index"))


@export_bp.route("/bank/confirm", methods=["POST"])
def bank_confirm():
    """Step 2: save the rows the user kept, with every field as edited in the preview."""
    try:
        data = _preview_serializer().loads(request.form.get("payload", ""))
    except BadSignature:
        flash("Anteprima non valida o scaduta: carica di nuovo il file.", "error")
        return redirect(url_for("export.index"))

    rows = data["rows"]
    selected = sorted({int(i) for i in request.form.getlist("include") if i.isdigit() and int(i) < 5000})
    refs = [rows[i]["import_ref"] for i in selected if i < len(rows)]
    existing = {
        ref for (ref,) in
        Transaction.query.with_entities(Transaction.import_ref).filter(Transaction.import_ref.in_(refs))
    } if refs else set()

    created, invalid, skipped = [], [], 0
    for index in selected:
        base = rows[index] if index < len(rows) else {}  # indexes past the payload are rows added by hand
        if base.get("import_ref") in existing:
            skipped += 1
            continue
        fields = {name: request.form.get(f"{name}-{index}", "") for name in
                  ("date", "description", "amount", "type", "category", "counterparty", "aicat")}
        try:
            created.append(bank_import.build_edited_transaction(base, fields, data["bank"], ai=data.get("ai", False)))
        except ValueError:
            invalid.append(index + 1)

    db.session.add_all(created)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Alcuni movimenti risultano già importati: ricarica il file e riprova.", "error")
        return redirect(url_for("export.index"))

    message = f"{len(created)} movimenti importati da {bank_import.BANKS[data['bank']].name}."
    if skipped:
        message += f" {skipped} già presenti sono stati ignorati."
    flash(message, "success")
    if invalid:
        flash(f"Righe non salvate perché incomplete o non valide: {', '.join(map(str, invalid))}.", "warning")
    return redirect(url_for("transactions.index"))


@export_bp.route("/bank/classify", methods=["POST"])
def bank_classify():
    """Suggest category and counterparty for preview rows (JSON in, JSON out); nothing is saved here."""
    body = request.get_json(silent=True)
    rows = body.get("rows") if isinstance(body, dict) else None
    items = []
    for row in rows[:1000] if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            amount = float(row.get("amount") or 0)
            items.append({"id": int(row["index"]), "text": str(row.get("text") or "")[:500],
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
