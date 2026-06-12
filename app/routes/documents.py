from flask import Blueprint, render_template, request, redirect, url_for

documents_bp = Blueprint("documents", __name__, url_prefix="/documents")


@documents_bp.route("/")
def index():
    # TODO: fetch documents from archive
    documents = []
    return render_template("documents/index.html", documents=documents)


@documents_bp.route("/upload", methods=["POST"])
def upload():
    # TODO: handle file upload and link to transaction/category
    return redirect(url_for("documents.index"))
