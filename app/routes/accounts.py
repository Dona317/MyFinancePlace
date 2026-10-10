from datetime import date

from apiflask import APIBlueprint
from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.routes.helpers import delete_and_redirect, form_choice, form_date, form_decimal, form_text, save_form
from app.services import accounts, display, owners
from app.services import currency as currency_service
from app.services.tax_rules import REGIMES as TAX_REGIMES

accounts_bp = APIBlueprint(
    "accounts",
    __name__,
    url_prefix="/accounts",
    tag="Accounts"
)

CURRENCIES = list(currency_service.CURRENCIES)


def _account_from_form(account: Account) -> Account:
    account.name = form_text("name", _("Nome"), required=True)
    account.kind = form_choice("kind", _("Tipo"), accounts.KINDS)
    currency = (request.form.get("currency") or "EUR").upper()
    account.currency = currency if currency in CURRENCIES else "EUR"
    account.opening_balance = form_decimal("opening_balance", _("Saldo iniziale"), allow_negative=True) or 0
    account.iban_tail = (form_text("iban_tail", _("Ultime cifre IBAN / carta")) or "")[-10:] or None
    owners.set_iban(account, request.form.get("iban"))
    account.notes = form_text("notes", _("Note"))
    account.active = "active" in request.form
    account.fee_fixed = form_decimal("fee_fixed", _("Commissione fissa"))
    account.fee_percent = form_decimal("fee_percent", _("Commissione percentuale"))
    account.fee_min = form_decimal("fee_min", _("Commissione minima"))
    account.fee_max = form_decimal("fee_max", _("Commissione massima"))
    account.tax_regime = form_choice("tax_regime", _("Regime fiscale"), TAX_REGIMES) if request.form.get("tax_regime") \
        else "amministrato"
    account.abroad = "abroad" in request.form
    if account.fee_min is not None and account.fee_max is not None and account.fee_min > account.fee_max:
        raise ValueError(_("Commissioni: il minimo non può superare il massimo."))
    duplicate = Account.query.filter(Account.name == account.name, Account.id != account.id).first()
    if duplicate:
        raise ValueError(_("Esiste già un conto chiamato «%(name)s».", name=account.name))
    return account


def _render_form(account, values):
    return render_template("accounts/form.html", tax_regimes=TAX_REGIMES, account=account, kinds=accounts.KINDS, currencies=CURRENCIES,
                           values=values)


@accounts_bp.route("/")
def index():
    rows = accounts.summary()
    return render_template(
        "accounts/index.html", rows=rows, kinds=accounts.KINDS, icons=accounts.ICONS,
        total=sum(r["balance_base"] for r in rows if r["account"].active), unassigned=accounts.unassigned_count(),
    )


@accounts_bp.route("/<int:account_id>")
def detail(account_id):
    account = db.get_or_404(Account, account_id)
    recent = (Transaction.query
              .filter((Transaction.account_id == account.id) | (Transaction.counter_account_id == account.id))
              .order_by(Transaction.date.desc(), Transaction.id.desc()).limit(50).all())
    return _render_detail(account, recent, None)


def _render_detail(account: Account, recent: list[Transaction], result: dict | None):
    return render_template("accounts/detail.html", account=account, balance=accounts.balance(account),
                           recent=recent, kinds=accounts.KINDS, today=date.today(), result=result,
                           symbol=currency_service.symbol(account.currency), estimated=accounts.estimated(account),
                           in_account=lambda tx: accounts.amount_in(tx, account))


@accounts_bp.route("/<int:account_id>/reconcile", methods=["POST"])
def reconcile(account_id):
    account = db.get_or_404(Account, account_id)
    try:
        on = form_date("on", _("Data dell'estratto"), required=True)
        statement = form_decimal("statement_balance", _("Saldo dell'estratto"), required=True, allow_negative=True)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("accounts.detail", account_id=account.id))
    result = accounts.reconcile(account, on, statement)
    if result["difference"] == 0:
        flash(_("Conto riconciliato al %(on)s: il saldo coincide con l'estratto.", on=display.day(on)), "success")
    recent = (Transaction.query.filter(Transaction.account_id == account.id, Transaction.date <= on)
              .order_by(Transaction.date.desc(), Transaction.id.desc()).limit(50).all())
    return _render_detail(account, recent, result)


@accounts_bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        return save_form(Account(), _account_from_form, _render_form,
                         lambda a: _("Conto «%(name)s» aggiunto.", name=a.name), lambda a: url_for("accounts.index"))
    return _render_form(None, {})


@accounts_bp.route("/<int:account_id>/edit", methods=["GET", "POST"])
def edit(account_id):
    account = db.get_or_404(Account, account_id)
    if request.method == "POST":
        return save_form(account, _account_from_form, _render_form,
                         lambda a: _("Conto «%(name)s» aggiornato.", name=a.name),
                         lambda a: url_for("accounts.detail", account_id=a.id))
    return _render_form(account, {})


@accounts_bp.route("/<int:account_id>/delete", methods=["POST"])
def delete(account_id):
    account = db.get_or_404(Account, account_id)
    return delete_and_redirect(account, _("Conto «%(name)s» eliminato: le sue transazioni restano, senza conto.",
                                          name=account.name), url_for("accounts.index"))
