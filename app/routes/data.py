"""Dati (23 Nov 2026): the data the app collects from the internet — exchange rates (Cambi) and past prices of the
holdings (Prezzi storici) — with what is missing, and the state of the update under way (the pill at the bottom)."""
from __future__ import annotations

from apiflask import APIBlueprint
from flask import flash, jsonify, redirect, render_template, url_for
from flask_babel import gettext as _

from app.routes.helpers import safe_next
from app.services import currency, fx_status, history_filler, market_data
from app.services.ui_settings import current_settings

data_bp = APIBlueprint("data", __name__, url_prefix="/dati", tag="Data")


@data_bp.route("/")
def index():
    return redirect(url_for("data.rates"))


@data_bp.route("/cambi")
def rates():
    """The currencies in use, their rates and where they are missing."""
    rows = fx_status.report()
    return render_template("data/cambi.html", rows=rows, online=current_settings()["prices_online"],
                           problems=sum(1 for r in rows if r["status"] != "ok"), base=currency.base())


@data_bp.route("/cambi/bce", methods=["POST"])
def rates_download():
    """The ECB rates of the currencies in use, now (the whole history needed the first time)."""
    try:
        done = history_filler.fill_rates()
    except (OSError, ValueError) as exc:
        flash(_("Cambi BCE non letti: %(error)s", error=str(exc)[:200]), "error")
        return redirect(url_for("data.rates"))
    if done["currencies"]:
        flash(_("Cambi BCE di %(codes)s: %(count)s nuovi.", codes=", ".join(done["currencies"]), count=done["added"]),
              "success")
    else:
        flash(_("Nessuna valuta diversa dall'euro in uso: non servono cambi."), "info")
    return redirect(url_for("data.rates"))


@data_bp.route("/prezzi")
def prices():
    """The past closes of the holdings: from when they are needed, coverage, holes, sources."""
    return render_template("data/prezzi.html", coverage=history_filler.coverage(),
                           online=current_settings()["prices_online"],
                           market=market_data.overview() if market_data.available() else [])


@data_bp.route("/aggiorna", methods=["POST"])
def update():
    """«Aggiorna ora»: prices and rates in the background; the pill at the bottom follows it."""
    if not current_settings()["prices_online"]:
        flash(_("I prezzi da internet sono spenti: accendili in Impostazioni → Dati da internet."), "warning")
    elif history_filler.run_in_background(force=True):
        flash(_("Aggiornamento dei dati avviato: lo segui in basso, puoi continuare a usare l'app."), "info")
    else:
        flash(_("Un aggiornamento è già in corso."), "info")
    return redirect(safe_next() or url_for("data.prices"))


@data_bp.route("/stato")
def state():
    """The update under way (or the last one): for the pill."""
    return jsonify(history_filler.status() or {"state": "idle"})
