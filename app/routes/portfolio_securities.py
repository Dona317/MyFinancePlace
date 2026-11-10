"""
Portfolios and securities accounts (F42): the page that lists them (rename, the star of the default portfolio,
archive), a securities account's form and its own page, with its positions and its liquidity; the order register
(F46); the fee calculator.
"""
from decimal import Decimal

from flask import Response, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.securities import Portfolio, SecuritiesAccount
from app.models.wealth import Holding
from app.routes.helpers import form_decimal, form_text
from app.routes.portfolio import portfolio_bp
from app.services import accounts, fee_calculator, order_register, portfolio_ops, portfolio_overview, securities, wealth
from app.services.parsing import to_date


def _summary(positions) -> dict:
    return wealth.portfolio_summary(positions)


@portfolio_bp.route("/portfolios")
def portfolios_page():
    if securities.ensure_assigned() or Portfolio.query.filter_by(is_default=True).count() == 0:
        securities.default_portfolio()  # the star is always somewhere
        db.session.commit()
    folios = securities.portfolios(active_only=False)
    dossiers = securities.accounts(active_only=False)
    every = securities.positions()
    value_of = {p.id: sum(x.value for x in every if x.portfolio_id == p.id) for p in folios}
    rows = [{"dossier": d, "value": sum(x.value for x in every if x.securities_account_id == d.id),
             "cash": securities.cash(d)} for d in dossiers]
    return render_template("portfolio/portfolios.html", folios=folios, value_of=value_of,
                           count_of={p.id: securities.operations_count(p) for p in folios}, rows=rows,
                           nav_active="portfolios")


def _back():
    return redirect(url_for("portfolio.portfolios_page"))


@portfolio_bp.route("/portfolios/new", methods=["POST"])
def portfolio_new():
    try:
        folio = securities.save_portfolio(None, request.form.get("name", ""), request.form.get("description"))
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return _back()
    db.session.commit()
    flash(_("Portafoglio «%(name)s» creato.", name=folio.name), "success")
    return _back()


@portfolio_bp.route("/portfolios/<int:portfolio_id>/rename", methods=["POST"])
def portfolio_rename(portfolio_id):
    folio = db.get_or_404(Portfolio, portfolio_id)
    try:
        securities.save_portfolio(folio, request.form.get("name", ""), request.form.get("description"))
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return _back()
    folio.active = True
    db.session.commit()
    flash(_("Portafoglio «%(name)s» salvato.", name=folio.name), "success")
    return _back()


@portfolio_bp.route("/portfolios/<int:portfolio_id>/default", methods=["POST"])
def portfolio_default(portfolio_id):
    folio = db.get_or_404(Portfolio, portfolio_id)
    securities.set_default(folio)
    db.session.commit()
    flash(_("«%(name)s» è il portafoglio predefinito: le nuove operazioni vanno lì se non ne scegli un altro.",
            name=folio.name), "success")
    return _back()


@portfolio_bp.route("/portfolios/<int:portfolio_id>/delete", methods=["POST"])
def portfolio_delete(portfolio_id):
    folio = db.get_or_404(Portfolio, portfolio_id)
    name = folio.name
    try:
        securities.delete_portfolio(folio)
    except ValueError as exc:
        flash(str(exc), "error")
        return _back()
    archived = folio in db.session and not folio.active
    db.session.commit()
    flash(_("Portafoglio «%(name)s» archiviato: ha delle operazioni, che restano.", name=name) if archived
          else _("Portafoglio «%(name)s» eliminato.", name=name), "success")
    return _back()


# ── Securities accounts ────────────────────────────────────────────────────────

def _account_data() -> dict:
    return {"name": form_text("name", _("Nome")), "broker": form_text("broker", _("Intermediario")),
            "settlement_account_id": request.form.get("settlement_account_id", type=int),
            "tax_regime": request.form.get("tax_regime"), "abroad": bool(request.form.get("abroad")),
            "fee_fixed": form_decimal("fee_fixed", _("Commissione fissa")),
            "fee_percent": form_decimal("fee_percent", _("Commissione %")),
            "fee_min": form_decimal("fee_min", _("Commissione minima")),
            "fee_max": form_decimal("fee_max", _("Commissione massima")),
            "notes": form_text("notes", _("Note")), "active": bool(request.form.get("active"))}


def _account_form(dossier: SecuritiesAccount | None):
    values = {}
    if request.method == "POST":
        try:
            dossier = securities.save_account(dossier, _account_data())
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
            values = request.form
        else:
            db.session.commit()
            flash(_("Conto titoli «%(name)s» salvato.", name=dossier.name), "success")
            return redirect(url_for("portfolio.dossier_page", dossier_id=dossier.id))
    return render_template("portfolio/dossier_form.html", dossier=dossier, values=values,
                           settlement=[(a.id, a.name) for a in accounts.active() if a.kind not in ("debt",)],
                           regimes=securities.REGIMES), 400 if values else 200


@portfolio_bp.route("/dossiers/new", methods=["GET", "POST"])
def dossier_new():
    return _account_form(None)


@portfolio_bp.route("/dossiers/<int:dossier_id>/edit", methods=["GET", "POST"])
def dossier_edit(dossier_id):
    return _account_form(db.get_or_404(SecuritiesAccount, dossier_id))


@portfolio_bp.route("/dossiers/<int:dossier_id>")
def dossier_page(dossier_id):
    """A securities account: its positions by portfolio and its liquidity, the settlement account's balance."""
    dossier = db.get_or_404(SecuritiesAccount, dossier_id)
    if securities.ensure_assigned():
        db.session.commit()
    held = securities.positions(securities_account_id=dossier.id)
    names = {p.id: p.name for p in securities.portfolios(active_only=False)}
    cash = securities.cash(dossier)
    summary = _summary(held)
    return render_template("portfolio/dossier.html", dossier=dossier, positions=held, names=names, cash=cash,
                           summary=summary, total=summary["value"] + cash, nav_active="portfolios")


# ── The order register (F46) ───────────────────────────────────────────────────

@portfolio_bp.route("/orders")
def orders_page():
    """Every operation of every holding, filtered, with its totals; ?format=csv downloads it."""
    args = request.args
    filters = order_register.Filters(
        portfolio_id=args.get("portfolio", type=int), securities_account_id=args.get("dossier", type=int),
        holding_id=args.get("holding", type=int), kind=args.get("kind") if args.get("kind") in portfolio_ops.KINDS else None,
        start=to_date(args.get("start")), end=to_date(args.get("end")))
    found = order_register.register(filters)
    names = {"portfolios": {p.id: p.name for p in securities.portfolios(active_only=False)},
             "dossiers": {d.id: d.name for d in securities.accounts(active_only=False)}}
    if args.get("format") == "csv":
        return Response(order_register.to_csv(found, names), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=ordini.csv"})
    return render_template("portfolio/orders.html", register=found, filters=filters, names=names,
                           kinds=portfolio_ops.KINDS, nav_active="orders",
                           holdings=Holding.query.order_by(Holding.name).all())


# ── The overview (F48) ─────────────────────────────────────────────────────────

@portfolio_bp.route("/overview")
def overview_page():
    """The portfolio at a glance: value and money put in, returns, splits, models, what is coming, costs, orders."""
    if securities.ensure_assigned():
        db.session.commit()
    return render_template("portfolio/overview.html", o=portfolio_overview.overview(), nav_active="overview",
                           kinds=portfolio_ops.KINDS)


# ── The fee calculator ─────────────────────────────────────────────────────────

@portfolio_bp.route("/fees", methods=["GET", "POST"])
def fees_page():
    """What a yearly fee in basis points costs on price × quantity of each asset plus the liquidity, with TER and
    stamp duty: prefilled from the positions (all, ?portfolio= or ?dossier=), every number editable."""
    portfolio_id, dossier_id = request.values.get("portfolio", type=int), request.values.get("dossier", type=int)
    if request.method == "POST":
        result = fee_calculator.from_form(request.form)
    else:
        if securities.ensure_assigned():
            db.session.commit()
        rows, cash = fee_calculator.starting_rows(portfolio_id, dossier_id)
        result = fee_calculator.Result(rows, cash, fee_calculator.number(request.args.get("bps"), Decimal(0)))
    names = {"portfolios": {p.id: p.name for p in securities.portfolios()},
             "dossiers": {d.id: d.name for d in securities.accounts()}}
    return render_template("portfolio/fees.html", r=result, names=names, portfolio_id=portfolio_id,
                           dossier_id=dossier_id, empty_rows=fee_calculator.EMPTY_ROWS, nav_active="fees")
