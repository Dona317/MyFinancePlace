"""The first set-up of an archive (F109): one page per step, see services/onboarding.py."""
from __future__ import annotations

from apiflask import APIBlueprint
from flask import abort, flash, redirect, render_template, request, url_for
from flask_babel import gettext as _

from app.models.account import Account
from app.services import accounts, family, onboarding, owners
from app.services.parsing import to_decimal
from app.services.ui_settings import FONTS, LANGUAGES, current_settings

onboarding_bp = APIBlueprint("onboarding", __name__, url_prefix="/benvenuto", tag="Onboarding")

STEPS = tuple(onboarding.TITLES)


@onboarding_bp.route("/")
def index():
    """Where the tutorial was left (the first step the first time)."""
    return redirect(url_for("onboarding.step", name=onboarding.current_step()))


@onboarding_bp.route("/<name>", methods=["GET", "POST"])
def step(name):
    if name not in STEPS:
        abort(404)
    if request.method == "POST":
        error = _save(name)
        if error is None:
            onboarding.mark(name)
            if request.args.get("da") == "lista" and name != "scelta":  # opened from «Primi passi»: back there
                flash(_("Salvato."), "success")
                return redirect(url_for("onboarding.checklist"))
            if name == "scelta":
                return redirect(url_for("onboarding.step", name=onboarding.choose(request.form.get("path", "new"))))
            return redirect(url_for("onboarding.step", name=onboarding.go(onboarding.next_of(name))))
        flash(error, "error")
    onboarding.go(name)
    order = onboarding.steps()
    shown = [s for s in order if s not in ("benvenuto", "scelta")]
    return render_template(
        f"onboarding/{name}.html", step=name, focus_page=True, title=onboarding.TITLES[name],
        position=(shown.index(name) + 1) if name in shown else None, count=len(shown),
        back=onboarding.previous_of(name), settings=current_settings(), languages=LANGUAGES, fonts=FONTS,
        currencies=onboarding.CURRENCIES, locales=onboarding.LOCALES, modules=onboarding.MODULES,
        people=[tuple(name.split(" ", 1)) if " " in name else (name, "") for name in owners.holders()],
        max_people=onboarding.MAX_PEOPLE, kinds={k: accounts.KINDS[k] for k in onboarding.ACCOUNT_KINDS},
        icons=accounts.ICONS, made=onboarding.made_accounts() if name == "movimenti" else [],
        owner_choices=family.choices(), todo=onboarding.left_to_do() if name == "fine" else [],
        cash=Account.query.filter_by(fixed="cash").first(),
    )


def _save(name: str) -> str | None:
    """What the step's form says, saved; a message when it cannot be."""
    form = request.form
    if name == "preferenze":
        onboarding.preferences(form.get("language", "it"), form.get("currency", "EUR"), form.get("locale", "it-IT"))
    elif name == "aspetto":
        onboarding.look(form.get("font", "inter"))
    elif name == "persone":
        people = list(zip(form.getlist("first"), form.getlist("last")))[:onboarding.MAX_PEOPLE]
        half = next((f"{first} {last}".strip() for first, last in people if bool(first.strip()) != bool(last.strip())), None)
        if half:
            return _("«%(name)s»: scrivi sia il nome sia il cognome.", name=half)
        try:
            onboarding.people_and_areas([f"{first.strip()} {last.strip()}" for first, last in people if first.strip()],
                                        set(form.getlist("modules")))
        except ValueError as exc:  # a holder needs name and surname (owners.set_holders)
            return str(exc)
    elif name == "conti":
        rows = []
        for kind, label, bank, balance, owner in zip(form.getlist("kind"), form.getlist("name"), form.getlist("bank"),
                                                     form.getlist("balance"), form.getlist("owner") or [""] * 99):
            amount = to_decimal(balance) if balance.strip() else None
            if balance.strip() and amount is None:
                return _("«%(value)s» non è un importo: scrivi il saldo come 1.234,56.", value=balance)
            rows.append({"kind": kind, "name": label, "bank": bank, "balance": amount, "owner": owner})
        cash = to_decimal(form.get("cash", "")) if form.get("cash", "").strip() else None
        made = onboarding.add_accounts(rows, cash)
        if made:
            flash(_("%(count)s conti creati.", count=len(made)), "success")
    return None


@onboarding_bp.route("/primi-passi")
def checklist():
    """«Primi passi»: what to prepare before using the app, with what is done; each opens its step."""
    done, total = onboarding.progress()
    return render_template("onboarding/primi_passi.html", items=onboarding.checklist(), done=done, total=total)


@onboarding_bp.route("/<name>/salta", methods=["POST"])
def skip(name):
    """«Salta questo passo»: left for the list at the end."""
    if name not in STEPS:
        abort(404)
    if name == "benvenuto":  # the welcome's «Salta»: straight to the choice
        return redirect(url_for("onboarding.step", name=onboarding.go("scelta")))
    return redirect(url_for("onboarding.step", name=onboarding.skip(name)))


@onboarding_bp.route("/chiudi", methods=["POST"])
def finish():
    """«Apri la Dashboard» (or «Configura più tardi»): the tutorial does not open by itself any more."""
    onboarding.finish()
    if request.form.get("later"):
        flash(_("Configurazione rimandata: la riprendi quando vuoi da «Primi passi» nel menu."), "info")
    return redirect(url_for("dashboard.dashboard"))


@onboarding_bp.route("/ricomincia", methods=["POST"])
def restart():
    onboarding.restart()
    return redirect(url_for("onboarding.step", name="benvenuto"))
