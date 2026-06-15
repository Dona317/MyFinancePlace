from flask import render_template, request, send_file
from apiflask import APIBlueprint

export_bp = APIBlueprint(
    "export",
    __name__,
    url_prefix="/export",
    tag="Export"
)


@export_bp.route("/")
def index():
    return render_template("export/index.html")


@export_bp.route("/csv")
def export_csv():
    # TODO: generate CSV export and stream to client
    pass


@export_bp.route("/json")
def export_json():
    # TODO: generate JSON export and stream to client
    pass


@export_bp.route("/pdf")
def export_pdf():
    # TODO: generate PDF report and stream to client
    pass


@export_bp.route("/tax/<int:year>")
def export_tax(year):
    # TODO: generate tax export for the given fiscal year
    pass
