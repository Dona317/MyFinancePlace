"""
Model portfolios and rebalancing (F19d), on the portfolio's blueprint: the templates (own ones and ready ones to
copy), the one active, what to buy or sell to get back to it, and those orders confirmed once executed.
"""
from datetime import date
from decimal import Decimal

from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.portfolio_model import PortfolioTemplate
from app.models.securities import Portfolio, SecuritiesAccount
from app.models.wealth import Holding
from app.routes.portfolio import portfolio_bp
from app.services import accounts, broker, portfolio_ops, securities
from app.services import portfolio_models as models
from app.services.parsing import to_date, to_decimal

EMPTY_SLOTS = 3  # blank rows offered under the template's slots


@portfolio_bp.route("/models")
def models_index():
    templates = PortfolioTemplate.query.order_by(PortfolioTemplate.active.desc(), PortfolioTemplate.name).all()
    return render_template("portfolio/models.html", templates=templates, ready=models.READY)


@portfolio_bp.route("/models/ready/<key>", methods=["POST"])
def models_copy(key):
    if key not in models.READY:
        flash(_("Modello pronto sconosciuto."), "error")
        return redirect(url_for("portfolio.models_index"))
    template = models.copy_ready(key)
    db.session.commit()
    flash(_("«%(name)s» copiato: cambialo come vuoi. È un esempio, non un consiglio d'investimento.", name=template.name),
          "success")
    return redirect(url_for("portfolio.models_edit", template_id=template.id))


def _slots_from_form() -> list[models.SlotInput]:
    slots = []
    for index in range(int(request.form.get("rows", 0) or 0)):
        label = (request.form.get(f"label-{index}") or "").strip()
        target = to_decimal(request.form.get(f"target-{index}"))
        if not label and target is None:
            continue  # an empty row
        if not label or target is None:
            raise models.TemplateError(_("Ogni parte ha bisogno di un nome e di un obiettivo in %."))
        slots.append(models.SlotInput(label, target, request.form.get(f"class-{index}"), request.form.get(f"isin-{index}"),
                                      request.form.get(f"ticker-{index}"),
                                      [int(h) for h in request.form.getlist(f"holdings-{index}") if h.isdigit()]))
    return slots


def _rows(template: PortfolioTemplate | None) -> list[dict]:
    """The slot rows of the form: what was posted (after an error) or the template's, plus blank ones."""
    if request.method == "POST":
        rows = [{"label": request.form.get(f"label-{i}", ""), "target": request.form.get(f"target-{i}", ""),
                 "class": request.form.get(f"class-{i}", ""), "isin": request.form.get(f"isin-{i}", ""),
                 "ticker": request.form.get(f"ticker-{i}", ""),
                 "holdings": {int(h) for h in request.form.getlist(f"holdings-{i}") if h.isdigit()}}
                for i in range(int(request.form.get("rows", 0) or 0))]
        rows = [r for r in rows if r["label"] or r["target"]]
    else:
        rows = [{"label": s.label, "target": f"{s.target.normalize():f}".replace(".", ","), "class": s.asset_class or "",
                 "isin": s.isin or "", "ticker": s.ticker or "", "holdings": s.holding_ids}
                for s in (template.slots if template else [])]
    return rows + [{"label": "", "target": "", "class": "", "isin": "", "ticker": "", "holdings": set()}] * EMPTY_SLOTS


def _page(template: PortfolioTemplate | None):
    values = request.form if request.method == "POST" else {
        "name": template.name if template else "", "description": (template.description or "") if template else "",
        "band": f"{(template.band if template else Decimal(5)).normalize():f}".replace(".", ","),
        "portfolio_id": str(template.portfolio_id or "") if template else request.args.get("portfolio", "")}
    return render_template("portfolio/model_form.html", template=template, values=values, rows=_rows(template),
                           holdings=models.investments(), classes=models.investment_classes(),
                           folios=securities.portfolios())


def _form(template: PortfolioTemplate | None):
    if request.method == "GET":
        return _page(template)
    is_new = template is None
    target = template or PortfolioTemplate(active=False)
    folio = db.session.get(Portfolio, request.form.get("portfolio_id", type=int) or 0)
    moved = not is_new and target.portfolio_id != (folio.id if folio else None)
    try:
        with db.session.no_autoflush:
            if is_new:
                db.session.add(target)
            target.portfolio_id = folio.id if folio else None
            # F50: the first model of a portfolio (or of all the investments) becomes its active one
            if is_new or moved:
                target.active = models.active(target.portfolio_id) is None
            models.save(target, request.form.get("name", ""), request.form.get("description"),
                        to_decimal(request.form.get("band")), _slots_from_form())
    except models.TemplateError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return _page(None if is_new else db.session.get(PortfolioTemplate, template.id))
    db.session.commit()
    flash(_("Portafoglio modello salvato."), "success")
    return redirect(url_for("portfolio.rebalance", portfolio=target.portfolio_id) if target.active
                    else url_for("portfolio.models_index"))


@portfolio_bp.route("/models/new", methods=["GET", "POST"])
def models_new():
    return _form(None)


@portfolio_bp.route("/models/<int:template_id>", methods=["GET", "POST"])
def models_edit(template_id):
    return _form(db.get_or_404(PortfolioTemplate, template_id))


@portfolio_bp.route("/models/<int:template_id>/activate", methods=["POST"])
def models_activate(template_id):
    template = db.get_or_404(PortfolioTemplate, template_id)
    models.activate(template)
    db.session.commit()
    flash(_("«%(name)s» è ora il portafoglio modello di riferimento.", name=template.name), "success")
    return redirect(url_for("portfolio.rebalance", portfolio=template.portfolio_id))


@portfolio_bp.route("/models/<int:template_id>/delete", methods=["POST"])
def models_delete(template_id):
    template = db.get_or_404(PortfolioTemplate, template_id)
    db.session.delete(template)
    db.session.commit()
    flash(_("Portafoglio modello eliminato."), "success")
    return redirect(url_for("portfolio.models_index"))


def _scope():
    """The portfolio whose model is looked at (?portfolio=id, F50), or None: all the investments together."""
    folio_id = request.values.get("portfolio", type=int)
    return folio_id if folio_id and db.session.get(Portfolio, folio_id) else None


def _scopes() -> list[tuple[int | None, str]]:
    """The scopes that have an active model, for the selector."""
    return [(t.portfolio_id, t.portfolio.name if t.portfolio else _("Tutti gli investimenti")) for t in models.actives()]


@portfolio_bp.route("/rebalance")
def rebalance():
    folio_id = _scope()
    template = models.active(folio_id)
    if template is None:
        flash(_("Questo portafoglio non ha ancora un portafoglio modello attivo: creane uno e collegalo.") if folio_id
              else _("Scegli o crea prima un portafoglio modello."), "info")
        return redirect(url_for("portfolio.models_index"))
    mode = "full" if request.args.get("mode") == "full" else "new"
    amount = to_decimal(request.args.get("amount")) or Decimal(0)
    plan = models.rebalance(template, mode, amount)
    return render_template("portfolio/rebalance.html", plan=plan, scopes=_scopes(), folio_id=folio_id)


# ── From the rebalancing to the orders (F42) ───────────────────────────────────

def _proposed_orders(plan) -> list[dict]:
    """The moves of the rebalancing as orders: buy or sell, the holding, units and the latest price (all editable)."""
    orders = []
    for line in plan.lines:
        if not line.move or line.via is None or not line.units:
            continue
        orders.append({"holding": line.via, "label": line.label, "side": "buy" if line.move > 0 else "sell",
                       "units": abs(line.units), "price": Decimal(str(line.via.price)), "amount": abs(line.move)})
    return orders


@portfolio_bp.route("/rebalance/orders", methods=["GET", "POST"])
def rebalance_orders():
    """What to do at the broker, then — once done — the confirmation with the prices actually executed: each order
    becomes a purchase or a sale, in the chosen securities account and portfolio or, when none is chosen, where the
    units are (services.portfolio_ops.record_order)."""
    folio_id = _scope()
    template = models.active(folio_id)
    if template is None:
        flash(_("Scegli o crea prima un portafoglio modello."), "info")
        return redirect(url_for("portfolio.models_index"))
    mode = "full" if request.values.get("mode") == "full" else "new"
    amount = to_decimal(request.values.get("amount")) or Decimal(0)
    if request.method == "POST":
        account = db.session.get(Account, request.form.get("account_id", type=int) or 0)
        dossier = db.session.get(SecuritiesAccount, request.form.get("securities_account_id", type=int) or 0)
        folio = db.session.get(Portfolio, request.form.get("portfolio_id", type=int) or 0)
        on = to_date(request.form.get("on")) or date.today()
        done = 0
        try:
            if on > date.today():
                raise ValueError(_("La data non può essere nel futuro."))
            for i in range(request.form.get("rows", type=int) or 0):
                if not request.form.get(f"do-{i}"):
                    continue
                holding = db.session.get(Holding, request.form.get(f"holding-{i}", type=int) or 0)
                units, price = to_decimal(request.form.get(f"units-{i}")), to_decimal(request.form.get(f"price-{i}"))
                fee = to_decimal(request.form.get(f"fee-{i}"))
                if holding is None or not units or not price:
                    continue
                side = "sell" if request.form.get(f"side-{i}") == "sell" else "buy"
                portfolio_ops.record_order(holding, side, on, units, price, fee, account, dossier, folio,
                                           notes=_("Ribilanciamento «%(name)s»", name=template.name))
                done += 1
            if not done:
                raise ValueError(_("Nessun ordine da confermare: spunta quelli eseguiti e indica quote e prezzo."))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
            return redirect(url_for("portfolio.rebalance_orders", mode=mode, amount=request.values.get("amount"),
                                    portfolio=folio_id))
        db.session.commit()
        flash(_("%(count)s ordini del ribilanciamento registrati.", count=done), "success")
        return redirect(url_for("portfolio.rebalance", mode=mode, amount=request.values.get("amount"), portfolio=folio_id))
    plan = models.rebalance(template, mode, amount)
    dossiers = securities.accounts()
    first = dossiers[0] if len(dossiers) == 1 else None
    orders = _proposed_orders(plan)
    for order in orders:
        rule = first or accounts.favorite()
        fee = broker.commission(rule, order["units"] * order["price"]) if rule is not None else None
        order["fee"] = fee
    return render_template("portfolio/rebalance_orders.html", plan=plan, orders=orders, today=date.today(),
                           accounts=[(a.id, a.name) for a in accounts.active()],
                           dossiers=[(d.id, d.name) for d in dossiers], first=first,
                           folios=[(p.id, p.name) for p in securities.portfolios()],
                           mode=mode, folio_id=folio_id,
                           amount=request.values.get("amount", ""))
