from flask import render_template, request, redirect, url_for
from apiflask import APIBlueprint

snapshots_bp = APIBlueprint(
    "snapshots",
    __name__,
    url_prefix="/snapshots",
    tag="Snapshot"
)


@snapshots_bp.route("/")
def index():
    # TODO: fetch snapshot list with metadata
    snapshots = []
    return render_template("snapshots/index.html", snapshots=snapshots)


@snapshots_bp.route("/create", methods=["POST"])
def create():
    # TODO: generate and persist a new snapshot of current financial state
    return redirect(url_for("snapshots.index"))


@snapshots_bp.route("/compare")
def compare():
    # TODO: compare two snapshots side by side
    return render_template("snapshots/compare.html")
