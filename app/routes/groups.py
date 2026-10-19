"""Gruppi (F21): families or groups of archives, and their consolidated view (read only)."""
import re
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.client import Client, ClientGroup
from app.routes.helpers import csv_text, download, flash_errors
from app.services import consolidation, groups, studio

groups_bp = Blueprint("groups", __name__, url_prefix="/groups")


def _group(group_id: int) -> ClientGroup:
    return db.get_or_404(ClientGroup, group_id)


def _save(group: ClientGroup | None):
    form = request.form
    with flash_errors(groups.GroupError):
        saved = groups.save(group, form.get("name", ""), form.get("color"), form.get("notes"), form.getlist("members"))
        flash(_("Gruppo «%(name)s» salvato.", name=saved.name), "success")
        return redirect(url_for("groups.consolidated", group_id=saved.id))
    return redirect(url_for("groups.index"))


@groups_bp.route("/")
def index():
    return render_template("groups/index.html", groups=groups.all_groups(), clients=studio.clients(), colors=studio.COLORS)


@groups_bp.route("/new", methods=["POST"])
def create():
    return _save(None)


@groups_bp.route("/<int:group_id>/edit", methods=["POST"])
def edit(group_id):
    return _save(_group(group_id))


@groups_bp.route("/<int:group_id>/delete", methods=["POST"])
def delete(group_id):
    group = _group(group_id)
    name = group.name
    groups.delete(group)
    flash(_("Gruppo «%(name)s» eliminato: gli archivi restano com'erano.", name=name), "success")
    return redirect(url_for("groups.index"))


@groups_bp.route("/<int:group_id>")
def consolidated(group_id):
    return render_template("groups/consolidated.html", data=consolidation.consolidate(_group(group_id)))


@groups_bp.route("/<int:group_id>/csv")
def export_csv(group_id):
    data = consolidation.consolidate(_group(group_id))
    slug = re.sub(r"[^a-z0-9]+", "_", data["group"].name.lower()).strip("_") or "gruppo"
    name = f"consolidato_{slug}_{date.today():%Y%m%d}.csv"
    return download(csv_text(consolidation.csv_rows(data)), name, "text/csv; charset=utf-8")


@groups_bp.route("/<int:group_id>/open/<int:client_id>", methods=["POST"])
def open_member(group_id, client_id):
    """Go to a member's own archive, to look at a number in detail."""
    client = db.get_or_404(Client, client_id)
    if client.archived:
        flash(_("«%(name)s» è archiviato: riattivalo per aprirlo.", name=client.name), "error")
        return redirect(url_for("groups.consolidated", group_id=group_id))
    studio.choose(client)
    flash(_("Ora stai lavorando su «%(name)s».", name=client.name), "success")
    return redirect(url_for("dashboard.dashboard"))
