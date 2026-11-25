"""Collegamenti bancari (F107): link a bank through PSD2 (Enable Banking), tie its accounts to the app's, download the
movements by hand or by themselves, and look at the ones waiting (in the usual import preview).

A bank is linked from one of the user's accounts (Conti e Carte → modifica conto → «Collega a Enable Banking»): the
bank's account becomes that one, so nothing is ever linked to an account not made yet. Two pages then manage what is
linked: «Collegamenti bancari» (a tab of Conti e Carte) for the archive open now, and «Gestione PSD2» for the whole
app — the Enable Banking credentials, every connection of every archive, the log of the accesses."""
from datetime import date, datetime, timezone

from apiflask import APIBlueprint
from flask import current_app, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.bank_link import BankAccountLink, BankConnection
from app.models.client import Client
from app.routes.helpers import safe_next, uploaded_file
from app.services import accounts, open_banking, studio
from app.services.open_banking import credentials
from app.services.parsing import to_date, to_decimal

banking_bp = APIBlueprint("banking", __name__, url_prefix="/banking", tag="Banking")

COUNTRIES = ("IT", "AT", "BE", "DE", "ES", "FI", "FR", "IE", "LT", "LU", "LV", "NL", "PT", "EE")


def _redirect_url() -> str:
    """Where the bank sends the user back: it must be among the redirect URLs of the Enable Banking application. The
    server's setting, else the way back saved with the credentials (an https relay page, for Production), else this
    app's own callback (enough for the sandbox)."""
    found = credentials.current()
    return (current_app.config.get("ENABLE_BANKING_REDIRECT_URL") or (found.redirect_url if found else None)
            or url_for("banking.callback", _external=True))


def _back():
    return redirect(url_for("banking.index"))


def _connection(connection_id: int) -> BankConnection:
    return db.get_or_404(BankConnection, connection_id)


def _manage():
    return redirect(url_for("banking.manage"))


def _bank_choices() -> dict:
    """The country asked for and its banks, for the «Collega a Enable Banking» form of an account."""
    country = (request.args.get("country") or "IT").upper()
    country = country if country in COUNTRIES else "IT"
    banks, error = [], None
    if open_banking.configured():
        try:
            banks = open_banking.banks(country)
        except open_banking.BankingError as exc:
            error = str(exc)
    return {"countries": COUNTRIES, "country": country, "banks": banks, "banks_error": error}


def account_panel(account: Account | None) -> dict | None:
    """What the account's edit page shows about its bank connection (None: an account a bank cannot be linked to)."""
    if not open_banking.linkable(account):
        return None
    links = open_banking.links_of(account)
    panel = {"configured": open_banking.configured(), "links": links, "free": [], "can_manage": studio.sees_archives(),
             "now_utc": _now(), "notice_days": open_banking.EXPIRY_NOTICE_DAYS}
    if panel["configured"] and not links:
        panel.update(free=open_banking.free_links(), **_bank_choices())
    return panel


def _account_page(account: Account):
    return redirect(url_for("accounts.edit", account_id=account.id) + "#bank-link")


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
        at_bank_rows={c.id: _at_bank(c) for c in connections},
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
    return render_template(
        "banking/manage.html", connections=connections, accesses=accesses, archives=open_banking.archives_shown(),
        redirect_url=_redirect_url(), notice_days=open_banking.EXPIRY_NOTICE_DAYS, now_utc=_now(),
        status=credentials.status(),
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
        credentials.clean_redirect(request.form.get("redirect_url"))
    except ValueError:
        flash(_("L'indirizzo di ritorno deve iniziare con https:// (Enable Banking non accetta altro in Production)."),
              "error")
        return _manage()
    try:
        credentials.save(request.form.get("app_id", ""), pem, request.form.get("redirect_url"))
    except ValueError:
        flash(_("Servono l'ID dell'applicazione e la sua chiave privata (il file .pem scaricato da Enable Banking)."),
              "error")
        return _manage()
    flash(_("Credenziali di Enable Banking salvate."), "success")
    _check()
    return _manage()


@banking_bp.route("/credentials/check", methods=["POST"])
def check_credentials():
    """«Verifica applicazione»: what Enable Banking says about it, and what is missing."""
    _check()
    return _manage()


def _check() -> None:
    try:
        info = open_banking.check_application(_redirect_url())
    except open_banking.BankingError as exc:
        flash(str(exc), "error")
        return
    for level, text in open_banking.describe_application(info, _redirect_url()):
        flash(text, level)


@banking_bp.route("/credentials/delete", methods=["POST"])
def delete_credentials():
    credentials.remove()
    flash(_("Credenziali di Enable Banking rimosse: i download si fermano finché non le inserisci di nuovo."), "success")
    return _manage()


@banking_bp.route("/accounts/<int:account_id>/connect", methods=["POST"])
def connect(account_id):
    """«Collega a Enable Banking» on an account: off to the bank's page to give the consent; on the way back the
    bank's account becomes this one."""
    account = db.get_or_404(Account, account_id)
    try:
        url = open_banking.start(request.form.get("aspsp", ""), request.form.get("country", "IT"), _redirect_url(),
                                 psu_type=request.form.get("psu_type") or "personal", account=account)
    except open_banking.BankingError as exc:
        flash(str(exc), "error")
        return _account_page(account)
    return redirect(url)


@banking_bp.route("/accounts/<int:account_id>/use/<int:link_id>", methods=["POST"])
def use_link(account_id, link_id):
    """A bank account already authorised (in a consent given for another account) becomes this one: no new consent."""
    account = db.get_or_404(Account, account_id)
    link = db.get_or_404(BankAccountLink, link_id)
    if link.account_id is not None or not open_banking.linkable(account):
        flash(_("Questo conto della banca è già collegato a un altro conto."), "error")
        return _account_page(account)
    open_banking.attach(link, account)
    db.session.commit()
    flash(_("«%(bank_account)s» di %(bank)s ora è il conto «%(name)s».", bank_account=link.name or link.iban or link.uid,
            bank=link.connection.aspsp_name, name=account.name), "success")
    _download(link.connection)
    return _account_page(account)


@banking_bp.route("/accounts/<int:account_id>/detach", methods=["POST"])
def detach(account_id):
    """The bank account stops being this account's (and being read); the consent stays, for the other accounts."""
    account = db.get_or_404(Account, account_id)
    open_banking.detach(account)
    flash(_("«%(name)s» non è più collegato alla banca: i movimenti già salvati restano.", name=account.name), "success")
    return _account_page(account)


@banking_bp.route("/connections/<int:connection_id>/choose/<int:account_id>", methods=["GET", "POST"])
def choose(connection_id, account_id):
    """Back from the bank with several accounts: which one is the account the link was started from."""
    connection = _connection(connection_id)
    account = db.get_or_404(Account, account_id)
    if request.method == "POST":
        link = next((k for k in connection.links if k.id == request.form.get("link_id", type=int)), None)
        if link is None:
            flash(_("Scegli il conto della banca che corrisponde a «%(name)s».", name=account.name), "error")
        else:
            for other in connection.links:
                if other.account_id == account.id and other is not link:
                    other.account_id, other.active = None, False
            open_banking.attach(link, account)
            db.session.commit()
            _download(connection)
            return _account_page(account)
    return render_template("banking/choose.html", connection=connection, account=account)


@banking_bp.route("/connections/<int:connection_id>/renew", methods=["POST"])
def renew(connection_id):
    """A new consent for the same bank; asked from an account's page, the way back lands there."""
    connection = _connection(connection_id)
    account = db.session.get(Account, request.form.get("account_id", type=int) or 0)
    try:
        url = open_banking.start(connection.aspsp_name, connection.aspsp_country, _redirect_url(), connection,
                                 account=account)
    except open_banking.BankingError as exc:
        flash(str(exc), "error")
        return _account_page(account) if account is not None else _back()
    return redirect(url)


@banking_bp.route("/callback/paste", methods=["POST"])
def paste_return():
    """The way back did not load: the address the browser was left on, pasted here, completes the link."""
    try:
        values = open_banking.pasted_return(request.form.get("url", ""))
    except ValueError:
        flash(_("Questo indirizzo non contiene la risposta della banca: copia tutto l'indirizzo della pagina su cui sei "
                "arrivato dopo il consenso (contiene «code=» e «state=»)."), "error")
        return redirect(safe_next() or url_for("banking.manage"))
    return redirect(url_for("banking.callback", **values))


@banking_bp.route("/callback")
def callback():
    """Back from the bank, in whatever browser the bank sent back to (the desktop app opens the system's): the
    consent is completed here, in the archive it was started for, the movements are downloaded, and a page of its
    own says how it went — «you can close this tab and go back to the app». No sign-in needed: the `state` is a
    random, single-use token kept on the server, and the bank's code is useless without the app's private key."""
    pending = open_banking.peek(request.args.get("state"))
    if pending:
        studio.activate(db.session.get(Client, pending.get("client") or 0) or studio.current())
    error = request.args.get("error_description") or request.args.get("error")
    try:
        connection, account = open_banking.finish(request.args.get("state"), request.args.get("code"), error)
    except open_banking.BankingError as exc:
        return render_template("banking/done.html", error=str(exc)), 400
    choose = open_banking.needs_choice(connection, account)
    results, download_error = [], None
    if not choose:
        try:
            results = open_banking.sync_connection(connection, psu=open_banking.psu_headers())
            download_error = connection.last_error  # an account refused while the others were read
        except open_banking.BankingError as exc:
            download_error = str(exc)
    return render_template("banking/done.html", connection=connection, account=account, choose=choose,
                           summary=open_banking.summary(results) if results else None, download_error=download_error,
                           waiting=sum(r.waiting for r in results))


def _download(connection: BankConnection) -> None:
    try:
        results = open_banking.sync_connection(connection, psu=open_banking.psu_headers())
    except open_banking.BankingError as exc:
        flash(str(exc), "error")
        return
    flash(_("%(bank)s aggiornata: %(summary)s", bank=connection.aspsp_name, summary=open_banking.summary(results)),
          "success")
    if connection.last_error:  # an account refused while the others were read
        flash(connection.last_error, "warning")
    if any(r.waiting for r in results):
        flash(_("Apri «Controlla» sui conti per vedere i movimenti in attesa e salvarli."), "info")


@banking_bp.route("/connections/<int:connection_id>/sync", methods=["POST"])
def sync(connection_id):
    _download(_connection(connection_id))
    return redirect(safe_next() or url_for("banking.index"))


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
