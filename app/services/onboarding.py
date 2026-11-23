"""
The first set-up of an archive (23 Nov 2026, F109): a guided start instead of an empty dashboard.

    benvenuto ──(Salta)──▶ scelta ──┬─ «sono nuovo» ─▶ preferenze ▶ aspetto ▶ persone ▶ conti ▶ movimenti ▶ fine
                                    └─ «ho già un archivio» ─▶ importa (a backup) ─▶ fine

Every step can be skipped; the state (the step reached, the path, the steps skipped) is kept in the archive, so the
tutorial starts again where it was left and each archive has its own. It opens by itself from the Dashboard only
for an archive with nothing in it yet (no transactions, no accounts of the user's, no holdings) and not done before:
an archive in use is never interrupted. Each step saves through the services the pages use.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import accounts, currency, owners, settings_store
from app.services.i18n import _l
from app.services.ui_settings import DEFAULT_SETTINGS, FONTS, LANGUAGES, SETTINGS_KEY, current_settings

STATE = "onboarding"
NEW = ("preferenze", "aspetto", "persone", "conti", "movimenti", "fine")
EXISTING = ("importa", "fine")
TITLES = {"benvenuto": _l("Benvenuto"), "scelta": _l("Da dove parti"), "preferenze": _l("Lingua e valuta"),
          "aspetto": _l("Aspetto"), "persone": _l("Persone e aree"), "conti": _l("I tuoi conti"),
          "movimenti": _l("I movimenti"), "importa": _l("Il tuo archivio"), "fine": _l("Tutto pronto")}
CURRENCIES = ("EUR", "USD", "GBP", "CHF", "DKK", "SEK", "NOK", "PLN", "CZK", "JPY", "CAD", "AUD")
LOCALES = {"it-IT": "1.234,56 · 31/12/2026", "en-GB": "1,234.56 · 31/12/2026", "en-US": "1,234.56 · 12/31/2026",
           "de-DE": "1.234,56 · 31.12.2026", "fr-FR": "1 234,56 · 31/12/2026"}
DATE_FORMATS = {"it-IT": "DD/MM/YYYY", "en-GB": "DD/MM/YYYY", "en-US": "MM/DD/YYYY", "de-DE": "DD.MM.YYYY",
                "fr-FR": "DD/MM/YYYY"}
MODULES = (("module_portfolio", _l("Investimenti"), _l("Azioni, ETF, fondi, obbligazioni, cripto e conti titoli")),
           ("module_debt", _l("Debiti e mutui"), _l("Mutui, prestiti, rate e piani di ammortamento")),
           ("module_insurance", _l("Assicurazioni"), _l("Polizze, premi e scadenze")),
           ("module_documents", _l("Documenti"), _l("Contratti, fatture e scontrini collegati ai movimenti")),
           ("module_tax", _l("Fisco"), _l("730, plusvalenze, bollo e IVAFE")))
MAX_PEOPLE = 10  # the holders the step takes (first and last name each)
ACCOUNT_KINDS = ("current", "card", "prepaid", "savings", "other")  # the ones a user opens (Contanti is always there)


def state() -> dict:
    return settings_store.get_json(STATE, {}, expect=dict) or {}


def _save(**values) -> dict:
    current = state() | values
    settings_store.set_json(STATE, current)
    return current


def steps(path: str | None = None) -> tuple[str, ...]:
    """Every step of the path chosen (before the choice: the first two only)."""
    path = path or state().get("path")
    return ("benvenuto", "scelta") + (EXISTING if path == "existing" else NEW if path == "new" else ())


def empty_archive() -> bool:
    """Nothing in the archive yet: no transactions, no accounts of the user's (Contanti and Debiti are always there),
    no holdings."""
    return (Transaction.query.first() is None and Holding.query.first() is None
            and Account.query.filter(Account.fixed.is_(None)).first() is None)


def needed() -> bool:
    """The tutorial opens by itself: never finished nor put aside, and the archive is empty."""
    return not state().get("done") and empty_archive()


def current_step() -> str:
    return state().get("step") or "benvenuto"


def go(step: str) -> str:
    """The step reached (the tutorial starts from there next time)."""
    _save(step=step)
    return step


def next_of(step: str) -> str:
    order = steps()
    return order[order.index(step) + 1] if step in order and order.index(step) + 1 < len(order) else "fine"


def previous_of(step: str) -> str | None:
    order = steps()
    return order[order.index(step) - 1] if step in order and order.index(step) > 0 else None


def choose(path: str) -> str:
    """«Sono nuovo» or «ho già un archivio»: the rest of the steps."""
    path = "existing" if path == "existing" else "new"
    _save(path=path)
    return go(steps(path)[2])


def skip(step: str) -> str:
    """A step left for later: the checklist of the end says so."""
    skipped = sorted(set(state().get("skipped") or []) | {step})
    _save(skipped=skipped)
    return go(next_of(step))


def finish() -> None:
    """Done (or put aside with «Configura più tardi»): it does not open by itself any more."""
    _save(done=True, step="fine")


def restart() -> None:
    """Impostazioni → «Rifai la configurazione iniziale»: from the first step again."""
    settings_store.set_json(STATE, {"step": "benvenuto"})


# ── What the steps save ────────────────────────────────────────────────────────

def save_settings(**values) -> None:
    """Some of the interface choices (Impostazioni), the others as they are."""
    saved = settings_store.get_json(SETTINGS_KEY, None, expect=dict) or dict(current_settings())
    old_base = currency.base()
    saved.update({k: v for k, v in values.items() if k in DEFAULT_SETTINGS})
    settings_store.set_json(SETTINGS_KEY, saved)
    if currency.base() != old_base:
        currency.recompute()


def preferences(language: str, base: str, locale: str) -> None:
    save_settings(language=language if language in LANGUAGES else "it",
                  currency=base if base in CURRENCIES else "EUR",
                  locale=locale if locale in LOCALES else "it-IT",
                  date_format=DATE_FORMATS.get(locale, "DD/MM/YYYY"))


def look(font: str) -> None:
    save_settings(font=font if font in FONTS else "inter")


def people_and_areas(holders: list[str], modules: set[str]) -> None:
    owners.set_holders([h for h in holders if h.strip()])
    save_settings(**{key: key in modules for key, _label, _hint in MODULES})


def add_accounts(rows: list[dict], cash: Decimal | None = None, today: date | None = None) -> list[Account]:
    """The accounts written in the step, each with the balance it has today (its opening balance until movements
    come: the bank connection aligns it, an import adds to it); and the cash in the wallet. A row without a name is
    left out; a name already used gets a number."""
    today = today or date.today()
    made = []
    taken = {name.lower() for (name,) in db.session.query(Account.name)}
    for row in rows:
        name = " ".join((row.get("name") or "").split())[:80]
        if not name:
            continue
        unique, n = name, 2
        while unique.lower() in taken:
            unique, n = f"{name} {n}", n + 1
        taken.add(unique.lower())
        balance = row.get("balance") or Decimal(0)
        account = Account(name=unique, kind=row.get("kind") if row.get("kind") in ACCOUNT_KINDS else "current",
                          bank=(row.get("bank") or "").strip()[:80] or None, owner=row.get("owner") or None,
                          currency=currency.base(), opening_balance=balance, reconciled_on=today,
                          reconciled_balance=balance)
        db.session.add(account)
        made.append(account)
    if cash:
        accounts.ensure_fixed()
        wallet = Account.query.filter_by(fixed="cash").first()
        if wallet is not None:
            wallet.opening_balance = cash
    db.session.commit()
    if made:
        _save(accounts=sorted(set(state().get("accounts") or []) | {a.id for a in made}))
    return made


def made_accounts() -> list[Account]:
    """The accounts made in the tutorial (for «I movimenti»), else every account of the user's."""
    ids = state().get("accounts") or []
    found = Account.query.filter(Account.id.in_(ids)).order_by(Account.id).all() if ids else []
    return found or Account.query.filter(Account.fixed.is_(None), Account.active.is_(True)).order_by(Account.name).all()


def left_to_do() -> list[dict]:
    """The end: what is still to do (the steps skipped and what the archive misses), each with where to do it."""
    skipped = set(state().get("skipped") or [])
    todo = []
    if "conti" in skipped or not Account.query.filter(Account.fixed.is_(None)).first():
        todo.append({"label": _l("Aggiungi i tuoi conti"), "endpoint": "accounts.new", "icon": "bank"})
    if not Transaction.query.first():
        todo.append({"label": _l("Porta i movimenti: collega la banca o carica un estratto conto"),
                     "endpoint": "export.import_page", "icon": "box-arrow-in-down"})
    if current_settings().get("module_portfolio", True) and not Holding.query.first():
        todo.append({"label": _l("Aggiungi le posizioni del portafoglio"), "endpoint": "portfolio.index", "icon": "briefcase"})
    if "persone" in skipped:
        todo.append({"label": _l("Scegli le persone e le aree da seguire"), "endpoint": "settings.index", "icon": "people"})
    return todo
