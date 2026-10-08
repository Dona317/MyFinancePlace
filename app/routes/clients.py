"""Clienti (F11): the archives this studio keeps, one per client; open one, add, rename, export, delete."""
from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.client import Client
from app.services import studio

clients_bp = Blueprint("clients", __name__, url_prefix="/clients")


def _client(client_id: int) -> Client:
    return db.get_or_404(Client, client_id)


@clients_bp.route("/")
def index():
    return render_template("clients/index.html", clients=studio.clients(), open_client=studio.current() or studio.primary(),
                           colors=studio.COLORS)


@clients_bp.route("/new", methods=["POST"])
def create():
    try:
        client = studio.create(request.form.get("name", ""), request.form.get("color"), request.form.get("notes"))
    except studio.StudioError as exc:
        flash(str(exc), "error")
        return redirect(url_for("clients.index"))
    studio.choose(client)
    flash(_("Cliente «%(name)s» creato con un archivio tutto suo: ora stai lavorando sui suoi dati.", name=client.name), "success")
    return redirect(url_for("dashboard.dashboard"))


@clients_bp.route("/<int:client_id>/open", methods=["POST"])
def open_client(client_id):
    client = _client(client_id)
    if client.archived:
        flash(_("«%(name)s» è archiviato: riattivalo per aprirlo.", name=client.name), "error")
        return redirect(url_for("clients.index"))
    studio.choose(client)
    flash(_("Ora stai lavorando su «%(name)s».", name=client.name), "success")
    return redirect(url_for("dashboard.dashboard"))


@clients_bp.route("/<int:client_id>/edit", methods=["POST"])
def edit(client_id):
    client = _client(client_id)
    if client is studio.current() and "archived" in request.form:
        flash(_("Non puoi archiviare il cliente aperto: aprine prima un altro."), "error")
        return redirect(url_for("clients.index"))
    try:
        studio.update(client, request.form.get("name", ""), request.form.get("color"), request.form.get("notes"),
                      "archived" in request.form)
        flash(_("Cliente «%(name)s» aggiornato.", name=client.name), "success")
    except studio.StudioError as exc:
        flash(str(exc), "error")
    return redirect(url_for("clients.index"))


@clients_bp.route("/<int:client_id>/backup")
def backup(client_id):
    client = _client(client_id)
    archive = studio.backup(client)
    name = f"myfinanceplace_{client.slug}.zip"
    return Response(archive, mimetype="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@clients_bp.route("/<int:client_id>/delete", methods=["POST"])
def delete(client_id):
    client = _client(client_id)
    if client.is_primary:
        abort(400)
    if request.form.get("confirm", "").strip() != client.name:
        flash(_("Per eliminare «%(name)s» scrivi il suo nome esatto.", name=client.name), "error")
        return redirect(url_for("clients.index"))
    name = client.name
    try:
        kept = studio.delete(client)
    except studio.StudioError as exc:
        flash(str(exc), "error")
        return redirect(url_for("clients.index"))
    flash(_("Cliente «%(name)s» eliminato. Una copia di sicurezza è in %(path)s.", name=name, path=kept.name), "success")
    return redirect(url_for("clients.index"))
