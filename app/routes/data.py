"""Dati (23 Nov 2026): the data the app collects from the internet — exchange rates (Cambi) and past prices of the
holdings (Prezzi storici) — with what is missing, and the state of the update under way (the pill at the bottom)."""
from __future__ import annotations

import io
from datetime import date

from apiflask import APIBlueprint
from flask import flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_babel import gettext as _

from app.routes.helpers import safe_next, uploaded_file
from app.services import currency, fx_status, history_filler, history_links, market_data
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
                           online=current_settings()["prices_online"], links=history_links.links(),
                           store=market_data.totals(), seed=market_data.seed_path() is not None,
                           market=market_data.overview() if market_data.available() else [])


@data_bp.route("/prezzi/link", methods=["POST"])
def price_link():
    """«Incolla il link»: the page of an instrument on justETF, Borsa Italiana, Morningstar…; its history read now
    from justETF by the ISIN, and the link saved with the instrument for the daily update."""
    back = redirect(url_for("data.prices") + "#paste-link")
    if not current_settings()["prices_online"]:
        flash(_("I prezzi da internet sono spenti: accendili in Impostazioni → Dati da internet."), "warning")
        return back
    symbol = request.form.get("symbol", "").strip().upper()
    try:
        done = history_links.apply(symbol, request.form.get("url", ""))
    except ValueError as exc:
        flash(str(exc), "error")
        return back
    except OSError as exc:
        flash(_("Storico non letto da justETF: %(error)s", error=str(exc)[:200]), "error")
        return back
    via = "" if done.link.direct else _(" (link di %(site)s, letto da justETF con l'ISIN %(isin)s)",
                                          site=done.link.name, isin=done.link.isin)
    flash(_("%(symbol)s: %(count)s chiusure lette, dal %(first)s al %(last)s%(via)s. Il link resta salvato: "
            "l'aggiornamento di ogni giorno lo rilegge.", symbol=symbol, count=done.added,
            first=done.first.strftime("%d/%m/%Y"), last=done.last.strftime("%d/%m/%Y"), via=via), "success")
    return back


@data_bp.route("/prezzi/link/togli", methods=["POST"])
def price_link_forget():
    history_links.forget(request.form.get("symbol", "").strip().upper())
    flash(_("Link tolto: lo storico già letto resta."), "info")
    return redirect(url_for("data.prices") + "#paste-link")


@data_bp.route("/prezzi/esporta")
def prices_export():
    """F113: the whole price database (every archive's instruments, closes and links) as a zip of two CSV files."""
    if not market_data.available() or not market_data.totals()["instruments"]:
        flash(_("Il database dei prezzi è ancora vuoto: non c'è niente da esportare."), "info")
        return redirect(url_for("data.prices") + "#store")
    return send_file(io.BytesIO(market_data.export_zip()), mimetype="application/zip", as_attachment=True,
                     download_name=f"MyFinancePlace_prezzi_{date.today():%Y-%m-%d}.zip")


@data_bp.route("/prezzi/importa", methods=["POST"])
def prices_import():
    """F113: a price database exported (here or on another computer) added to this one: nothing already here is
    removed or changed."""
    back = redirect(url_for("data.prices") + "#store")
    upload = uploaded_file()
    if upload is None:
        flash(_("Scegli il file .zip esportato da «Esporta il database»."), "error")
        return back
    try:
        done = market_data.import_zip(upload.read())
    except ValueError as exc:
        flash(_("File non letto: %(error)s", error=str(exc)[:200]), "error")
        return back
    flash(_("Database dei prezzi importato: %(instruments)s titoli nuovi, %(closes)s chiusure nuove, %(kept)s già "
            "presenti lasciate come erano.", instruments=done.instruments, closes=done.closes, kept=done.kept),
          "success")
    if done.skipped:
        flash(_("%(count)s righe non leggibili saltate.", count=done.skipped), "warning")
    return back


@data_bp.route("/prezzi/partenza", methods=["POST"])
def prices_seed():
    """F114: the starting price database shipped with the app added to the store (what is there is kept)."""
    back = redirect(url_for("data.prices") + "#store")
    path = market_data.seed_path()
    if path is None:
        flash(_("Questa installazione non ha il database di partenza."), "error")
        return back
    done = market_data.import_zip(path.read_bytes())
    flash(_("Database di partenza importato: %(instruments)s titoli nuovi, %(closes)s chiusure nuove, %(kept)s già "
            "presenti lasciate come erano.", instruments=done.instruments, closes=done.closes, kept=done.kept),
          "success")
    return back


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
