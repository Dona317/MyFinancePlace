import re
from datetime import date
from decimal import Decimal

from apiflask import APIBlueprint
from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.wealth import Holding, HoldingPrice, Snapshot
from app.routes.helpers import delete_and_redirect, form_choice, form_date, form_decimal, form_text, save_form
from app.services import accounts, broker, display, portfolio_ops, price_feed, wealth
from app.services.i18n import _l
from app.services.ui_settings import current_settings

portfolio_bp = APIBlueprint(
    "portfolio",
    __name__,
    url_prefix="/portfolio",
    tag="Portfolio"
)


SOURCE_LABELS = {"auto": _l("Automatica"), "yahoo": "Yahoo Finance", "stooq": "Stooq", "coingecko": "CoinGecko",
                 "justetf": "justETF", "borsaitaliana": "Borsa Italiana", "morningstar": "Morningstar",
                 "manual": _l("Solo a mano")}


def _instrument_from_form(holding: Holding) -> None:
    """ISIN, quote currency, exchange, multiplier and where the price comes from (F19)."""
    isin = (form_text("isin", "ISIN") or "").replace(" ", "").upper() or None
    if isin and not price_feed.ISIN.match(isin):
        raise ValueError(_("ISIN: 12 caratteri, due lettere del paese e poi lettere e cifre (es. IE00BK5BQT80)."))
    holding.isin = isin
    code = (form_text("currency", _("Valuta")) or "").upper() or None
    if code and not re.fullmatch(r"[A-Z]{3}", code):
        raise ValueError(_("Valuta: il codice di tre lettere (EUR, USD, GBP…)."))
    holding.currency = code
    holding.exchange = form_text("exchange", _("Borsa"))
    multiplier = form_decimal("multiplier", _("Moltiplicatore"))
    multiplier = Decimal(1) if multiplier is None else multiplier
    if multiplier <= 0:
        raise ValueError(_("Moltiplicatore: un numero maggiore di zero (1 per azioni ed ETF, es. 100 per un'opzione)."))
    holding.multiplier = multiplier
    holding.price_source = form_choice("price_source", _("Fonte del prezzo"), SOURCE_LABELS) \
        if request.form.get("price_source") else "auto"


def _holding_from_form(holding: Holding) -> Holding:
    holding.name = form_text("name", _("Nome"), required=True)
    holding.ticker = form_text("ticker", _("Ticker"))
    holding.asset_class = form_choice("asset_class", _("Classe"), wealth.ASSET_CLASSES)
    _instrument_from_form(holding)
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
    # quantity and average price typed here are the opening position: the operations recorded move it from there
    holding.opening_quantity, holding.opening_price = holding.quantity, holding.avg_price
    holding.opening_date = holding.purchase_date
    if holding.id is not None:
        portfolio_ops.recompute(holding)
    return holding


def _render_form(holding, values):
    return render_template("portfolio/form.html", holding=holding, asset_classes=wealth.ASSET_CLASSES, values=values,
                           sources=SOURCE_LABELS, online=current_settings()["prices_online"])


@portfolio_bp.route("/")
def index():
    price_feed.refresh_in_background()  # the day's prices, once a day (when turned on)
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


@portfolio_bp.route("/<int:holding_id>")
def detail(holding_id):
    """One holding: its value and returns, its price, its operations."""
    holding = db.get_or_404(Holding, holding_id)
    points = wealth.price_history(holding)
    return render_template("portfolio/detail.html", holding=holding, operations=portfolio_ops.operations(holding),
                           financed=[row for row in wealth.financed_assets() if row["holding"].id == holding.id],
                           perf=portfolio_ops.performance([holding]), kinds=portfolio_ops.KINDS,
                           kind_of=portfolio_ops.kind_of,
                           chart={"labels": [p.on.isoformat() for p in points], "data": [float(p.price) for p in points]})


def _operation_from_form() -> portfolio_ops.Operation:
    kind = form_choice("kind", _("Operazione"), portfolio_ops.KINDS)
    account_id = request.form.get("account_id", type=int)
    on = form_date("on", _("Data"), required=True)
    if on > date.today():
        raise ValueError(_("La data non può essere nel futuro."))
    trade = kind in ("buy", "sell")
    return portfolio_ops.Operation(
        kind, on, db.session.get(Account, account_id) if account_id else None,
        units=form_decimal("units", _("Quote")) if trade else None,
        price=form_decimal("price", _("Prezzo per quota")) if trade else None,
        amount=None if trade else form_decimal("amount", _("Importo")),
        fee=form_decimal("fee", _("Commissione")) if trade else None,
        notes=form_text("notes", _("Note")))


@portfolio_bp.route("/<int:holding_id>/operation", methods=["GET", "POST"])
def operation(holding_id):
    """A purchase, sale, dividend, coupon, commission or tax of the holding, saved as transactions."""
    holding = db.get_or_404(Holding, holding_id)
    values = {}
    if request.method == "POST":
        try:
            op = _operation_from_form()
            created = portfolio_ops.record(holding, op)
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
            values = request.form
        else:
            flash(_("%(kind)s registrata: %(description)s.", kind=portfolio_ops.KINDS[op.kind], description=created[0].description),
                  "success")
            return redirect(url_for("portfolio.detail", holding_id=holding.id))
    active = accounts.active()
    return render_template("portfolio/operation.html", holding=holding, values=values, today=date.today(),
                           kinds=portfolio_ops.KINDS, accounts=[(a.id, a.name) for a in active],
                           fee_rules=broker.rules(active)), 400 if values else 200


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


@portfolio_bp.route("/lookup")
def lookup():
    """ISIN, ticker or name → the instruments found (to fill the form); only with prices from the internet on."""
    if not current_settings()["prices_online"]:
        return jsonify({"error": _("La ricerca usa internet: accendila in Impostazioni → Dati da internet."),
                        "results": []}), 403
    found, errors = price_feed.search(request.args.get("q", "")[:60])
    if not found and errors:
        return jsonify({"error": _("Ricerca non riuscita: %(error)s", error=" · ".join(errors)), "results": []}), 502
    return jsonify({"results": [c.as_dict() | {"source_name": SOURCE_LABELS.get(c.source, c.source)} for c in found[:10]],
                    "errors": errors})


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


# registers the broker import, link, model portfolio, rule and PAC routes on portfolio_bp
from app.routes import portfolio_import, portfolio_rules, portfolio_templates  # noqa: E402,F401
