import json
from datetime import date, datetime
from flask import render_template, request, redirect, url_for, flash, Response
from apiflask import APIBlueprint
from app.extensions import db
from app.services import analytics, transfer

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


@export_bp.route("/")
def index():
    return render_template("export/index.html", years=analytics.available_years())


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
