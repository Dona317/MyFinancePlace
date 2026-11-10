"""
Operations from outside the app (F19c), on the portfolio's blueprint: a broker statement imported with a review step
(its columns, or a document read by the AI model: the operations, or the current state they are derived from),
and the bank account's movements of a holding (a purchase paid from the current account) linked to it.
"""
import base64
import zlib
from datetime import date
from decimal import Decimal

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import or_

from app.extensions import db
from app.models.account import Account
from app.models.securities import SecuritiesAccount
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.routes.helpers import form_ids, uploaded_file
from app.routes.portfolio import portfolio_bp
from app.services import accounts, ai_extraction, broker_import, import_presets, portfolio_ops, portfolio_reading, securities, transfer
from app.services.parsing import to_date, to_decimal

LINK_LIMIT = 200
AUTO = object()  # «apply the preset saved for these columns, if any»


def _serializer(salt: str = "broker-import-preview") -> URLSafeSerializer:
    return URLSafeSerializer(current_app.secret_key, salt=salt)


def _file_token(filename: str, raw: bytes) -> str:
    """The uploaded file, signed and carried by the mapping and preview pages (nothing is stored on the server)."""
    data = base64.b64encode(zlib.compress(raw)).decode()
    return _serializer("broker-import-file").dumps({"name": filename, "data": data})


def _file_from_token(token: str) -> tuple[str, bytes]:
    found = _serializer("broker-import-file").loads(token or "")
    return found["name"], zlib.decompress(base64.b64decode(found["data"]))


# ── Broker statement ───────────────────────────────────────────────────────────

@portfolio_bp.route("/import", methods=["GET", "POST"])
def broker_upload():
    """Step 1: the broker's CSV or Excel → the trades found, for review."""
    if request.method == "GET":
        return render_template("portfolio/import.html", ai=ai_extraction.describe(),
                               ai_cloud=ai_extraction.provider() == "anthropic", dossiers=securities.accounts(),
                               today=date.today())
    upload = uploaded_file()
    if upload is None:
        flash(_("Scegli il file del broker da importare."), "error")
        return redirect(url_for("portfolio.broker_upload"))
    return _analyse(upload.filename, upload.read())


@portfolio_bp.route("/import/columns", methods=["POST"])
def broker_columns():
    """The mapping screen and the preset choice: the file comes back signed, with the columns chosen
    (`col_<field>`), another preset (`choose`), or the request to change the columns (`edit`)."""
    try:
        filename, raw = _file_from_token(request.form.get("file_token", ""))
    except (BadSignature, KeyError, TypeError, ValueError, zlib.error):
        flash(_("Anteprima non valida o scaduta: carica di nuovo il file."), "error")
        return redirect(url_for("portfolio.broker_upload"))
    preset = _broker_preset(request.form.get("preset"))
    if request.form.get("choose"):
        return _analyse(filename, raw, preset=preset)
    mapping = {name: request.form.get(f"col_{name}") or None for name in broker_import.FIELDS}
    return _analyse(filename, raw, mapping=mapping, preset=preset, edit=bool(request.form.get("edit")))


@portfolio_bp.route("/import/ai", methods=["POST"])
def broker_ai():
    """A document of the broker read by the AI model: the operations it lists, or the current state (the positions)
    compared with the recorded ones; either way the rows go to the review page."""
    upload = uploaded_file()
    if upload is None:
        flash(_("Scegli il documento del broker da leggere."), "error")
        return redirect(url_for("portfolio.broker_upload"))
    mode = "state" if request.form.get("mode") == "state" else "operations"
    dossier = db.session.get(SecuritiesAccount, request.form.get("dossier_id", type=int) or 0)
    try:
        if mode == "state":
            reading = portfolio_reading.state(upload.filename, upload.read(), dossier.id if dossier else None,
                                              to_date(request.form.get("on")), bool(request.form.get("complete")))
        else:
            reading = portfolio_reading.operations(upload.filename, upload.read())
    except ai_extraction.AIExtractionError as exc:
        flash(_("Lettura AI non riuscita: %(exc)s", exc=exc), "error")
        return redirect(url_for("portfolio.broker_upload"))
    if not reading.preview.rows:
        flash(_("Le posizioni del documento sono quelle già registrate (%(count)s): nessuna operazione da aggiungere.",
                count=reading.unchanged), "success")
        for note in reading.notes or []:
            flash(note, "warning")
        return redirect(url_for("portfolio.broker_upload"))
    active = accounts.active()
    suggested = dossier.settlement_account_id if dossier else _suggested_account(active, upload.filename)
    return render_template("portfolio/import_preview.html", preview=reading.preview, filename=upload.filename,
                           payload=_serializer().dumps([r.as_dict() for r in reading.preview.rows]),
                           holdings=Holding.query.order_by(Holding.name).all(), accounts=active, suggested=suggested,
                           token=None, mapped="", preset=None, presets=[], reading=reading, dossier=dossier)


def _broker_preset(preset_id: str | None) -> dict | None:
    preset = import_presets.get(preset_id)
    return preset if preset and preset.get("kind") == "broker" else None


def _analyse(filename: str, raw: bytes, *, mapping: dict | None = None, preset=AUTO, edit: bool = False):
    """The preview of the file's trades, or the mapping screen when the columns are not all found (or the user asked
    to change them). Without a mapping, the preset saved for these columns is applied, else the guess."""
    try:
        headers, guessed, samples = broker_import.columns(filename, raw)
    except transfer.TableError as exc:
        flash(str(exc), "error")
        return redirect(url_for("portfolio.broker_upload"))
    if preset is AUTO:
        preset = import_presets.match(headers, "broker")
    if mapping is None:
        mapping = {**dict.fromkeys(broker_import.FIELDS), **import_presets.resolve(preset, headers)} if preset else guessed
    mapping = broker_import.clean(headers, mapping)
    token = _file_token(filename, raw)
    presets = import_presets.usable(headers, "broker")
    problem = broker_import.missing(mapping)
    preview = None
    if not edit and not problem:
        try:
            preview = broker_import.read(filename, raw, mapping)
        except transfer.TableError as exc:
            problem = str(exc)
    if preview is None:
        return render_template("portfolio/import_columns.html", filename=filename, headers=headers, samples=samples,
                               mapping=mapping, problem=None if edit else problem, token=token, preset=preset,
                               fields=_field_labels())
    holdings = Holding.query.order_by(Holding.name).all()
    active = accounts.active()
    suggested = _suggested_account(active, filename)
    preset_account = (preset or {}).get("options", {}).get("account_id")
    if preset_account and any(a.id == preset_account for a in active):
        suggested = preset_account
    mapped = _serializer("broker-import-mapping").dumps({"headers": headers, "mapping": preview.mapping})
    return render_template("portfolio/import_preview.html", preview=preview, filename=filename,
                           payload=_serializer().dumps([r.as_dict() for r in preview.rows]), holdings=holdings,
                           accounts=active, suggested=suggested, token=token, mapped=mapped, preset=preset,
                           presets=presets)


def _field_labels() -> list[tuple[str, str, str]]:
    """(field, label, note) of the mapping screen, in its order."""
    return [
        ("date", _("Data"), _("Il giorno dell’operazione (obbligatoria).")),
        ("side", _("Tipo di operazione"), _("Acquisto o vendita (A/V, Buy/Sell…). Senza, una quantità negativa è una vendita.")),
        ("isin", _("ISIN"), _("Il codice ISIN del titolo: il modo più sicuro di riconoscerlo.")),
        ("ticker", _("Ticker"), _("Il simbolo di borsa (ENEL.MI, VWRL…).")),
        ("name", _("Nome del titolo"), _("Serve almeno uno fra ISIN, ticker e nome.")),
        ("units", _("Quantità"), _("Le quote o il nominale comprati o venduti (obbligatoria).")),
        ("price", _("Prezzo"), _("Il prezzo di una quota; le obbligazioni in % del nominale.")),
        ("value", _("Controvalore in euro"), _("L’importo totale in euro: con il prezzo in un’altra valuta, il prezzo in euro "
                                              "si ricava da qui. Serve il prezzo o il controvalore.")),
        ("fee", _("Commissione"), _("Le commissioni e i costi dell’operazione.")),
    ]


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
    dossier_id = request.form.get("dossier_id", type=int)
    dossier = db.session.get(SecuritiesAccount, dossier_id) if dossier_id else None  # the state read was of this one
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
                                     fee=Decimal(row["fee"]) or None, import_ref=row["ref"], securities_account=dossier)
        try:
            with db.session.begin_nested():
                portfolio_ops.record(holding, op)
            saved += 1
        except ValueError as exc:
            refused.append(_("riga %(line)s: %(error)s", line=row["line"], error=exc))
    db.session.commit()
    _save_preset(account)
    message = _("%(count)s operazioni importate.", count=saved)
    if created:
        message += " " + _("Nuovi titoli: %(names)s.", names=", ".join(h.name for h in created.values()))
    if skipped:
        message += " " + _("%(count)s già presenti sono state ignorate.", count=skipped)
    flash(message, "success")
    if refused:
        flash(_("Non importate: %(rows)s", rows=" · ".join(refused[:5])), "warning")
    return redirect(url_for("portfolio.index"))


def _save_preset(account: Account | None) -> None:
    """«Salva come preset» ticked in the preview: the file's columns (and the account) saved under a name."""
    if not request.form.get("save_preset"):
        return
    try:
        mapped = _serializer("broker-import-mapping").loads(request.form.get("mapped", ""))
    except BadSignature:
        return
    name = import_presets.clean_name(request.form.get("preset_name"))
    if not name:
        flash(_("Preset non salvato: scrivi un nome."), "warning")
        return
    preset = import_presets.save(name, "broker", mapped["headers"], mapped["mapping"],
                                 {"account_id": account.id if account else None})
    flash(_("Preset «%(name)s» salvato: verrà applicato ai prossimi file con le stesse colonne.",
            name=preset["name"]), "success")


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
