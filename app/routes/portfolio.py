from datetime import date

from apiflask import APIBlueprint
from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.wealth import Holding, HoldingPrice, Snapshot
from app.routes.helpers import delete_and_redirect, form_choice, form_date, form_decimal, form_text, save_form
from app.services import display, price_feed, wealth
from app.services.ui_settings import current_settings

portfolio_bp = APIBlueprint(
    "portfolio",
    __name__,
    url_prefix="/portfolio",
    tag="Portfolio"
)


def _holding_from_form(holding: Holding) -> Holding:
    holding.name = form_text("name", _("Nome"), required=True)
    holding.ticker = form_text("ticker", _("Ticker"))
    holding.asset_class = form_choice("asset_class", _("Classe"), wealth.ASSET_CLASSES)
    holding.quantity = form_decimal("quantity", _("Quantità"), required=True)
    holding.avg_price = form_decimal("avg_price", _("Prezzo medio di acquisto"), required=True)
    price = form_decimal("current_price", _("Prezzo attuale"))
    if price is not None and price != holding.current_price and holding.id is not None:
        wealth.record_price(holding, price)  # a new price of an existing holding goes into its history
    elif price != holding.current_price:
        holding.price_date = date.today() if price is not None else None
    holding.current_price = price
    holding.purchase_date = form_date("purchase_date", _("Data di acquisto"))
    holding.notes = form_text("notes", _("Note"))
    rate = form_decimal("tax_rate", _("Aliquota sulle plusvalenze"))
    if rate is not None and not 0 < rate <= 100:
        raise ValueError(_("Aliquota sulle plusvalenze: indica una percentuale tra 0 e 100 (es. 12,5)."))
    holding.tax_rate = rate
    holding.abroad = "abroad" in request.form
    return holding


def _render_form(holding, values):
    return render_template("portfolio/form.html", holding=holding, asset_classes=wealth.ASSET_CLASSES, values=values)


@portfolio_bp.route("/")
def index():
    selected = request.args.get("asset_class", "")
    holdings = wealth.holdings_on()
    today = date.today()
    snapshots = Snapshot.query.order_by(Snapshot.taken_on, Snapshot.id).all()
    return render_template(
        "portfolio/index.html",
        holdings=[h for h in holdings if not selected or h.asset_class == selected],
        summary=wealth.portfolio_summary(holdings),
        dividends_ytd=wealth.dividends(date(today.year, 1, 1), date(today.year + 1, 1, 1)),
        asset_classes=wealth.ASSET_CLASSES,
        selected=selected,
        trend={"labels": [s.taken_on.strftime("%d/%m/%y") for s in snapshots],
               "data": [float(s.investments) for s in snapshots]},
    )


@portfolio_bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        return save_form(Holding(), _holding_from_form, _render_form,
                         lambda h: _("Posizione «%(name)s» aggiunta.", name=h.name), lambda h: url_for("portfolio.index"))
    return _render_form(None, {})


@portfolio_bp.route("/<int:holding_id>/edit", methods=["GET", "POST"])
def edit(holding_id):
    holding = db.get_or_404(Holding, holding_id)
    if request.method == "POST":
        return save_form(holding, _holding_from_form, _render_form,
                         lambda h: _("Posizione «%(name)s» aggiornata.", name=h.name), lambda h: url_for("portfolio.index"))
    return _render_form(holding, {})


@portfolio_bp.route("/prices", methods=["GET", "POST"])
def prices():
    """Update the current price of every holding in one go."""
    holdings = wealth.holdings_on()
    if request.method == "POST":
        changed = 0
        try:
            on = form_date("on", _("Data dei prezzi")) or date.today()
            if on > date.today():
                raise ValueError(_("La data dei prezzi non può essere nel futuro."))
            for holding in holdings:
                price = form_decimal(f"price-{holding.id}", _("Prezzo di %(name)s", name=holding.name))
                if price is not None and price > 0:
                    wealth.record_price(holding, price, on)
                    changed += 1
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
            return render_template("portfolio/prices.html", holdings=holdings, values=request.form, today=date.today(),
                                   online=current_settings()["prices_online"], supported=price_feed.supported)
        db.session.commit()
        flash(_("Prezzi aggiornati: %(changed)s.", changed=changed) if changed else _("Nessun prezzo cambiato."), "success")
        return redirect(url_for("portfolio.index"))
    return render_template("portfolio/prices.html", holdings=holdings, values={}, today=date.today(),
                           online=current_settings()["prices_online"], supported=price_feed.supported)


@portfolio_bp.route("/prices/online", methods=["POST"])
def prices_online():
    """Read today's prices from the internet (when turned on in Settings) and record them."""
    if not current_settings()["prices_online"]:
        flash(_("I prezzi da internet sono spenti: accendili in Impostazioni → Dati da internet."), "warning")
        return redirect(url_for("portfolio.prices"))
    results = price_feed.update_all(wealth.holdings_on())
    db.session.commit()
    updated = [r for r in results if r.error is None]
    if updated:
        flash(_("Prezzi aggiornati da internet: %(names)s.", names=", ".join(
            f"{r.holding.name} {display.money(r.price)}" for r in updated)), "success")
    for r in (r for r in results if r.error):
        flash(_("%(name)s: %(error)s", name=r.holding.name, error=r.error), "warning")
    if not results:
        flash(_("Nessuna posizione con un ticker da cercare: ETF, azioni, obbligazioni, fondi o cripto con il ticker compilato."), "warning")
    return redirect(url_for("portfolio.prices"))


@portfolio_bp.route("/<int:holding_id>/history", methods=["GET", "POST"])
def history(holding_id):
    """The holding's price history: add one price, or paste many lines «date;price»."""
    holding = db.get_or_404(Holding, holding_id)
    if request.method == "POST":
        try:
            if request.form.get("lines", "").strip():
                points, unread = wealth.parse_prices(request.form["lines"])
            else:
                when = form_date("on", _("Data"), required=True)
                price = form_decimal("price", _("Prezzo"), required=True)
                if price <= 0:
                    raise ValueError(_("Il prezzo deve essere maggiore di zero."))
                points, unread = [(when, price)], []
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("portfolio.history", holding_id=holding.id))
        for when, price in points:
            wealth.record_price(holding, price, when)
        db.session.commit()
        if points:
            flash(_("Prezzi salvati: %(count)s.", count=len(points)), "success")
        if unread:
            flash(_("Righe non lette: %(lines)s", lines=" · ".join(unread[:5])), "warning")
        return redirect(url_for("portfolio.history", holding_id=holding.id))
    points = wealth.price_history(holding)
    return render_template("portfolio/history.html", holding=holding, points=points,
                           chart={"labels": [p.on.isoformat() for p in points], "data": [float(p.price) for p in points]})


@portfolio_bp.route("/prices/<int:point_id>/delete", methods=["POST"])
def delete_price(point_id):
    point = db.get_or_404(HoldingPrice, point_id)
    holding_id = point.holding_id
    wealth.remove_price(point)
    db.session.commit()
    flash(_("Prezzo eliminato."), "success")
    return redirect(url_for("portfolio.history", holding_id=holding_id))


@portfolio_bp.route("/<int:holding_id>/delete", methods=["POST"])
def delete(holding_id):
    holding = db.get_or_404(Holding, holding_id)
    return delete_and_redirect(holding, _("Posizione «%(name)s» eliminata.", name=holding.name), url_for("portfolio.index"))
