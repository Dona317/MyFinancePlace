"""
Model portfolios and rebalancing (F19d), on the portfolio's blueprint: the templates (own ones and ready ones to
copy), the one active, and what to buy or sell to get back to it.
"""
from decimal import Decimal

from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.portfolio_model import PortfolioTemplate
from app.routes.portfolio import portfolio_bp
from app.services import portfolio_models as models
from app.services.parsing import to_decimal

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
        "band": f"{(template.band if template else Decimal(5)).normalize():f}".replace(".", ",")}
    return render_template("portfolio/model_form.html", template=template, values=values, rows=_rows(template),
                           holdings=models.investments(), classes=models.investment_classes())


def _form(template: PortfolioTemplate | None):
    if request.method == "GET":
        return _page(template)
    is_new = template is None
    target = template or PortfolioTemplate(active=PortfolioTemplate.query.count() == 0)
    try:
        with db.session.no_autoflush:
            if is_new:
                db.session.add(target)
            models.save(target, request.form.get("name", ""), request.form.get("description"),
                        to_decimal(request.form.get("band")), _slots_from_form())
    except models.TemplateError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return _page(None if is_new else db.session.get(PortfolioTemplate, template.id))
    db.session.commit()
    flash(_("Portafoglio modello salvato."), "success")
    return redirect(url_for("portfolio.rebalance") if target.active else url_for("portfolio.models_index"))


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
    return redirect(url_for("portfolio.rebalance"))


@portfolio_bp.route("/models/<int:template_id>/delete", methods=["POST"])
def models_delete(template_id):
    template = db.get_or_404(PortfolioTemplate, template_id)
    db.session.delete(template)
    db.session.commit()
    flash(_("Portafoglio modello eliminato."), "success")
    return redirect(url_for("portfolio.models_index"))


@portfolio_bp.route("/rebalance")
def rebalance():
    template = models.active()
    if template is None:
        flash(_("Scegli o crea prima un portafoglio modello."), "info")
        return redirect(url_for("portfolio.models_index"))
    mode = "full" if request.args.get("mode") == "full" else "new"
    amount = to_decimal(request.args.get("amount")) or Decimal(0)
    plan = models.rebalance(template, mode, amount)
    return render_template("portfolio/rebalance.html", plan=plan)
