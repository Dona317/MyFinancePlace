"""
Operations from outside the app (F19c), on the portfolio's blueprint: a broker statement imported with a review step,
and the bank account's movements of a holding (a purchase paid from the current account) linked to it.
"""
from datetime import date
from decimal import Decimal

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import or_

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.routes.helpers import form_ids, uploaded_file
from app.routes.portfolio import portfolio_bp
from app.services import accounts, broker_import, portfolio_ops, transfer
from app.services.parsing import to_decimal

LINK_LIMIT = 200


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(current_app.secret_key, salt="broker-import-preview")


# ── Broker statement ───────────────────────────────────────────────────────────

@portfolio_bp.route("/import", methods=["GET", "POST"])
def broker_upload():
    """Step 1: the broker's CSV or Excel → the trades found, for review."""
    if request.method == "GET":
        return render_template("portfolio/import.html")
    upload = uploaded_file()
    if upload is None:
        flash(_("Scegli il file del broker da importare."), "error")
        return redirect(url_for("portfolio.broker_upload"))
    try:
        preview = broker_import.read(upload.filename, upload.read())
    except transfer.TableError as exc:
        flash(str(exc), "error")
        return redirect(url_for("portfolio.broker_upload"))
    holdings = Holding.query.order_by(Holding.name).all()
    active = accounts.active()
    return render_template("portfolio/import_preview.html", preview=preview, filename=upload.filename,
                           payload=_serializer().dumps([r.as_dict() for r in preview.rows]), holdings=holdings,
                           accounts=active, suggested=_suggested_account(active, upload.filename))


def _suggested_account(active: list[Account], filename: str) -> int | None:
    """The account whose name appears in the file's name (degiro_2026.csv → «Degiro»), or the only «other» one."""
    name = filename.lower()
    found = [a for a in active if a.name.split()[0].lower() in name]
    if len(found) == 1:
        return found[0].id
    brokers = [a for a in active if a.kind == "other"]
    return brokers[0].id if len(brokers) == 1 else None


def _holding_for(row: dict, choice: str, created: dict) -> Holding:
    """The holding the row goes to: chosen in the preview, or a new one (one per instrument of the file)."""
    if choice and choice.isdigit():
        holding = db.session.get(Holding, int(choice))
        if holding is not None:
            return holding
    key = row["isin"] or row["ticker"] or row["name"]
    if key not in created:
        created[key] = Holding(name=row["name"][:200], isin=row["isin"], ticker=row["ticker"],
                               asset_class=broker_import.guess_class(row["name"]), quantity=0, avg_price=0,
                               opening_quantity=0, opening_price=0, purchase_date=date.fromisoformat(row["on"]))
        db.session.add(created[key])
        db.session.flush()
    return created[key]


@portfolio_bp.route("/import/confirm", methods=["POST"])
def broker_confirm():
    """Step 2: the rows kept become operations of their holdings (new holdings created as needed)."""
    try:
        rows = _serializer().loads(request.form.get("payload", ""))
    except BadSignature:
        flash(_("Anteprima non valida o scaduta: carica di nuovo il file."), "error")
        return redirect(url_for("portfolio.broker_upload"))
    account_id = request.form.get("account_id", type=int)
    account = db.session.get(Account, account_id) if account_id else None
    known = {ref for (ref,) in Transaction.query.with_entities(Transaction.import_ref)
             .filter(Transaction.import_ref.in_([r["ref"] for r in rows]))}
    created, saved, skipped, refused = {}, 0, 0, []
    for index in sorted(form_ids("include")):
        if index >= len(rows):
            continue
        row = rows[index]
        if row["ref"] in known:
            skipped += 1
            continue
        holding = _holding_for(row, request.form.get(f"holding-{index}", ""), created)
        units = Decimal(row["units"])
        op = portfolio_ops.Operation("buy" if units > 0 else "sell", date.fromisoformat(row["on"]), account,
                                     units=abs(units), price=Decimal(row["price"]),
                                     fee=Decimal(row["fee"]) or None, import_ref=row["ref"])
        try:
            with db.session.begin_nested():
                portfolio_ops.record(holding, op)
            saved += 1
        except ValueError as exc:
            refused.append(_("riga %(line)s: %(error)s", line=row["line"], error=exc))
    db.session.commit()
    message = _("%(count)s operazioni importate.", count=saved)
    if created:
        message += " " + _("Nuovi titoli: %(names)s.", names=", ".join(h.name for h in created.values()))
    if skipped:
        message += " " + _("%(count)s già presenti sono state ignorate.", count=skipped)
    flash(message, "success")
    if refused:
        flash(_("Non importate: %(rows)s", rows=" · ".join(refused[:5])), "warning")
    return redirect(url_for("portfolio.index"))


# ── Bank movements of a holding ────────────────────────────────────────────────

def _candidates(holding: Holding) -> list[Transaction]:
    """Movements that look like this holding's purchases or sales and are not operations yet: already linked to it
    without units, in the «Investimenti» category, or naming its ISIN, ticker or name."""
    words = [w for w in (holding.isin, (holding.ticker or "").split(".")[0], holding.name) if w and len(w) >= 3]
    named = [field.ilike(f"%{word}%") for word in words for field in (Transaction.description, Transaction.bank_description)]
    unlinked = Transaction.holding_id.is_(None) & (or_(Transaction.category == "Investimenti", *named))
    return (Transaction.query
            .filter(Transaction.units.is_(None), Transaction.fee_for_id.is_(None),
                    Transaction.type.in_(("expense", "transfer", "income")),
                    (Transaction.holding_id == holding.id) | unlinked)
            .order_by(Transaction.date.desc()).limit(LINK_LIMIT).all())


def _link(tx: Transaction, holding: Holding, units: Decimal, price: Decimal) -> None:
    """The movement becomes the trade: money out of the account = a purchase, into it = a sale."""
    selling = tx.type == "income" or (tx.type == "transfer" and tx.account_id is None)
    account_id = tx.account_id or tx.counter_account_id
    tx.holding_id, tx.units, tx.unit_price = holding.id, -units if selling else units, price
    tx.type, tx.category = "transfer", "Investimenti"
    tx.account_id, tx.counter_account_id = (None, account_id) if selling else (account_id, None)


@portfolio_bp.route("/<int:holding_id>/link", methods=["GET", "POST"])
def link(holding_id):
    """Movements of the current account that were this holding's purchases or sales: units and price make them its
    operations."""
    holding = db.get_or_404(Holding, holding_id)
    candidates = _candidates(holding)
    if request.method == "POST":
        portfolio_ops.ensure_opening(holding.id)
        linked, wrong = 0, []
        for tx in candidates:
            if not request.form.get(f"link-{tx.id}"):
                continue
            units, price = to_decimal(request.form.get(f"units-{tx.id}")), to_decimal(request.form.get(f"price-{tx.id}"))
            if units is None and price:
                units = tx.amount / price
            if price is None and units:
                price = tx.amount / units
            if not units or units <= 0 or not price or price <= 0:
                wrong.append(tx.date.strftime("%d/%m/%Y"))
                continue
            _link(tx, holding, abs(units), abs(price))
            linked += 1
        db.session.flush()
        portfolio_ops.recompute(holding)
        db.session.commit()
        if linked:
            flash(_("%(count)s movimenti collegati come operazioni di «%(name)s».", count=linked, name=holding.name), "success")
        if wrong:
            flash(_("Indica le quote o il prezzo per i movimenti del %(days)s.", days=", ".join(wrong)), "warning")
        return redirect(url_for("portfolio.detail", holding_id=holding.id))
    return render_template("portfolio/link.html", holding=holding, candidates=candidates)
