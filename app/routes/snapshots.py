from flask import flash, redirect, render_template, request, url_for
from apiflask import APIBlueprint

from app.extensions import db
from app.models.wealth import Snapshot
from app.routes.helpers import form_text
from app.services import wealth

snapshots_bp = APIBlueprint(
    "snapshots",
    __name__,
    url_prefix="/snapshots",
    tag="Snapshot"
)


def _ordered() -> list[Snapshot]:
    return Snapshot.query.order_by(Snapshot.taken_on, Snapshot.id).all()


@snapshots_bp.route("/")
def index():
    snapshots = _ordered()
    rows, previous = [], None
    for s in snapshots:
        rows.append({"snapshot": s, "delta": float(s.net_worth) - float(previous.net_worth) if previous else None})
        previous = s
    return render_template(
        "snapshots/index.html",
        rows=list(reversed(rows)),  # newest first in the table
        snapshots=snapshots,
        current=wealth.balance_sheet(),
    )


@snapshots_bp.route("/create", methods=["POST"])
def create():
    snapshot = wealth.take_snapshot(form_text("label", "Etichetta"))
    net_worth = f"{float(snapshot.net_worth):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    flash(f"Istantanea del {snapshot.taken_on.strftime('%d/%m/%Y')} salvata: patrimonio netto € {net_worth}.", "success")
    return redirect(url_for("snapshots.index"))


@snapshots_bp.route("/<int:snapshot_id>/delete", methods=["POST"])
def delete(snapshot_id):
    snapshot = db.get_or_404(Snapshot, snapshot_id)
    db.session.delete(snapshot)
    db.session.commit()
    flash("Istantanea eliminata.", "success")
    return redirect(url_for("snapshots.index"))


@snapshots_bp.route("/compare")
def compare():
    """Two snapshots side by side, line by line; with a single one, it is compared with today."""
    snapshots = _ordered()
    first = db.session.get(Snapshot, request.args.get("a", type=int) or 0)
    second = db.session.get(Snapshot, request.args.get("b", type=int) or 0)
    if first is None and snapshots:
        first = snapshots[-2] if len(snapshots) > 1 else snapshots[-1]
    if first and second and (second.taken_on, second.id) < (first.taken_on, first.id):
        first, second = second, first

    def view(s: Snapshot | None) -> dict | None:
        if s is None:
            return None
        detail = s.detail or {}
        return {"id": s.id, "title": s.label or s.taken_on.strftime("%d/%m/%Y"), "date": s.taken_on,
                "assets": detail.get("assets", {}), "liabilities": detail.get("liabilities", {}),
                "total_assets": s.total_assets, "total_liabilities": float(s.liabilities), "net_worth": float(s.net_worth)}

    left = view(first)
    if second is None:
        sheet = wealth.balance_sheet()
        right = {"id": None, "title": "Oggi", "date": sheet["date"],
                 "assets": {**sheet["current_assets"], **sheet["other_assets"]},
                 "liabilities": {**sheet["current_liabilities"], **sheet["long_liabilities"]},
                 "total_assets": sheet["total_assets"], "total_liabilities": sheet["total_liabilities"],
                 "net_worth": sheet["net_worth"]}
    else:
        right = view(second)

    lines = []
    if left:
        for section in ("assets", "liabilities"):
            names = list(dict.fromkeys(list(left[section]) + list(right[section])))
            for name in names:
                a, b = float(left[section].get(name, 0)), float(right[section].get(name, 0))
                lines.append({"section": section, "name": name, "a": a, "b": b, "diff": b - a})
    return render_template("snapshots/compare.html", snapshots=snapshots, left=left, right=right, lines=lines)
