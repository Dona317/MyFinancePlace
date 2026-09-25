import json
from datetime import date, datetime
from flask import render_template, request, redirect, url_for, flash, Response, current_app
from apiflask import APIBlueprint
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models.transaction import Transaction
from app.services import analytics, transfer, bank_import, ai_extraction

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


def _known_categories() -> list[str]:
    defaults = ["Casa", "Alimentari", "Trasporto", "Salute", "Svago", "Abbonamenti", "Stipendio",
                "Freelance", "Investimenti", "Rimborsi", "Commissioni", "Giroconto", "Altro"]
    stored = [c for (c,) in db.session.query(Transaction.category).filter(Transaction.category.isnot(None)).distinct()]
    return sorted(set(defaults) | set(stored))


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

@export_bp.route("/bank", methods=["POST"])
def bank_preview():
    """Step 1: parse the uploaded statement and show a reviewable preview."""
    upload = request.files.get("file")
    if not upload or not upload.filename:
        flash("Seleziona l'estratto conto da importare.", "error")
        return redirect(url_for("export.index"))

    bank = request.form.get("bank", bank_import.AUTO)
    try:
        preview = bank_import.analyze_statement(upload.filename, upload.read(), bank)
    except bank_import.StatementImportError as exc:
        flash(str(exc), "error")
        return redirect(url_for("export.index"))

    payload = _preview_serializer().dumps({
        "bank": preview.bank.key,
        "ai": bool(preview.ai_model),
        "rows": [row.to_dict() for row in preview.rows],
    })
    return render_template(
        "export/bank_preview.html",
        preview=preview,
        payload=payload,
        filename=upload.filename,
        categories=_known_categories(),
    )


@export_bp.route("/bank/confirm", methods=["POST"])
def bank_confirm():
    """Step 2: create transactions for the rows the user kept, with their edited category/type."""
    try:
        data = _preview_serializer().loads(request.form.get("payload", ""))
    except BadSignature:
        flash("Anteprima non valida o scaduta: carica di nuovo il file.", "error")
        return redirect(url_for("export.index"))

    rows = data["rows"]
    selected = {int(i) for i in request.form.getlist("include") if i.isdigit() and int(i) < len(rows)}
    refs = [rows[i]["import_ref"] for i in selected]
    existing = {
        ref for (ref,) in
        Transaction.query.with_entities(Transaction.import_ref).filter(Transaction.import_ref.in_(refs))
    } if refs else set()

    created = []
    for index in sorted(selected):
        row = dict(rows[index])
        if row["import_ref"] in existing:
            continue
        tx_type = request.form.get(f"type-{index}")
        if tx_type in ("income", "expense", "transfer"):
            row["type"] = tx_type
        created.append(bank_import.build_transaction(
            row, data["bank"], request.form.get(f"category-{index}"), ai=data.get("ai", False)
        ))

    db.session.add_all(created)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Alcuni movimenti risultano già importati: ricarica il file e riprova.", "error")
        return redirect(url_for("export.index"))

    skipped = len(selected) - len(created)
    message = f"{len(created)} movimenti importati da {bank_import.BANKS[data['bank']].name}."
    if skipped:
        message += f" {skipped} già presenti sono stati ignorati."
    flash(message, "success")
    return redirect(url_for("transactions.index"))
