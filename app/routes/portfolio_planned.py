"""
Theoretical orders, and the export / restore of the investments on their own, on the portfolio's blueprint: the orders of a rebalancing or of a PAC instalment saved before
going to the broker, what they would make of the positions and of the liquidity (gross of commissions), and their
confirmation with the executed figures and the commissions — given order by order, as one total, or found from the
liquidity left on the account (services.planned_orders).
"""
from datetime import date

from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.planned_order import PlannedOrder
from app.routes.helpers import download, uploaded_file
from app.routes.portfolio import portfolio_bp
from app.services import backup, investments_archive, planned_orders
from app.services.parsing import to_date, to_decimal


@portfolio_bp.route("/planned")
def planned_page():
    found = planned_orders.batches()
    every = [o for b in found for o in b.orders]
    return render_template("portfolio/planned.html", batches=found, positions=planned_orders.positions(every),
                           cash={b.batch: planned_orders.cash(b.orders) for b in found},
                           total_cash=planned_orders.cash(every), today=date.today(), nav_active="planned",
                           gross=planned_orders.gross)


@portfolio_bp.route("/planned/<batch>/confirm", methods=["POST"])
def planned_confirm(batch):
    form = request.form
    orders = PlannedOrder.query.filter_by(batch=batch).all()
    executed = []
    for order in orders:
        if not form.get(f"do-{order.id}"):
            continue
        executed.append(planned_orders.Execution(order, to_decimal(form.get(f"units-{order.id}")) or 0,
                                                 to_decimal(form.get(f"price-{order.id}")) or 0,
                                                 to_decimal(form.get(f"fee-{order.id}"))))
    actual = {}
    for key, value in form.items():
        if key.startswith("cash-") and key[5:].isdigit() and value.strip():
            actual[int(key[5:])] = to_decimal(value)
    try:
        result = planned_orders.confirm(batch, executed, to_date(form.get("on")) or date.today(),
                                        form.get("fee_mode", "each"), to_decimal(form.get("fee_total")), actual)
    except (planned_orders.PlannedError, ValueError) as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return redirect(url_for("portfolio.planned_page") + f"#batch-{batch}")
    db.session.commit()
    message = _("%(count)s ordini eseguiti registrati, commissioni %(fees)s €.", count=result.recorded,
                fees=f"{result.fees:.2f}".replace(".", ","))
    if result.by_account:
        message += " " + "; ".join(_("%(account)s: %(fees)s € ricavati dalla liquidità", account=name,
                                     fees=f"{fee:.2f}".replace(".", ",")) for name, fee in result.by_account.items())
    flash(message, "success")
    left = PlannedOrder.query.filter_by(batch=batch).count()
    if left:
        flash(_("%(count)s ordini non spuntati restano teorici.", count=left), "info")
    return redirect(url_for("portfolio.planned_page"))


@portfolio_bp.route("/planned/<batch>/discard", methods=["POST"])
def planned_discard(batch):
    removed = planned_orders.discard(batch)
    db.session.commit()
    flash(_("%(count)s ordini teorici eliminati.", count=removed), "success")
    return redirect(url_for("portfolio.planned_page"))


# ── The investments on their own: export and restore ───────────────────────────

@portfolio_bp.route("/archive")
def investments_export():
    """Download the Portfolio section (services.investments_archive)."""
    return download(investments_archive.create_archive(), f"investimenti_{date.today():%Y-%m-%d}.zip", "application/zip")


@portfolio_bp.route("/archive/restore", methods=["POST"])
def investments_restore():
    """Replace the Portfolio section with a file's; the whole archive is saved first."""
    upload = uploaded_file()
    if upload is None:
        flash(_("Scegli il file degli investimenti da ripristinare."), "error")
        return redirect(url_for("portfolio.broker_upload") + "#archive")
    if not request.form.get("confirm"):
        flash(_("Per ripristinare conferma che gli investimenti attuali verranno sostituiti."), "error")
        return redirect(url_for("portfolio.broker_upload") + "#archive")
    try:
        data = investments_archive.read_upload(upload.read())
        safety = backup.save_safety_copy()
        added = investments_archive.restore(data)
    except investments_archive.ArchiveError as exc:
        flash(str(exc), "error")
        return redirect(url_for("portfolio.broker_upload") + "#archive")
    flash(_("Investimenti ripristinati: %(holdings)s titoli, %(transactions)s movimenti, %(dossiers)s conti titoli, "
            "%(folios)s portafogli. L'archivio di prima è salvato in «%(safety)s».", holdings=added["holdings"],
            transactions=added["transactions"], dossiers=added["securities_accounts"], folios=added["portfolios"],
            safety=safety), "success")
    return redirect(url_for("portfolio.index"))
