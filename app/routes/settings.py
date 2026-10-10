import json
import re
from datetime import date

from apiflask import APIBlueprint
from flask import flash, jsonify, redirect, render_template, request, session, url_for
from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.category import Category, CategoryRule
from app.models.currency import ExchangeRate
from app.routes.helpers import delete_and_redirect, flash_errors, form_choice, form_date, form_decimal, form_text
from app.services import (
    ai_classification,
    ai_extraction,
    ai_models,
    categories,
    category_rules,
    currency,
    desktop,
    display,
    owners,
    settings_store,
)
from app.services.bank_import import CATEGORY_RULES

# The interface choices live in a service (services read them too); re-exported for this page and older imports
from app.services.ui_settings import (  # noqa: F401
    AUTONOMY_TARGETS,
    DEFAULT_SETTINGS,
    FONTS,
    LANGUAGES,
    MODULE_BLUEPRINTS,
    MODULE_ENDPOINT_PREFIXES,
    MODULE_ENDPOINTS,
    SETTINGS_KEY,
    autonomy_target,
    current_language,
    current_settings,
    module_setting,
)

settings_bp = APIBlueprint(
    "settings",
    __name__,
    url_prefix="/settings",
    tag="Settings"
)

@settings_bp.route("/")
def index():
    return render_template("settings/index.html", settings=current_settings(), defaults=DEFAULT_SETTINGS,
                           currencies=currency.CURRENCIES, locales=display.LOCALES, languages=LANGUAGES, preview_date=date(2026, 5, 25),
                           autonomy_targets=AUTONOMY_TARGETS, desktop_app=desktop.available(), fonts=FONTS)


@settings_bp.route("/save", methods=["POST"])
def save():
    form = request.form
    new_settings = {}
    for key, default in DEFAULT_SETTINGS.items():
        if isinstance(default, bool):
            new_settings[key] = key in form  # checkbox is present only when checked
        else:
            new_settings[key] = (form.get(key) or default).strip()
    old_base = currency.base()
    settings_store.set(SETTINGS_KEY, json.dumps(new_settings))
    session.pop("settings", None)  # older versions kept them in the browser session
    flash(_("Impostazioni salvate con successo."), "success")
    if currency.base() != old_base:
        currency.recompute()
        flash(_("Totali ora in %(value)s: controvalori ricalcolati con i cambi salvati.", value=currency.base()), "success")
    return redirect(url_for("settings.index"))


@settings_bp.route("/reset", methods=["POST"])
def reset():
    settings_store.set(SETTINGS_KEY, None)
    session.pop("settings", None)
    flash(_("Impostazioni ripristinate ai valori predefiniti."), "success")
    return redirect(url_for("settings.index"))


# ── Categories ─────────────────────────────────────────────────────────────────

@settings_bp.route("/categories")
def categories_page():
    rows = categories.all_categories()
    by_id = {c.id: c for c in rows}
    mains = [c for c in rows if c.parent_id is None]
    ordered = []  # each main category followed by its subcategories
    for main in mains:
        ordered.append(main)
        ordered.extend(c for c in rows if c.parent_id == main.id)
    ordered.extend(c for c in rows if c not in ordered)
    return render_template("settings/categories.html", categories=ordered, by_id=by_id,
                           mains=[c.name for c in mains], has_children={c.parent_id for c in rows},
                           usage=categories.usage(), kinds=categories.KINDS, natures=categories.NATURES,
                           unmanaged=sorted(categories.used_names() - {c.name for c in rows}))


@settings_bp.route("/categories/save", methods=["POST"])
def category_save():
    """Add a category, or change one: renaming it (or merging into another) updates every transaction."""
    try:
        name = form_text("name", _("Nome"), required=True)
        kind = form_choice("kind", _("Tipo"), categories.KINDS)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("settings.categories_page"))
    categories.ensure_defaults()  # before looking the name up: the defaults may not exist yet
    old = request.form.get("old_name")
    hint = form_text("hint", _("Descrizione"))
    discretionary = "discretionary" in request.form
    nature = request.form.get("nature")
    nature = nature if nature in categories.NATURES else None  # empty: the main category's, else variable
    if old and old != name:
        merged = categories.rename(old, name)
        flash(_("«%(old)s» unita a «%(name)s».", old=old, name=name) if merged else _("«%(old)s» rinominata in «%(name)s».", old=old, name=name), "success")
    category = Category.query.filter_by(name=name).first()
    if category is None:
        category = Category(name=name, position=len(categories.all_categories()))
        db.session.add(category)
        if not old:
            flash(_("Categoria «%(name)s» aggiunta.", name=name), "success")
    elif not old:
        flash(_("La categoria «%(name)s» esiste già: aggiornata.", name=name), "success")
    category.kind, category.hint, category.discretionary, category.nature = kind, hint, discretionary, nature
    db.session.flush()
    try:
        categories.set_parent(category, request.form.get("parent") or None)
    except ValueError as exc:
        flash(str(exc), "error")
    db.session.commit()
    categories.forget()
    if old == name:
        flash(_("Categoria «%(name)s» aggiornata.", name=name), "success")
    return redirect(url_for("settings.categories_page"))


@settings_bp.route("/categories/delete", methods=["POST"])
def category_delete():
    name = request.form.get("name") or ""
    replacement = request.form.get("replacement") or None
    if replacement == name:
        replacement = None
    moved = categories.delete(name, replacement)
    if not moved:
        flash(_("Categoria «%(name)s» eliminata.", name=name), "success")
    elif replacement:
        flash(_("Categoria «%(name)s» eliminata: %(moved)s transazioni spostate in «%(replacement)s».",
                name=name, moved=moved, replacement=replacement), "success")
    else:
        flash(_("Categoria «%(name)s» eliminata: %(moved)s transazioni lasciate senza categoria.", name=name, moved=moved), "success")
    return redirect(url_for("settings.categories_page"))


# ── Categorization rules ───────────────────────────────────────────────────────

@settings_bp.route("/rules")
def rules_page():
    rules = CategoryRule.query.order_by(CategoryRule.source, CategoryRule.keyword).all()
    return render_template("settings/rules.html", rules=rules, builtin=CATEGORY_RULES,
                           categories=categories.known_categories())


@settings_bp.route("/rules/save", methods=["POST"])
def rule_save():
    try:
        rule = category_rules.save(request.form.get("keyword") or "", request.form.get("category") or "")
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("settings.rules_page"))
    flash(_("Regola salvata: «%(keyword)s» → %(category)s.", keyword=rule.keyword, category=rule.category), "success")
    if request.form.get("apply"):
        flash(_("Ricategorizzate %(value)s transazioni senza categoria o in «Altro».", value=category_rules.apply()), "success")
    return redirect(url_for("settings.rules_page"))


@settings_bp.route("/rules/<int:rule_id>/delete", methods=["POST"])
def rule_delete(rule_id):
    rule = db.get_or_404(CategoryRule, rule_id)
    return delete_and_redirect(rule, _("Regola «%(keyword)s» eliminata.", keyword=rule.keyword), url_for("settings.rules_page"))


@settings_bp.route("/rules/apply", methods=["POST"])
def rules_apply():
    changed = category_rules.apply(only_uncategorized=not request.form.get("all"))
    flash(_("Regole applicate: %(changed)s transazioni ricategorizzate.", changed=changed), "success")
    return redirect(url_for("settings.rules_page"))


# ── Currencies and exchange rates ──────────────────────────────────────────────

@settings_bp.route("/currencies")
def currencies_page():
    rates = ExchangeRate.query.order_by(ExchangeRate.on.desc(), ExchangeRate.currency).limit(300).all()
    return render_template("settings/currencies.html", rates=rates, usage=currency.foreign_usage(),
                           currencies={k: v for k, v in currency.CURRENCIES.items() if k != currency.BASE},
                           today=date.today())


@settings_bp.route("/currencies/rate", methods=["POST"])
def currency_rate_save():
    try:
        code = form_choice("currency", _("Valuta"), currency.CURRENCIES)
        on = form_date("on", _("Data"), required=True)
        rate = form_decimal("rate", _("Cambio"), required=True)
        currency.save_rate(code, on, rate)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("settings.currencies_page"))
    updated = currency.recompute(code)
    flash(_("Cambio salvato: 1 %(code)s = € %(rate)s al %(on)s. Ricalcolate %(updated)s transazioni.", code=code, rate=rate, on=display.day(on), updated=updated), "success")
    return redirect(url_for("settings.currencies_page"))


@settings_bp.route("/currencies/rate/<int:rate_id>/delete", methods=["POST"])
def currency_rate_delete(rate_id):
    rate = db.get_or_404(ExchangeRate, rate_id)
    code = rate.currency
    db.session.delete(rate)
    db.session.commit()
    currency.recompute(code)
    flash(_("Cambio eliminato."), "success")
    return redirect(url_for("settings.currencies_page"))


@settings_bp.route("/currencies/ecb", methods=["POST"])
def currency_ecb():
    try:
        count = currency.download_ecb()
    except (OSError, ValueError) as exc:
        flash(_("Non riesco a scaricare i cambi della BCE (%(exc)s). Controlla la connessione o inseriscili a mano.", exc=exc), "error")
        return redirect(url_for("settings.currencies_page"))
    flash(_("Scaricati %(count)s cambi di riferimento BCE degli ultimi 90 giorni; transazioni ricalcolate.", count=count), "success")
    return redirect(url_for("settings.currencies_page"))


# ── AI models (Ollama / Anthropic) ─────────────────────────────────────────────

MODEL_NAME = re.compile(r"^[a-z0-9][a-z0-9._\-/]*(:[a-z0-9._\-]+)?$", re.IGNORECASE)


def _valid_model_name(name: str) -> bool:
    return bool(name) and len(name) <= 100 and bool(MODEL_NAME.match(name))


@settings_bp.route("/ai")
def ai_models_page():
    ollama = ai_models.status(ai_extraction.base_url())
    catalog = {tier: [m for m in ai_models.CATALOG if m.tier == tier] for tier in ai_models.TIERS}
    extra_installed = sorted(set(ollama["installed"]) - set(ai_models.BY_NAME))
    return render_template(
        "settings/ai.html",
        provider=ai_extraction.provider(),
        model=ai_extraction.model_name(),
        models_by_provider={p: ai_extraction.model_for(p) for p in ai_extraction.DEFAULT_MODELS},
        classify_by_provider={p: settings_store.get(ai_classification.classify_setting(p)) or ""
                              for p in ai_extraction.DEFAULT_MODELS},
        ollama=ollama,
        ollama_url=ai_extraction.base_url(),
        catalog=catalog,
        tiers=ai_models.TIERS,
        extra_installed=extra_installed,
        pulls=ai_models.pull_progress(),
        is_vision=ai_models.is_vision,
        anthropic_models=ai_extraction.ANTHROPIC_MODELS,
    )


@settings_bp.route("/ai/save", methods=["POST"])
def ai_save():
    provider = request.form.get("provider", "none")
    model = (request.form.get("model") or "").strip()
    classify_model = (request.form.get("classify_model") or "").strip()
    if provider != "none" and provider not in ai_extraction.DEFAULT_MODELS:
        flash(_("Provider non valido."), "error")
        return redirect(url_for("settings.ai_models_page"))
    for name in (model, classify_model):
        if name and not _valid_model_name(name):
            flash(_("Nome del modello non valido."), "error")
            return redirect(url_for("settings.ai_models_page"))
        if provider != "none" and name and not ai_extraction.model_matches_provider(provider, name):
            which = "un modello Claude (es. claude-haiku-4-5)" if provider == "anthropic" else "un modello Ollama (es. qwen2.5vl:7b)"
            flash(_("%(name)s non è un modello per questo provider: scegli %(which)s.", name=name, which=which), "error")
            return redirect(url_for("settings.ai_models_page"))
    settings_store.set(ai_extraction.PROVIDER_SETTING, provider)
    if provider != "none" and model:  # empty field: keep this provider's previous choice
        settings_store.set(ai_extraction.model_setting(provider), model)
    if provider != "none" and "classify_model" in request.form:
        # empty = classify with the same model that reads documents
        settings_store.set(ai_classification.classify_setting(provider), classify_model or None)
    if provider == "none":
        flash(_("Lettura AI disattivata."), "success")
    else:
        flash(_("Lettura AI attiva: %(value)s.", value=ai_extraction.describe()), "success")
    return redirect(url_for("settings.ai_models_page"))


@settings_bp.route("/ai/pull", methods=["POST"])
def ai_pull():
    name = (request.form.get("name") or "").strip()
    if not _valid_model_name(name):
        flash(_("Nome del modello non valido."), "error")
    elif ai_models.start_pull(ai_extraction.base_url(), name):
        flash(_("Download di %(name)s avviato: puoi seguire l'avanzamento qui sotto.", name=name), "success")
    else:
        flash(_("Il download di %(name)s è già in corso.", name=name), "warning")
    return redirect(url_for("settings.ai_models_page"))


@settings_bp.route("/ai/pull-status")
def ai_pull_status():
    return jsonify(ai_models.pull_progress())


@settings_bp.route("/ai/delete", methods=["POST"])
def ai_delete():
    name = (request.form.get("name") or "").strip()
    if not _valid_model_name(name):
        flash(_("Nome del modello non valido."), "error")
        return redirect(url_for("settings.ai_models_page"))
    with flash_errors(ai_models.OllamaError):
        ai_models.delete(ai_extraction.base_url(), name)
        flash(_("Modello %(name)s rimosso.", name=name), "success")
    return redirect(url_for("settings.ai_models_page"))


# Account and users pages live in their own module on this blueprint
from app.routes import settings_users  # noqa: E402,F401


@settings_bp.route("/owners", methods=["GET", "POST"])
def owners_page():
    """Titolari e IBAN: who owns the accounts, so that a bonifico between them is read as a giroconto."""
    account_list = Account.query.order_by(Account.active.desc(), Account.name).all()
    if request.method == "POST":
        try:
            owners.set_holders(request.form.get("holders", "").splitlines())
            for account in account_list:
                owners.set_iban(account, request.form.get(f"iban-{account.id}"))
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
            return render_template("settings/owners.html", accounts=account_list, values=request.form), 400
        flash(_("Titolari e IBAN salvati: i bonifici tra i tuoi conti verranno importati come giroconti."), "success")
        return redirect(url_for("settings.owners_page"))
    values = {"holders": "\n".join(owners.holders())} | {f"iban-{a.id}": a.iban or "" for a in account_list}
    return render_template("settings/owners.html", accounts=account_list, values=values)
