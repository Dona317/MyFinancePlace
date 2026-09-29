from datetime import date

from flask import flash, redirect, render_template, request, url_for
from apiflask import APIBlueprint

from app.extensions import db
from app.models.wealth import Holding, Snapshot
from app.routes.helpers import form_choice, form_date, form_decimal, form_text
from app.services import wealth

portfolio_bp = APIBlueprint(
    "portfolio",
    __name__,
    url_prefix="/portfolio",
    tag="Portfolio"
)


def _holding_from_form(holding: Holding) -> Holding:
    holding.name = form_text("name", "Nome", required=True)
    holding.ticker = form_text("ticker", "Ticker")
    holding.asset_class = form_choice("asset_class", "Classe", wealth.ASSET_CLASSES)
    holding.quantity = form_decimal("quantity", "Quantità", required=True)
    holding.avg_price = form_decimal("avg_price", "Prezzo medio di acquisto", required=True)
    price = form_decimal("current_price", "Prezzo attuale")
    if price != holding.current_price:
        holding.price_date = date.today() if price is not None else None
    holding.current_price = price
    holding.purchase_date = form_date("purchase_date", "Data di acquisto")
    holding.notes = form_text("notes", "Note")
    return holding


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
        try:
            holding = _holding_from_form(Holding())
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("portfolio/form.html", holding=None, asset_classes=wealth.ASSET_CLASSES,
                                   values=request.form)
        db.session.add(holding)
        db.session.commit()
        flash(f"Posizione «{holding.name}» aggiunta.", "success")
        return redirect(url_for("portfolio.index"))
    return render_template("portfolio/form.html", holding=None, asset_classes=wealth.ASSET_CLASSES, values={})


@portfolio_bp.route("/<int:holding_id>/edit", methods=["GET", "POST"])
def edit(holding_id):
    holding = db.get_or_404(Holding, holding_id)
    if request.method == "POST":
        try:
            _holding_from_form(holding)
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
            return render_template("portfolio/form.html", holding=holding, asset_classes=wealth.ASSET_CLASSES,
                                   values=request.form)
        db.session.commit()
        flash(f"Posizione «{holding.name}» aggiornata.", "success")
        return redirect(url_for("portfolio.index"))
    return render_template("portfolio/form.html", holding=holding, asset_classes=wealth.ASSET_CLASSES, values={})


@portfolio_bp.route("/prices", methods=["GET", "POST"])
def prices():
    """Update the current price of every holding in one go."""
    holdings = wealth.holdings_on()
    if request.method == "POST":
        changed = 0
        try:
            for holding in holdings:
                price = form_decimal(f"price-{holding.id}", f"Prezzo di {holding.name}")
                if price is not None and price != holding.current_price:
                    holding.current_price = price
                    holding.price_date = date.today()
                    changed += 1
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
            return render_template("portfolio/prices.html", holdings=holdings, values=request.form)
        db.session.commit()
        flash(f"Prezzi aggiornati: {changed}." if changed else "Nessun prezzo cambiato.", "success")
        return redirect(url_for("portfolio.index"))
    return render_template("portfolio/prices.html", holdings=holdings, values={})


@portfolio_bp.route("/<int:holding_id>/delete", methods=["POST"])
def delete(holding_id):
    holding = db.get_or_404(Holding, holding_id)
    db.session.delete(holding)
    db.session.commit()
    flash(f"Posizione «{holding.name}» eliminata.", "success")
    return redirect(url_for("portfolio.index"))
