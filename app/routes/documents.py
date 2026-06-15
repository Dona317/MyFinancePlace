from flask import render_template, request, redirect, url_for
from apiflask import APIBlueprint

documents_bp = APIBlueprint(
    "documents",
    __name__,
    url_prefix="/documents",
    tag="Documents"
)


@documents_bp.route("/")
def index():
    # TODO: fetch documents from archive
    documents = []
    return render_template("documents/index.html", documents=documents)


@documents_bp.route("/upload", methods=["POST"])
def upload():
    # TODO: handle file upload and link to transaction/category
    return redirect(url_for("documents.index"))
