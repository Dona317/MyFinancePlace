from datetime import date

from apiflask import APIBlueprint
from flask import abort, flash, redirect, render_template, request, send_file, url_for
from flask_babel import gettext as _
from flask_babel import ngettext
from sqlalchemy import extract

from app.extensions import db
from app.models.transaction import Transaction
from app.models.wealth import Document
from app.routes.helpers import back_to, form_int, form_text, safe_next
from app.services import document_store
from app.services.categories import known_categories

documents_bp = APIBlueprint(
    "documents",
    __name__,
    url_prefix="/documents",
    tag="Documents"
)


def _year_choices() -> list[int]:
    this_year = date.today().year
    stored = {y for (y,) in db.session.query(Document.fiscal_year).distinct() if y}
    return sorted(stored | set(range(this_year - 5, this_year + 1)), reverse=True)


def _transaction_choices(document: Document | None) -> list[Transaction]:
    """Transactions to link the document to: those of its fiscal year (or the latest 300)."""
    query = Transaction.query
    if document and document.fiscal_year:
        query = query.filter(extract("year", Transaction.date) == document.fiscal_year)
    choices = query.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(300).all()
    if document and document.transaction and document.transaction not in choices:
        choices.insert(0, document.transaction)
    return choices


@documents_bp.route("/")
def index():
    filters = {key: request.args.get(key, "").strip() for key in ("q", "doc_type", "year", "category")}
    query = Document.query
    if filters["q"]:
        like = f"%{filters['q']}%"
        query = query.filter(Document.filename.ilike(like) | Document.notes.ilike(like))
    if filters["doc_type"]:
        query = query.filter(Document.doc_type == filters["doc_type"])
    if filters["year"].isdigit():
        query = query.filter(Document.fiscal_year == int(filters["year"]))
    if filters["category"]:
        query = query.filter(Document.category == filters["category"])
    documents = query.order_by(Document.uploaded_at.desc(), Document.id.desc()).all()
    return render_template(
        "documents/index.html",
        documents=documents,
        filters=filters,
        total=Document.query.count(),
        doc_types=document_store.DOC_TYPES,
        years=_year_choices(),
        categories=known_categories(),
        this_year=date.today().year,
    )


@documents_bp.route("/upload", methods=["POST"])
def upload():
    files = [f for f in request.files.getlist("files") if f and f.filename]
    if not files:
        flash(_("Scegli almeno un file da caricare."), "error")
        return redirect(url_for("documents.index"))
    try:
        year = form_int("fiscal_year", _("Anno fiscale"), minimum=1900, maximum=2999)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("documents.index"))
    doc_type = request.form.get("doc_type") if request.form.get("doc_type") in document_store.DOC_TYPES else None
    category = form_text("category", _("Categoria"))
    for upload_file in files:
        raw = upload_file.read()
        stored, mimetype = document_store.save(upload_file.filename, raw)
        db.session.add(Document(filename=upload_file.filename, stored_name=stored, mimetype=mimetype, size=len(raw),
                                doc_type=doc_type, fiscal_year=year, category=category))
    db.session.commit()
    flash(ngettext("%(num)s documento caricato.", "%(num)s documenti caricati.", len(files)), "success")
    return redirect(url_for("documents.index"))


@documents_bp.route("/<int:doc_id>/file")
def file(doc_id):
    """Open the document: PDFs and images in the browser, anything else downloaded."""
    document = db.get_or_404(Document, doc_id)
    try:
        path = document_store.path_of(document.stored_name)
    except FileNotFoundError:
        abort(404)
    if not path.exists():
        abort(404)
    inline = document.mimetype in document_store.INLINE_TYPES and not request.args.get("download")
    response = send_file(path, mimetype=document.mimetype or "application/octet-stream",
                         as_attachment=not inline, download_name=document.filename)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@documents_bp.route("/<int:doc_id>/edit", methods=["GET", "POST"])
def edit(doc_id):
    document = db.get_or_404(Document, doc_id)
    if request.method == "POST":
        try:
            document.filename = form_text("filename", _("Nome"), required=True)
            document.fiscal_year = form_int("fiscal_year", _("Anno fiscale"), minimum=1900, maximum=2999)
            tx_id = form_int("transaction_id", _("Transazione collegata"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
            return redirect(url_for("documents.edit", doc_id=doc_id, next=safe_next()))
        document.doc_type = request.form.get("doc_type") if request.form.get("doc_type") in document_store.DOC_TYPES else None
        document.category = form_text("category", _("Categoria"))
        document.notes = form_text("notes", _("Note"))
        document.transaction_id = tx_id if tx_id and db.session.get(Transaction, tx_id) else None
        db.session.commit()
        flash(_("Documento «%(filename)s» aggiornato.", filename=document.filename), "success")
        return back_to("documents.index")
    return render_template(
        "documents/form.html",
        document=document,
        doc_types=document_store.DOC_TYPES,
        years=_year_choices(),
        categories=known_categories(document.category),
        transactions=_transaction_choices(document),
        next_url=safe_next(),
    )


@documents_bp.route("/<int:doc_id>/delete", methods=["POST"])
def delete(doc_id):
    document = db.get_or_404(Document, doc_id)
    db.session.delete(document)
    db.session.commit()
    document_store.remove(document.stored_name)
    flash(_("Documento «%(filename)s» eliminato.", filename=document.filename), "success")
    return redirect(url_for("documents.index"))
