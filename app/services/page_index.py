"""
Every page of the app, by macro section → section → its own pages (the tabs), for the page search at the top of the
side menu and for the menu itself (22 Nov 2026, UI-34).

The menu shows Dashboard, Transazioni, Portfolio and Obiettivi on their own (MAIN); every other section is in the
expandable «Da smistare» list, until it finds its place. The search lists them all, the sections the user may not
see left out (sections.in_menu).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from flask import url_for
from werkzeug.routing import BuildError

from app.services import sections
from app.services.i18n import _l

MAIN = ("transactions", "portfolio", "goals")  # after the Dashboard, in this order


@dataclass(frozen=True)
class Page:
    label: str
    endpoint: str
    args: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Entry:
    """A section of the app: its page, its icon, its own pages (the tabs), and the key that says who sees it."""
    key: str | None          # sections.SECTIONS key (None: always shown)
    label: str
    icon: str
    page: Page
    pages: tuple[Page, ...] = ()
    tbd: bool = True         # still marked «TBD» in the menu


def _tree() -> list[tuple[str, list[Entry]]]:
    year = date.today().year
    P = Page
    return [
        (_l("Panoramica"), [
            Entry("transactions", _l("Transazioni"), "list-ul", P(_l("Transazioni"), "transactions.index"), (
                P(_l("Entrate"), "reports.income"), P(_l("Uscite"), "reports.spending"),
                P(_l("Entrate e uscite ricorrenti"), "subscriptions.index"), P(_l("Investimenti"), "transactions.investments_page"),
                P(_l("Flussi"), "transactions.flows_page"),
                P(_l("Storni"), "transactions.reversals_page")), tbd=False),
            Entry("accounts", _l("Conti e Carte"), "bank", P(_l("Conti e Carte"), "accounts.index"), (
                P(_l("Carte"), "accounts.index", {"tab": "cards"}),
                P(_l("Riconciliazioni"), "accounts.index", {"tab": "reconcile"}),
                P(_l("Collegamenti bancari"), "banking.index")), tbd=False),
            Entry("reports", _l("Report"), "bar-chart-line", P(_l("Report"), "reports.index"), (
                P(_l("Riepilogo"), "reports.summary"), P(_l("Ritmo"), "reports.rhythm"),
                P(_l("Bilancio dell’anno"), "reports.year_review"))),
        ]),
        (_l("Panoramica Finanziaria"), [
            Entry("accounting", _l("Panoramica Finanziaria"), "journal-text", P(_l("Panoramica Finanziaria"), "accounting.index"), (
                P(_l("Stato patrimoniale"), "accounting.balance_sheet"), P(_l("Conto economico"), "accounting.income_statement"),
                P(_l("Flusso di cassa"), "accounting.cash_flow"), P(_l("Crescita"), "accounting.growth"),
                P(_l("Chiusure d’anno"), "accounting.closes"))),
            Entry("forecast", _l("Previsioni"), "graph-up-arrow", P(_l("Previsioni"), "forecast.index"), (
                P(_l("Mese per mese"), "forecast.index", {"tab": "months"}),
                P(_l("Entrate e uscite ricorrenti"), "forecast.index", {"tab": "recurring"}),
                P(_l("Metodi"), "forecast.index", {"tab": "methods"}), P(_l("Pensione e FIRE"), "forecast.retirement"))),
        ]),
        (_l("Stile di Vita"), [
            Entry("goals", _l("Obiettivi"), "trophy", P(_l("Obiettivi"), "lifestyle.goals"), (
                P(_l("Raggiunti"), "lifestyle.goals", {"tab": "done"}),
                P(_l("Fondo d’emergenza"), "lifestyle.goals", {"tab": "emergency"}),
                P(_l("Suggeriti"), "lifestyle.goals", {"tab": "suggested"}))),
            Entry("budget", _l("Budget"), "clipboard-check", P(_l("Budget"), "lifestyle.budget"), (
                P(_l("Categorie"), "lifestyle.budget", {"tab": "categories"}),
                P(_l("Accantonamenti"), "lifestyle.budget", {"tab": "set_asides"}),
                P(_l("Storico"), "lifestyle.budget", {"tab": "history"}))),
            Entry("events", _l("Eventi"), "airplane", P(_l("Eventi"), "events.index")),
            Entry("deadlines", _l("Promemoria"), "bell", P(_l("Promemoria"), "deadlines.index"), (
                P(_l("Calendario"), "deadlines.index", {"tab": "calendar"}),
                P(_l("Le tue scadenze"), "deadlines.index", {"tab": "mine"}))),
        ]),
        (_l("Gestione"), [
            Entry("portfolio", _l("Portfolio"), "briefcase", P(_l("Portfolio"), "portfolio.index"), (
                P(_l("Riepilogo"), "portfolio.overview_page"), P(_l("Portafogli e conti titoli"), "portfolio.portfolios_page"),
                P(_l("Rendimenti"), "portfolio.performance_page"), P(_l("Ordini"), "portfolio.orders_page"),
                P(_l("Ordini teorici"), "portfolio.planned_page"), P(_l("Calcolo commissioni"), "portfolio.fees_page"),
                P(_l("In evidenza"), "portfolio.highlights_page"), P(_l("Rendite"), "portfolio.income"),
                P(_l("Composizione"), "portfolio.composition_page"), P(_l("Portafoglio modello"), "portfolio.rebalance"),
                P(_l("Backtest"), "portfolio.backtest_page"), P(_l("Regole e PAC"), "portfolio.rules"),
                P(_l("Importa dal broker"), "portfolio.broker_upload"))),
            Entry("debt", _l("Debiti"), "credit-card", P(_l("Debiti"), "debt.index"), (
                P(_l("Elenco dei debiti"), "debt.index", {"tab": "debts"}),
                P(_l("Ammortamento"), "debt.index", {"tab": "amortization"}),
                P(_l("Strumenti dei debiti"), "debt.index", {"tab": "tools"}))),
            Entry("gigs", _l("Lavoretti"), "tools", P(_l("Lavoretti"), "gigs.index")),
            Entry("loans", _l("Prestiti tra persone"), "arrow-left-right", P(_l("Prestiti tra persone"), "loans.index")),
            Entry("insurance", _l("Assicurazioni"), "shield-check", P(_l("Assicurazioni"), "insurance.index")),
            Entry("utilities", _l("Bollette"), "lightning-charge", P(_l("Bollette"), "utilities.index")),
            Entry("documents", _l("Documenti"), "folder2-open", P(_l("Documenti"), "documents.index"), (
                P(_l("In scadenza"), "documents.expiring"),)),
            Entry("tax", _l("Fisco"), "percent", P(_l("Fisco"), "tax.index"), (
                P(_l("730: spese detraibili"), "tax.deductions", {"year": year}),
                P(_l("Plusvalenze"), "tax.investments", {"year": year}),
                P(_l("Bollo e IVAFE"), "tax.duties", {"year": year}),
                P(_l("Tetti di versamento"), "tax.limits", {"year": year}),
                P(_l("Lavori occasionali"), "tax.gigs_page", {"year": year}))),
        ]),
        (_l("Strumenti"), [
            Entry("export", _l("Importa"), "box-arrow-in-down", P(_l("Importa"), "export.import_page")),
            Entry("export", _l("Esporta e backup"), "box-arrow-up", P(_l("Esporta e backup"), "export.index")),
            Entry("snapshots", _l("Istantanee"), "camera", P(_l("Istantanee"), "snapshots.index")),
            Entry("health", _l("Salute dei dati"), "clipboard-check", P(_l("Salute dei dati"), "health.index")),
            Entry("clients", _l("Clienti"), "people", P(_l("Clienti"), "clients.index")),
            Entry("groups", _l("Gruppi e famiglia"), "house-heart", P(_l("Gruppi e famiglia"), "groups.index")),
        ]),
        (_l("Impostazioni"), [
            Entry(None, _l("Impostazioni"), "gear", P(_l("Impostazioni"), "settings.index"), (
                P(_l("Categorie"), "settings.categories_page"), P(_l("Regole di categorizzazione"), "settings.rules_page"),
                P(_l("Valute e cambi"), "settings.currencies_page"), P(_l("Modelli AI"), "settings.ai_models_page"),
                P(_l("Classificazioni dei titoli"), "settings.taxonomies_page")), tbd=False),
        ]),
    ]


def _url(page: Page) -> str | None:
    try:
        return url_for(page.endpoint, **page.args)
    except BuildError:  # a page of a module this installation does not have
        return None


def _visible(entry: Entry) -> bool:
    if entry.key == "groups" and not _studio():  # groups of archives: only where there are several archives
        return False
    return entry.key is None or sections.in_menu(entry.key)


def _studio() -> bool:
    from app.services import studio
    try:
        return studio.is_studio()
    except Exception:  # noqa: BLE001 - the menu never breaks a page
        return False


def search_rows() -> list[dict]:
    """The rows of the page search, in order: a macro section (not a link), its sections, their own pages; each link
    with the words it is found by (its name and those above it)."""
    rows = []
    for macro, entries in _tree():
        shown = [e for e in entries if _visible(e) and _url(e.page)]
        if not shown:
            continue
        rows.append({"level": 0, "label": str(macro)})
        for entry in shown:
            rows.append({"level": 1, "label": str(entry.label), "url": _url(entry.page), "icon": entry.icon,
                         "find": f"{entry.label} {macro}"})
            for page in entry.pages:
                url = _url(page)
                if url:
                    rows.append({"level": 2, "label": str(page.label), "url": url,
                                 "find": f"{page.label} {entry.label} {macro}"})
    return rows


def menu() -> tuple[list[dict], list[dict]]:
    """The side menu: the main sections (MAIN, in its order) and the others («Da smistare»), each {key, label, icon,
    url, tbd, active}."""
    current = sections.section_of(_endpoint())
    items = {}
    others = []
    for _macro, entries in _tree():
        for entry in entries:
            if entry.key is None or not _visible(entry):
                continue
            url = _url(entry.page)
            if not url:
                continue
            item = {"key": entry.key, "label": str(entry.label), "icon": entry.icon, "url": url, "tbd": entry.tbd,
                    "active": _active(entry, current)}
            if entry.key in MAIN:
                items[entry.key] = item
            else:
                others.append(item)
    return [items[k] for k in MAIN if k in items], others


def _endpoint() -> str | None:
    from flask import request
    return request.endpoint


def _active(entry: Entry, current: str | None) -> bool:
    """The page shown belongs to this entry: its section (the register's tabs count as Transazioni); Importa and
    Esporta, the same section, by their own endpoint."""
    endpoint = _endpoint() or ""
    if entry.key == "export":
        return endpoint == entry.page.endpoint or (entry.page.endpoint == "export.import_page"
                                                   and endpoint.startswith("export.") and endpoint != "export.index")
    if entry.key == "transactions":
        return current in ("transactions", "subscriptions") or endpoint in ("reports.income", "reports.spending")
    if entry.key == "reports":
        return current == "reports" and endpoint not in ("reports.income", "reports.spending")
    if entry.key == "deadlines":
        return current in ("deadlines", "notifications")
    return current == entry.key
