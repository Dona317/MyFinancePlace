"""Collegamenti bancari (F107): link a bank through PSD2 (Enable Banking), tie its accounts to the app's, download the
movements by hand or by themselves, and look at the ones waiting (in the usual import preview).

Two pages: «Collegamenti bancari» (a tab of Conti e Carte) for the archive open now, and «Gestione PSD2» for the whole
app — the Enable Banking credentials, every connection of every archive, the log of the accesses, and «Collega una
banca» with the archive the new consent belongs to (an archive can hold several)."""
from datetime import date, datetime, timezone

from apiflask import APIBlueprint
from flask import current_app, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.bank_link import BankAccountLink, BankConnection
from app.routes.helpers import uploaded_file
from app.services import accounts, open_banking, studio
from app.services.open_banking import credentials
from app.services.parsing import to_date, to_decimal

banking_bp = APIBlueprint("banking", __name__, url_prefix="/banking", tag="Banking")

COUNTRIES = ("IT", "AT", "BE", "DE", "ES", "FI", "FR", "IE", "LT", "LU", "LV", "NL", "PT", "EE")


def _redirect_url() -> str:
    """Where the bank sends the user back: it must be among the redirect URLs of the Enable Banking application."""
    return current_app.config.get("ENABLE_BANKING_REDIRECT_URL") or url_for("banking.callback", _external=True)


def _back():
    return redirect(url_for("banking.index"))


def _connection(connection_id: int) -> BankConnection:
    return db.get_or_404(BankConnection, connection_id)


def _manage():
    return redirect(url_for("banking.manage"))


def _bank_choices() -> dict:
    """The country asked for and its banks, for the «Collega una banca» form."""
    country = (request.args.get("country") or "IT").upper()
    country = country if country in COUNTRIES else "IT"
    banks, error = [], None
    if open_banking.configured():
        try:
            banks = open_banking.banks(country)
        except open_banking.BankingError as exc:
            error = str(exc)
    return {"countries": COUNTRIES, "country": country, "banks": banks, "banks_error": error,
            "status": credentials.status()}


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@banking_bp.route("/")
def index():
    """The bank connections of the archive open now."""
    connections = BankConnection.query.order_by(BankConnection.aspsp_name, BankConnection.id).all()
    return render_template(
        "banking/index.html", connections=connections, accounts=accounts.active(),
        notice_days=open_banking.EXPIRY_NOTICE_DAYS, now_utc=_now(), today=_now().date(),
        sync_slots=open_banking.slots(),
        auto_today={c.id: open_banking.unattended_today(c) for c in connections},
        at_bank_rows={c.id: _at_bank(c) for c in connections}, **_bank_choices(),
    )


def _at_bank(connection: BankConnection) -> list[dict]:
    """The movements not booked yet at the bank, newest first, with real dates and amounts for the page."""
    rows = []
    for link in [k for k in connection.links if k.active]:
        for item in link.at_bank or []:
            rows.append({"date": to_date(item.get("date")), "description": item.get("description"),
                         "amount": to_decimal(item.get("amount")), "currency": item.get("currency") or "EUR"})
    return sorted(rows, key=lambda r: r["date"] or date.min, reverse=True)


@banking_bp.route("/manage")
def manage():
    """Gestione PSD2: the application's credentials, every archive's connections, the accesses."""
    connections, accesses = open_banking.overview()
    archives = open_banking.archives_shown()
    return render_template(
        "banking/manage.html", connections=connections, accesses=accesses, archives=archives,
        current_archive=open_banking.archive_id(), redirect_url=_redirect_url(), notice_days=open_banking.EXPIRY_NOTICE_DAYS,
        now_utc=_now(), **_bank_choices(),
    )


@banking_bp.route("/manage/open/<int:client_id>", methods=["POST"])
def open_archive(client_id):
    """From Gestione PSD2 to the connections of another archive: it becomes the open one."""
    target = _shown_archive(client_id)
    if target is None:
        return _manage()
    studio.choose(target)
    return redirect(url_for("banking.index") + (f"#connection-{request.form['connection']}"
                                                if (request.form.get("connection") or "").isdigit() else ""))


def _shown_archive(client_id: int | None):
    """One of the archives the user may work on; None (after saying why) for any other."""
    target = next((c for c in open_banking.archives_shown() if c.id == client_id), None)
    if target is None:
        flash(_("Archivio non disponibile."), "error")
    return target


@banking_bp.route("/credentials", methods=["POST"])
def save_credentials():
    if credentials.from_environment():
        flash(_("Le credenziali sono impostate dal server (ENABLE_BANKING_APP_ID): si cambiano lì."), "error")
        return _manage()
    upload = uploaded_file()
    pem = upload.read().decode("utf-8", "ignore") if upload is not None else (request.form.get("key_text") or "")
    try:
        credentials.save(request.form.get("app_id", ""), pem)
    except ValueError:
        flash(_("Servono l'ID dell'applicazione e la sua chiave privata (il file .pem scaricato da Enable Banking)."),
              "error")
        return _manage()
    flash(_("Credenziali di Enable Banking salvate."), "success")
    return _manage()


@banking_bp.route("/credentials/delete", methods=["POST"])
def delete_credentials():
    credentials.remove()
    flash(_("Credenziali di Enable Banking rimosse: i download si fermano finché non le inserisci di nuovo."), "success")
    return _manage()


@banking_bp.route("/connect", methods=["POST"])
def connect():
    """«Vai alla banca»: off to the bank's page to give the consent, for the archive chosen (Gestione PSD2) or the
    open one; the chosen archive becomes the open one, so the way back lands in it."""
    client_id = request.form.get("client_id", type=int)
    if client_id and client_id != open_banking.archive_id():
        target = _shown_archive(client_id)
        if target is None:
            return _manage()
        studio.choose(target)
    try:
        url = open_banking.start(request.form.get("aspsp", ""), request.form.get("country", "IT"), _redirect_url(),
                                 psu_type=request.form.get("psu_type") or "personal")
    except open_banking.BankingError as exc:
        flash(str(exc), "error")
        return _manage() if request.form.get("from") == "manage" else _back()
    return redirect(url)


@banking_bp.route("/connections/<int:connection_id>/renew", methods=["POST"])
def renew(connection_id):
    connection = _connection(connection_id)
    try:
        url = open_banking.start(connection.aspsp_name, connection.aspsp_country, _redirect_url(), connection)
    except open_banking.BankingError as exc:
        flash(str(exc), "error")
        return _back()
    return redirect(url)


@banking_bp.route("/callback")
def callback():
    """Back from the bank: the connection is saved and its movements downloaded straight away."""
    error = request.args.get("error_description") or request.args.get("error")
    try:
        connection = open_banking.finish(request.args.get("state"), request.args.get("code"), error)
    except open_banking.BankingError as exc:
        flash(str(exc), "error")
        return _back()
    flash(_("%(bank)s collegata: %(count)s conti.", bank=connection.aspsp_name, count=len(connection.links)), "success")
    _download(connection)
    return _back()


def _download(connection: BankConnection) -> None:
    try:
        results = open_banking.sync_connection(connection, psu=open_banking.psu_headers())
    except open_banking.BankingError as exc:
        flash(str(exc), "error")
        return
    flash(_("%(bank)s aggiornata: %(summary)s", bank=connection.aspsp_name, summary=open_banking.summary(results)),
          "success")
    if any(r.waiting for r in results):
        flash(_("Apri «Controlla» sui conti per vedere i movimenti in attesa e salvarli."), "info")


@banking_bp.route("/connections/<int:connection_id>/sync", methods=["POST"])
def sync(connection_id):
    _download(_connection(connection_id))
    return _back()


@banking_bp.route("/connections/<int:connection_id>/options", methods=["POST"])
def options(connection_id):
    connection = _connection(connection_id)
    connection.auto_sync = bool(request.form.get("auto_sync"))
    connection.auto_save = bool(request.form.get("auto_save"))
    db.session.commit()
    flash(_("Impostazioni di %(bank)s salvate.", bank=connection.aspsp_name), "success")
    return _back()


@banking_bp.route("/connections/<int:connection_id>/delete", methods=["POST"])
def delete(connection_id):
    connection = _connection(connection_id)
    name = connection.aspsp_name
    open_banking.disconnect(connection)
    flash(_("%(bank)s scollegata: i movimenti già salvati restano.", bank=name), "success")
    return _back()


@banking_bp.route("/links/<int:link_id>/account", methods=["POST"])
def link_account(link_id):
    """The account of the app the bank account's movements go to (none: they wait), and whether to read it at all."""
    link = db.get_or_404(BankAccountLink, link_id)
    account = db.session.get(Account, request.form.get("account_id", type=int) or 0)
    link.account_id = account.id if account else None
    link.active = bool(request.form.get("active"))
    db.session.commit()
    flash(_("Conto «%(name)s» aggiornato.", name=link.name or link.iban or link.uid), "success")
    return _back()


@banking_bp.route("/links/<int:link_id>/review")
def review(link_id):
    """The movements waiting on an account, in the import preview: confirmed there, they stop waiting."""
    from app.routes.export import _render_preview

    link = db.get_or_404(BankAccountLink, link_id)
    preview = open_banking.waiting_preview(link)
    if not preview.rows:
        flash(_("Nessun movimento in attesa su questo conto."), "info")
        return _back()
    name = f"{link.connection.aspsp_name} · {link.name or link.iban or link.uid}"
    return _render_preview(preview, name, account_id=link.account_id, psd2_link=link.id)
