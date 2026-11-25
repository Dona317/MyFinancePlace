"""
Reading the bank through PSD2 (F107): link a bank, download its movements, keep the link alive.

    «Collega una banca»  ──▶ the bank's page (consent) ──▶ callback: session + its accounts, each tied to an
                                                           account of the app (by IBAN, else chosen on the page)
    download (by hand, or by itself every few hours) ──▶ booked movements → the usual import rows (category, merchant,
                                                           giroconti, duplicates) ──▶ saved, or waiting in the preview

A movement keeps the id the bank gives it (entry_reference / transaction_id) in its import_ref: downloaded again it is
recognised, whatever its text. What looks like something already saved (the same movement imported from a statement
file, a giroconto whose other side is saved) always waits for the user's look; with «salva da solo» off, everything
does. The automatic download runs four times a day at most (PSD2 allows four unattended reads a day per account), all of
them in the hours the app is used: the window 8–24 (local time) cut in four slots — 8, 12, 16, 20 — one read per slot.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from flask import current_app, request
from flask_babel import gettext as _

from app.extensions import db
from app.models.account import Account
from app.models.bank_link import BankAccessLog, BankAccountLink, BankConnection
from app.models.transaction import Transaction
from app.services import accounts, bank_import, field_crypto, money, request_cache, reversals, studio
from app.services import cards as card_service
from app.services.parsing import clean_text, to_date

from . import client, credentials, store

INITIAL_DAYS = 90         # history read the first time (most banks give at least 90 days)
OVERLAP_DAYS = 7          # read again from a week before the last booked movement: late bookings are not missed
SHORTER_DAYS = (89, 30)   # the period refused by the bank (WRONG_TRANSACTIONS_PERIOD): asked again from these days back
SYNC_WINDOW = (8, 24)     # automatic downloads only between these local hours (config BANK_SYNC_WINDOW)
READS_PER_DAY = 4         # …cut into this many slots, one read each (config BANK_SYNC_PER_DAY; PSD2: 4 at most)
CONSENT_DAYS = 180        # the longest consent asked for; the bank's own maximum when lower
EXPIRY_NOTICE_DAYS = 14   # the reminder to renew appears this many days before the end
PENDING = "open_banking.pending"  # the consents waiting for the bank's answer (studio database): state → what to do
PENDING_MINUTES = 60      # a consent not answered within this time is forgotten
PENDING_KEPT = 20
KEEP_SKIPPED = 1000       # movements left out in the preview remembered per account (the newest)
BOOKED = "BOOK"
BALANCE_TYPES = ("CLBD", "ITBD", "XPCD", "ITAV", "CLAV", "OTHR")  # preferred first
BOOKED_BALANCES = ("CLBD", "ITBD")  # only booked movements: what the downloaded ones add up to (no pending)


def _utcnow() -> datetime:
    """Now in UTC, without the zone (as the app stores its times)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BankingError(Exception):
    """Something the user must hear about (Italian message)."""


@dataclass
class SyncResult:
    link: BankAccountLink
    saved: int = 0
    waiting: int = 0
    pending_at_bank: int = 0     # not booked yet at the bank: they come with a later download
    error: str | None = None
    created: list = field(default_factory=list)  # the transactions saved by this download
    aligned: Decimal | None = None  # the difference with the bank's balance, recorded by this download


@dataclass
class _Downloaded:
    rows: list = field(default_factory=list)
    refs: list = field(default_factory=list)
    at_bank: list = field(default_factory=list)   # not booked yet: {date, description, amount, currency}

    @property
    def pending(self) -> int:
        return len(self.at_bank)


# ── The application's credentials ───────────────────────────────────────────

def _credentials() -> client.Credentials:
    found = credentials.current()
    if found is None:
        raise BankingError(_("Collegamento bancario non configurato: inserisci l'ID dell'applicazione Enable Banking "
                             "e la sua chiave privata."))
    return found


def configured() -> bool:
    return credentials.current() is not None


def check_application(redirect_url: str) -> dict:
    """What Enable Banking says about the application: name, environment, active, the redirect URLs registered and
    whether the app's own is among them. BankingError when the credentials are refused or the API is not reachable."""
    try:
        info = client.application(_credentials())
    except client.ProviderError as exc:
        raise BankingError(_message(exc)) from exc
    urls = [str(u) for u in (info.get("redirect_urls") or [])]
    environment = str(info.get("environment") or "").upper() or None
    return {"name": info.get("name"), "environment": environment, "active": info.get("active"),
            "redirect_urls": urls, "redirect_ok": redirect_url in urls if urls else None,
            "production": environment == "PRODUCTION"}


def describe_application(info: dict, redirect_url: str) -> list[tuple[str, str]]:
    """The check as messages for the page: (level, text), worst first."""
    found = []
    if info["active"] is False:
        found.append(("warning", _("L'applicazione non è attiva: nel pannello di Enable Banking usa «Activate by linking "
                                   "accounts» e collega i tuoi conti.")))
    if info["redirect_ok"] is False:
        found.append(("warning", _("L'indirizzo di ritorno dell'app (%(url)s) non è tra quelli registrati "
                                   "nell'applicazione: aggiungilo nel pannello di Enable Banking.", url=redirect_url)))
    environment = {"PRODUCTION": _("Production (banche vere)"), "SANDBOX": _("Sandbox (banche di prova)")}.get(
        info["environment"] or "", info["environment"] or "?")
    state = {True: _("attiva"), False: _("non attiva")}.get(info["active"], _("stato non indicato"))
    found.append(("success", _("Applicazione «%(name)s» · %(environment)s · %(state)s.", name=info["name"] or "?",
                               environment=environment, state=state)))
    return found


def psu_headers() -> dict:
    """The user is there (a download asked from a page): the bank does not count it among the unattended ones."""
    return {"Psu-Ip-Address": request.remote_addr or "", "Psu-User-Agent": request.headers.get("User-Agent", "")}


def _message(exc: client.ProviderError) -> str:
    if exc.status == 0:
        return _("Enable Banking non raggiungibile: controlla la connessione a internet (%(detail)s).", detail=exc)
    if exc.status in (401, 403) and not exc.consent_gone:
        return _("Enable Banking ha rifiutato le credenziali: controlla l'ID dell'applicazione e la chiave privata "
                 "(%(detail)s).", detail=exc)
    return _("Enable Banking: %(detail)s", detail=exc)


# ── The banks ─────────────────────────────────────────────────────────────────

_banks_kept: dict[tuple, tuple[float, list]] = {}  # (application, country) → (until, banks): the list rarely changes
BANKS_KEEP_SECONDS = 12 * 3600


def banks(country: str = "IT") -> list[dict]:
    """The banks of a country: {name, country, logo, max_days}, by name (kept for a few hours)."""
    creds = _credentials()
    key = (creds.app_id, country)
    kept = _banks_kept.get(key)
    if kept and kept[0] > time.monotonic():
        return kept[1]
    try:
        found = client.aspsps(creds, country)
    except client.ProviderError as exc:
        raise BankingError(_message(exc)) from exc
    items = []
    for item in found:
        if not item.get("name"):
            continue
        seconds = item.get("maximum_consent_validity")
        items.append({"name": item["name"], "country": item.get("country") or country, "logo": item.get("logo"),
                      "max_days": int(seconds) // 86400 if isinstance(seconds, (int, float)) and seconds else None,
                      "psu_types": item.get("psu_types") or ["personal"]})
    items.sort(key=lambda b: b["name"].casefold())
    _banks_kept[key] = (time.monotonic() + BANKS_KEEP_SECONDS, items)
    return items


def _consent_end(aspsp: str, country: str, now: datetime) -> datetime:
    days = CONSENT_DAYS
    try:
        match = next((b for b in banks(country) if b["name"] == aspsp), None)
    except BankingError:
        match = None
    if match and match["max_days"]:
        days = max(1, min(days, match["max_days"]))
    return now + timedelta(days=days)


# ── Giving (and renewing) the consent ─────────────────────────────────────────

def start(aspsp: str, country: str, redirect_url: str, connection: BankConnection | None = None,
          psu_type: str = "personal", now: datetime | None = None, account: Account | None = None) -> str:
    """The bank's page where the user gives the consent; what to do on the way back is kept in the studio database. A new
    connection always starts from an account of the app (`account`): the bank's account becomes that one's."""
    aspsp, country = (aspsp or "").strip(), (country or "IT").strip().upper()[:2]
    if not aspsp:
        raise BankingError(_("Scegli la banca da collegare."))
    if connection is None and not linkable(account):
        raise BankingError(_("Si collega a partire da un conto: apri il conto in Conti e Carte, poi «Collega a Enable "
                             "Banking»."))
    now = now or _utcnow()
    state = new_state()
    try:
        answer = client.start_authorization(_credentials(), aspsp, country, redirect_url, state,
                                            _consent_end(aspsp, country, now), psu_type)
    except client.ProviderError as exc:
        if "redirect" in str(exc).lower():
            raise BankingError(_("Enable Banking non accetta l'indirizzo di ritorno %(url)s: deve essere identico a uno "
                                 "di quelli registrati nell'applicazione (anche la «/» finale). Correggilo in Gestione "
                                 "PSD2 → «Indirizzo di ritorno https».", url=redirect_url)) from exc
        raise BankingError(_message(exc)) from exc
    if not answer.get("url"):
        raise BankingError(_("Enable Banking non ha indicato la pagina della banca: riprova."))
    waiting = pending_states()
    waiting[state] = {"aspsp": aspsp, "country": country, "connection": connection.id if connection else None,
                      "client": archive_id(), "account": account.id if account else None, "at": now.isoformat()}
    store.put_json(PENDING, dict(list(waiting.items())[-PENDING_KEPT:]))
    return answer["url"]


def pending_states(now: datetime | None = None) -> dict:
    """The consents waiting for the bank's answer, kept in the studio database (not in the browser's session: the
    bank may send back to another browser, the one the desktop app opened), the stale ones left out."""
    limit = (now or _utcnow()) - timedelta(minutes=PENDING_MINUTES)
    found = store.get_json(PENDING, {})
    return {k: v for k, v in (found.items() if isinstance(found, dict) else [])
            if isinstance(v, dict) and (_parse_time(v.get("at")) or limit) >= limit}


def peek(state: str | None) -> dict | None:
    """What a consent waiting under `state` was started for (None: unknown or stale)."""
    return pending_states().get(state or "")


def new_state() -> str:
    """The `state` of a consent: a random token, then the address this app is open at (`localhost:5000`), so that a
    relay page on https (the way back Production requires) knows where to send the browser back."""
    origin = base64.urlsafe_b64encode(request.host.encode()).decode().rstrip("=")
    return f"{secrets.token_urlsafe(24)}.{origin}"


def pasted_return(text: str) -> dict:
    """The query of the address the bank sent the browser back to, pasted by the user (when the way back did not
    load): {state, code, error, error_description}. ValueError when it has neither a code nor an error."""
    query = urllib.parse.urlsplit((text or "").strip()).query
    values = {k: v[0] for k, v in urllib.parse.parse_qs(query).items() if v}
    if not values.get("state") or not (values.get("code") or values.get("error")):
        raise ValueError("no state and code")
    return {k: values[k] for k in ("state", "code", "error", "error_description") if values.get(k)}


def archive_id() -> int:
    """The archive open now (the primary one when none was chosen): every consent belongs to one."""
    current = studio.current()
    return current.id if current is not None else studio.primary().id


def _parse_time(value) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is not None:  # kept in UTC, without the zone (like the app's other times)
        moment = moment.replace(tzinfo=None) - moment.utcoffset()
    return moment


def _clean_iban(value: str | None) -> str | None:
    text = (value or "").replace(" ", "").upper()
    return text or None


def match_account(iban: str | None) -> Account | None:
    """The app's account with this IBAN (or whose account number is inside it)."""
    iban = _clean_iban(iban)
    if not iban:
        return None
    for account in accounts.active():
        if _clean_iban(account.iban) == iban:
            return account
    return accounts.found_in(iban)


def _account_fields(item: dict) -> dict:
    ids = item.get("account_id") or {}
    return {"uid": str(item.get("uid") or ""), "iban": _clean_iban(ids.get("iban")),
            "name": clean_text(item.get("name") or item.get("product") or item.get("details")),
            "currency": (item.get("currency") or "EUR").upper()[:3]}


def _update_links(connection: BankConnection, items: list[dict]) -> None:
    """The accounts of a new session: the links already there keep their account (matched by IBAN, else by name),
    the new ones are matched to an account of the app by IBAN; the others are kept, not read, until the user ties
    them to one of their accounts."""
    old = list(connection.links)
    seen = set()
    for item in items:
        values = _account_fields(item)
        if not values["uid"]:
            continue
        link = next((k for k in old if k.id not in seen and values["iban"] and k.iban == values["iban"]), None) or \
            next((k for k in old if k.id not in seen and not values["iban"] and k.name == values["name"]), None)
        if link is None:  # read only when it is one of the app's accounts: no movements for an account not made yet
            found = match_account(values["iban"])
            link = BankAccountLink(active=found is not None, account_id=found.id if found else None)
            connection.links.append(link)
        else:
            seen.add(link.id)
        link.uid, link.iban, link.name, link.currency = values["uid"], values["iban"], values["name"], values["currency"]


def finish(state: str | None, code: str | None, error: str | None = None) -> tuple[BankConnection, Account | None]:
    """Back from the bank: the consent becomes a connection (new, or the one being renewed) with its accounts; also
    returns the account of the app the new consent was started from."""
    waiting = pending_states()
    pending = waiting.pop(state or "", None)
    store.put_json(PENDING, waiting)  # used once
    if pending is None:
        raise BankingError(_("Collegamento non riconosciuto o scaduto: ricomincia dal conto, con «Collega a Enable "
                             "Banking»."))
    if pending.get("client") != archive_id():
        raise BankingError(_("Il collegamento era stato avviato in un altro archivio: aprilo e ricomincia."))
    if error or not code:
        raise BankingError(_("La banca non ha dato il consenso (%(detail)s).", detail=error or _("annullato")))
    creds = _credentials()
    try:
        answer = client.create_session(creds, code)
    except client.ProviderError as exc:
        raise BankingError(_message(exc)) from exc
    connection = db.session.get(BankConnection, pending.get("connection") or 0)
    if connection is None:
        connection = BankConnection(aspsp_name=pending["aspsp"], aspsp_country=pending["country"])
        db.session.add(connection)
    else:
        _forget_session(creds, connection)  # the old consent is replaced: withdrawn at the bank too
    connection.session_enc = field_crypto.encrypt(answer.get("session_id"))
    connection.valid_until = _parse_time((answer.get("access") or {}).get("valid_until"))
    connection.status, connection.last_error = "active", None
    _update_links(connection, list(answer.get("accounts") or []))
    db.session.flush()
    account = db.session.get(Account, pending.get("account") or 0)
    _attach_new(connection, account)
    log(connection, "consent")
    db.session.commit()
    return connection, account


# ── The account of the app a bank account belongs to ─────────────────────────

def linkable(account: Account | None) -> bool:
    """An account a bank can be linked to: an active one of the user's (not Contanti, not Debiti)."""
    return account is not None and account.active and not account.fixed and account.kind not in ("cash", "debt")


def links_of(account: Account) -> list[BankAccountLink]:
    return BankAccountLink.query.filter_by(account_id=account.id).order_by(BankAccountLink.id).all()


def free_links() -> list[BankAccountLink]:
    """Bank accounts already authorised in a consent and tied to no account of the app: one of them can become an
    account's without asking the bank again."""
    return [k for k in BankAccountLink.query.filter(BankAccountLink.account_id.is_(None)).order_by(BankAccountLink.id)
            if k.connection.status == "active"]


def attach(link: BankAccountLink, account: Account) -> None:
    """The bank's account `link` is `account`: its movements go there, and it is read."""
    link.account_id, link.active = account.id, True


def detach(account: Account) -> int:
    """The bank accounts tied to `account` stop being read (the consent stays: other accounts may use it)."""
    found = links_of(account)
    for link in found:
        link.account_id, link.active = None, False
    db.session.commit()
    return len(found)


def needs_choice(connection: BankConnection, account: Account | None) -> bool:
    """Back from the bank with several accounts and none recognised as `account`: the user says which one it is."""
    return account is not None and not any(k.account_id == account.id for k in connection.links)


def _attach_new(connection: BankConnection, account: Account | None) -> None:
    """The consent started from `account`: the only account of the bank, or the one with its IBAN, is that one."""
    if account is None or any(k.account_id == account.id for k in connection.links):
        return
    unmatched = [k for k in connection.links if k.account_id is None]
    if len(connection.links) == 1 and unmatched:
        attach(unmatched[0], account)


def session_id(connection: BankConnection) -> str | None:
    try:
        return field_crypto.decrypt(connection.session_enc)
    except field_crypto.Unreadable:
        return None


def _forget_session(creds: client.Credentials, connection: BankConnection) -> None:
    sid = session_id(connection)
    if not sid:
        return
    try:
        client.delete_session(creds, sid)
    except client.ProviderError:
        pass  # already gone at the bank, or not reachable: the consent ends by itself anyway


def disconnect(connection: BankConnection) -> None:
    """Withdraw the consent and forget the connection; the movements already saved stay."""
    found = credentials.current()
    if found is not None:
        _forget_session(found, connection)
    db.session.delete(connection)
    db.session.commit()


def encrypted_fields() -> list[tuple[BankConnection, str]]:
    """The encrypted values of the connections, for a change of key (services.field_crypto)."""
    return [(c, "session_enc") for c in BankConnection.query.filter(BankConnection.session_enc.isnot(None))] + \
        credentials.encrypted_row()


# ── Movements ─────────────────────────────────────────────────────────────────

def _amount(item: dict) -> Decimal | None:
    raw = (item.get("transaction_amount") or {}).get("amount")
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    indicator = (item.get("credit_debit_indicator") or "").upper()
    if indicator == "DBIT":
        value = -abs(value)
    elif indicator == "CRDT":
        value = abs(value)
    return money.cents(value)


def _texts(item: dict, outgoing: bool) -> tuple[str | None, str | None, str | None]:
    """(description, details, counterparty) of a movement as the bank describes it."""
    party = item.get("creditor" if outgoing else "debtor") or {}
    party_account = item.get("creditor_account" if outgoing else "debtor_account") or {}
    counterparty = clean_text(party.get("name"))
    remittance = item.get("remittance_information") or []
    if isinstance(remittance, str):
        remittance = [remittance]
    code = item.get("bank_transaction_code") or {}
    kind = clean_text(code.get("description") if isinstance(code, dict) else None)
    description = clean_text(" ".join(str(r) for r in remittance if r)) or counterparty or kind or clean_text(item.get("note"))
    extra = [t for t in (kind, counterparty, _clean_iban(party_account.get("iban")), clean_text(item.get("note")))
             if t and (not description or t.casefold() not in description.casefold())]
    return description, " · ".join(dict.fromkeys(extra)) or None, counterparty


# The merchant category code (ISO 18245) some banks give with card payments, as a word the built-in category rules
# know (bank_import.CATEGORY_RULES): used only when the description itself says nothing
_MCC_WORDS = (
    ((5411, 5412, 5422, 5441, 5451, 5462, 5499), "supermercati"),
    ((5541, 5542, 5983), "carburanti"),
    ((4111, 4112, 4121, 4131, 4511, 4784, 4789, 7523), "trasporti"),
    ((5812, 5813, 5814), "ristorante"),
    ((4722, 7011), "viaggi"),
    ((7832, 7922, 7991, 7996, 7999), "tempo libero"),
    ((5912, 8011, 8021, 8043, 8062, 8099), "salute"),
    ((4814, 4899, 5815, 5816, 5817, 5818), "abbonamenti"),
    ((4900,), "utenze"),
    ((5200, 5251, 5712, 5719), "casa"),
)
_MCC_RANGES = (((3000, 3350), "trasporti"), ((3501, 3999), "viaggi"))  # airlines, hotels


def mcc_word(code) -> str | None:
    """The word of a merchant category code, None when unknown."""
    try:
        number = int(str(code).strip())
    except (TypeError, ValueError):
        return None
    word = next((w for codes, w in _MCC_WORDS if number in codes), None)
    return word or next((w for (low, high), w in _MCC_RANGES if low <= number <= high), None)


def provider_ref(item: dict, uid: str) -> str | None:
    """The movement's own id at the bank, as an import_ref (None: the bank gives none)."""
    value = item.get("entry_reference") or item.get("transaction_id")
    if not value:
        return None
    return hashlib.sha256(f"psd2|{uid}|{value}".encode()).hexdigest()


def to_rows(items: list[dict], uid: str, currency: str = "EUR") -> _Downloaded:
    """The booked movements as import rows (the others are counted: they come back once booked)."""
    found = _Downloaded()
    for item in items:
        booked = (item.get("status") or BOOKED).upper() == BOOKED
        day = to_date(item.get("booking_date") or item.get("value_date") or item.get("transaction_date"))
        amount = _amount(item)
        description, details, counterparty = _texts(item, (amount or 0) < 0)
        code = ((item.get("transaction_amount") or {}).get("currency") or currency).upper()[:3]
        if not booked:
            found.at_bank.append({"date": (day or date.today()).isoformat(), "description": description or _("Movimento"),
                                  "amount": str(amount) if amount is not None else None, "currency": code})
            continue
        if day is None or amount is None or not amount:
            continue
        found.rows.append(bank_import.StatementRow(
            date=day, description=description or _("Movimento"), amount=amount, details=details,
            bank_category=mcc_word(item.get("merchant_category_code")), currency=code, counterparty=counterparty))
        found.refs.append(provider_ref(item, uid))
    return found


def prepare(rows: list, refs: list, uid: str) -> list:
    """The usual import steps (type, category, merchant, giroconti, cash, similar movements), then each row's own
    import_ref where there is one, and whether it is already saved."""
    bank_import.enrich(rows, f"psd2:{uid}")
    taken: set[str] = set()
    for row, ref in zip(rows, refs):
        if ref:
            row.import_ref = ref
    existing = bank_import.already_imported([r.import_ref for r in rows])
    for row in rows:
        row.duplicate = row.import_ref in existing or row.import_ref in taken
        taken.add(row.import_ref)
    return rows


def _stored(row) -> dict:
    return {"date": row.date.isoformat(), "description": row.description, "amount": str(row.amount),
            "details": row.details, "currency": row.currency, "counterparty": row.counterparty,
            "import_ref": row.import_ref}


def _from_stored(items: list[dict]) -> tuple[list, list]:
    rows, refs = [], []
    for item in items:
        day = to_date(item.get("date"))
        try:
            amount = Decimal(str(item.get("amount")))
        except (InvalidOperation, ValueError):
            continue
        if day is None:
            continue
        rows.append(bank_import.StatementRow(date=day, description=item.get("description") or _("Movimento"),
                                             amount=amount, details=item.get("details"),
                                             currency=item.get("currency") or "EUR",
                                             counterparty=item.get("counterparty")))
        refs.append(item.get("import_ref"))
    return rows, refs


def _savable(row) -> bool:
    """Saved by the automatic download: new, and like nothing saved (no similar movement, no giroconto to join)."""
    return not row.duplicate and not row.similar_to and not row.pairs_with


def _save(rows: list, account: Account) -> list:
    created = []
    for row in rows:
        base = row.to_dict()
        tx = bank_import.build_transaction(base, bank_import.PSD2_KEY)
        bank_import.assign_account(tx, base, account)
        created.append(tx)
    card_service.assign(created)
    db.session.add_all(created)
    return created


def _keep_waiting(link: BankAccountLink, rows: list) -> None:
    kept = {item.get("import_ref"): item for item in (link.pending or [])}
    for row in rows:
        kept.setdefault(row.import_ref, _stored(row))
    link.pending = sorted(kept.values(), key=lambda item: item.get("date") or "") or None


def _balance(link: BankAccountLink, items: list[dict]) -> bool:
    """The bank's balance kept on the link; True when it is a booked one in the account's currency (it can be
    compared with the movements downloaded)."""
    by_type = {(b.get("balance_type") or "").upper(): b for b in items}
    chosen = next((by_type[t] for t in BALANCE_TYPES if t in by_type), items[0] if items else None)
    if not chosen:
        return False
    amount = chosen.get("balance_amount") or {}
    try:
        link.balance = money.cents(Decimal(str(amount.get("amount"))))
    except (InvalidOperation, ValueError):
        return False
    link.balance_date = to_date(chosen.get("reference_date")) or date.today()
    currency = (amount.get("currency") or link.currency or "EUR").upper()
    return (chosen.get("balance_type") or "").upper() in BOOKED_BALANCES and currency == (link.currency or "EUR").upper()


def align(link: BankAccountLink) -> Decimal | None:
    """
    22 Nov 2026: the account follows the bank. The app's balance on the day of the bank's booked balance is compared
    with it; a difference is recorded — in the opening balance the first time, when the account's movements all came
    from the bank connection (the money that was there before the history read), else as a «Riconciliazione»
    movement (accounts.reconcile). Movements edited by the user stay as they are. Skipped while movements of the
    account wait in the preview: the bank's balance already counts them. Returns the difference recorded.
    """
    account = link.account
    if account is None or not account.active or link.pending or link.balance is None or not link.balance_date:
        return None
    on = min(link.balance_date, date.today())
    difference = money.cents(Decimal(str(link.balance)) - Decimal(str(accounts.balance(account, on))))
    if not difference:
        account.reconciled_on, account.reconciled_balance = on, link.balance
        return None
    first_day = db.session.query(db.func.min(Transaction.date)).filter(
        (Transaction.account_id == account.id) | (Transaction.counter_account_id == account.id)).scalar()
    history_from_bank = first_day is not None and link.connection.created_at is not None \
        and first_day >= link.connection.created_at.date() - timedelta(days=INITIAL_DAYS + OVERLAP_DAYS)
    if account.reconciled_on is None and history_from_bank and not accounts.reconciliations(account, 1):
        account.opening_balance = money.cents(Decimal(str(account.opening_balance or 0)) + difference)
        account.reconciled_on, account.reconciled_balance = on, link.balance
        request_cache.clear()  # the opening balances summed so far
    else:
        accounts.reconcile(account, on, Decimal(str(link.balance)))
    return difference


def _since(link: BankAccountLink, today: date) -> date:
    """The first day asked to the bank: a week before the newest booking downloaded; for an account that never had
    one, a week before the last download that worked (25 Nov 2026: not the whole INITIAL_DAYS again each time — once
    the first minutes after the consent are over, a bank may refuse to go that far back); never after today."""
    if link.last_booked:
        start = link.last_booked - timedelta(days=OVERLAP_DAYS)
    elif link.last_sync_at:
        start = link.last_sync_at.date() - timedelta(days=OVERLAP_DAYS)
    else:
        start = today - timedelta(days=INITIAL_DAYS)
    return min(max(start, today - timedelta(days=INITIAL_DAYS)), today)


def _read(creds: client.Credentials, uid: str, since: date, today: date, psu: dict | None) -> list[dict]:
    """The movements from `since`; when the bank refuses the period, again from a nearer day (SHORTER_DAYS)."""
    starts = [since] + [d for d in (today - timedelta(days=n) for n in SHORTER_DAYS) if d > since]
    for start in starts[:-1]:
        try:
            return client.transactions(creds, uid, start, psu=psu)
        except client.ProviderError as exc:
            if not exc.wrong_period:
                raise
    return client.transactions(creds, uid, starts[-1], psu=psu)


def sync_link(link: BankAccountLink, creds: client.Credentials, today: date | None = None,
              psu: dict | None = None) -> SyncResult:
    """Download one account's new movements: saved (auto_save, account chosen) or kept waiting for the preview."""
    today = today or date.today()
    result = SyncResult(link)
    items = _read(creds, link.uid, _since(link, today), today, psu)
    downloaded = to_rows(items, link.uid, link.currency)
    result.pending_at_bank = downloaded.pending
    link.at_bank = sorted(downloaded.at_bank, key=lambda item: item["date"], reverse=True) or None
    skipped = set(link.skipped or [])
    rows = [r for r in prepare(downloaded.rows, downloaded.refs, link.uid) if not r.duplicate and r.import_ref not in skipped]
    account = link.account if link.account and link.account.active else None
    if account is not None and link.connection.auto_save:
        savable = [r for r in rows if _savable(r)]
        result.created = _save(savable, account)
        result.saved = len(result.created)
        rows = [r for r in rows if not _savable(r)]
    _keep_waiting(link, rows)
    result.waiting = len(link.pending or [])
    if downloaded.rows:
        newest = max(r.date for r in downloaded.rows)
        link.last_booked = max(newest, link.last_booked) if link.last_booked else newest
    try:
        comparable = _balance(link, client.balances(creds, link.uid, psu=psu))
    except client.ProviderError:
        comparable = False  # the movements matter; the balance comes with the next download
    if comparable:
        db.session.flush()
        result.aligned = align(link)
    link.last_sync_at = _utcnow()
    return result


def sync_connection(connection: BankConnection, today: date | None = None, psu: dict | None = None,
                    now: datetime | None = None, kind: str | None = None) -> list[SyncResult]:
    """Every active account of a connection; the consent's state and the last error are kept on it. An account the
    bank refuses does not stop the others (25 Nov 2026): its error is kept, named after it; BankingError when every
    account failed or the consent is gone."""
    now = now or _utcnow()
    if connection.valid_until and connection.valid_until <= now:
        connection.status = "expired"
        db.session.commit()
        raise BankingError(_("Il consenso per %(bank)s è scaduto: rinnovalo.", bank=connection.aspsp_name))
    creds = _credentials()
    kind = kind or ("manual" if psu else "auto")
    results, errors = [], []
    links = [k for k in connection.links if k.active]
    for link in links:
        try:
            results.append(sync_link(link, creds, today, psu))
            db.session.commit()
        except client.ProviderError as exc:
            db.session.rollback()
            if exc.consent_gone:
                connection.status = "expired"
                connection.last_error = _message(exc)
                log(connection, kind, results, connection.last_error)
                db.session.commit()
                raise BankingError(connection.last_error) from exc
            # named after its account when the consent has several
            errors.append(_("%(account)s — %(error)s", account=_link_name(link), error=_message(exc))
                          if len(links) > 1 else _message(exc))
    connection.last_error = "; ".join(errors) or None
    log(connection, kind, results, connection.last_error)
    db.session.commit()
    created = [tx.id for r in results for tx in r.created]
    if created:  # F108: what was saved by itself and cancels a movement already there (a causale says «storno»)
        reversals.auto_link(created)
        db.session.commit()
    if errors and not results:
        raise BankingError(connection.last_error)
    return results


def _link_name(link: BankAccountLink) -> str:
    """The account an error is about: the app's name for it, else the bank's, else the end of the IBAN."""
    if link.account is not None:
        return link.account.name
    return link.name or (f"•••• {link.iban[-4:]}" if link.iban else link.uid)


def log(connection: BankConnection, kind: str, results: list[SyncResult] = (), error: str | None = None) -> None:
    """One access to the bank, in the archive it was made for (committed by the caller)."""
    db.session.add(BankAccessLog(
        connection_id=connection.id, bank=connection.aspsp_name, at=_utcnow(), kind=kind, ok=error is None,
        saved=sum(r.saved for r in results), waiting=sum(r.waiting for r in results),
        at_bank=sum(r.pending_at_bank for r in results), message=error))


def unattended_today(connection: BankConnection, now: datetime | None = None) -> int:
    """The automatic reads of the day (local) for a connection: PSD2 allows four per account."""
    now = now or _utcnow()
    local = _local(now)
    start = now - (local - local.replace(hour=0, minute=0, second=0, microsecond=0))  # local midnight, in UTC
    return BankAccessLog.query.filter(BankAccessLog.connection_id == connection.id, BankAccessLog.kind == "auto",
                                      BankAccessLog.at >= start).count()


def summary(results: list[SyncResult]) -> str:
    saved, waiting = sum(r.saved for r in results), sum(r.waiting for r in results)
    later = sum(r.pending_at_bank for r in results)
    parts = [_("%(count)s movimenti salvati", count=saved), _("%(count)s da controllare", count=waiting)]
    if later:
        parts.append(_("%(count)s non ancora contabilizzati", count=later))
    aligned = [r for r in results if r.aligned]
    if aligned:
        parts.append(_("saldo allineato alla banca (differenza %(amount)s)",
                       amount=", ".join(f"{r.aligned:+.2f}".replace(".", ",") for r in aligned)))
    return ", ".join(parts) + "."


# ── The preview of what waits ────────────────────────────────────────────────

def waiting_preview(link: BankAccountLink):
    """The movements waiting on a link, as the usual editable import preview (the ones saved meanwhile drop out)."""
    rows, refs = _from_stored(link.pending or [])
    rows = [r for r in prepare(rows, refs, link.uid) if not r.duplicate]
    link.pending = [_stored(r) for r in rows] or None
    db.session.commit()
    return bank_import.StatementPreview(bank=bank_import.layout_named(bank_import.PSD2_KEY), rows=rows,
                                        pending_skipped=0)


def forget_saved(link: BankAccountLink, dropped: set[str] = frozenset()) -> None:
    """After the preview's confirmation: the rows now saved (or left out on purpose) stop waiting."""
    refs = [item.get("import_ref") for item in (link.pending or [])]
    dropped = set(dropped) & set(refs)
    saved = bank_import.already_imported(refs) | dropped
    link.pending = [item for item in (link.pending or []) if item.get("import_ref") not in saved] or None
    if dropped:
        link.skipped = [*[r for r in (link.skipped or []) if r not in dropped], *sorted(dropped)][-KEEP_SKIPPED:]
    db.session.commit()


# ── By itself ─────────────────────────────────────────────────────────────────

def _window() -> tuple[int, int, int]:
    """(first hour, last hour, reads a day) of the automatic downloads."""
    start, end = current_app.config.get("BANK_SYNC_WINDOW", SYNC_WINDOW)
    reads = max(1, min(4, int(current_app.config.get("BANK_SYNC_PER_DAY", READS_PER_DAY))))
    return int(start), int(end), reads


def _local(now_utc: datetime) -> datetime:
    """The computer's local time of a UTC moment (the window is in the user's hours)."""
    return now_utc.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)


def slot_start(now: datetime | None = None) -> datetime | None:
    """Start (UTC) of the download slot `now` falls in; None outside the window."""
    now = now or _utcnow()
    local = _local(now)
    start, end, reads = _window()
    if not start <= local.hour < end:
        return None
    length = (end - start) / reads
    index = int((local.hour - start + local.minute / 60) // length)
    begins = local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=start + index * length)
    return now - (local - begins)


def slots() -> list[str]:
    """The local hours the slots start at («8:00», «12:00»…), for the page."""
    start, end, reads = _window()
    length = (end - start) / reads
    return [f"{int(start + i * length)}:{int((start + i * length) % 1 * 60):02d}" for i in range(reads)]


def due(connection: BankConnection, now: datetime | None = None) -> bool:
    """An automatic download is due: inside the window, none yet in this slot, under the reads of the day."""
    now = now or _utcnow()
    if not connection.auto_sync or connection.status != "active":
        return False
    links = [k for k in connection.links if k.active]
    begins = slot_start(now)
    if not links or begins is None:
        return False
    if unattended_today(connection, now) >= _window()[2]:
        return False
    oldest = min((k.last_sync_at for k in links), default=None, key=lambda t: t or datetime.min)
    return oldest is None or oldest < begins


def sync_due(now: datetime | None = None) -> int:
    """The automatic round of the open archive: every connection due; returns the movements saved or waiting."""
    if not configured():
        return 0
    moved = 0
    for connection in BankConnection.query.order_by(BankConnection.id).all():
        if not due(connection, now):
            continue
        try:
            moved += sum(r.saved + r.waiting for r in sync_connection(connection, now=now))
        except BankingError:
            continue  # kept on the connection: the page and the reminders say it
    return moved


def sync_all_archives(now: datetime | None = None) -> int:
    """The desktop app's round: every archive's connections that are due."""
    moved = 0
    for item in [c for c in studio.clients() if not c.archived]:
        with studio.using(item):
            moved += sync_due(now)
    return moved


_lock = threading.Lock()
_running: set = set()


def anything_due() -> bool:
    try:
        return configured() and any(due(c) for c in BankConnection.query.all())
    except Exception:  # noqa: BLE001 - an archive not upgraded yet: nothing to do
        db.session.rollback()
        return False


def run_in_background() -> None:
    """On a page visit: the connections due downloaded in a thread, so the page does not wait for the banks."""
    if not anything_due():
        return
    current = studio.current()
    if current_app.config.get("BANK_SYNC_INLINE"):
        sync_due()
        return
    key = current.id if current is not None else None
    with _lock:
        if key in _running:
            return
        _running.add(key)
    app = current_app._get_current_object()
    threading.Thread(target=_thread, args=(app, current, key), daemon=True, name="bank-sync").start()


def _thread(app, current, key) -> None:
    try:
        with app.app_context(), app.test_request_context("/"):
            studio.activate(current)
            sync_due()
    except Exception:  # noqa: BLE001 - a failed download must not hurt the app; the next round tries again
        app.logger.exception("bank movements not downloaded")
    finally:
        with _lock:
            _running.discard(key)


# ── When the app is opened ────────────────────────────────────────────────────

OPEN_SKIP_MINUTES = 30    # a connection read less than this ago is not read again when the app opens


def opened_due(connection: BankConnection, now: datetime | None = None) -> bool:
    """Read when the app opens: an active connection, with its automatic downloads on, not read in the last minutes."""
    now = now or _utcnow()
    links = [k for k in connection.links if k.active]
    if not connection.auto_sync or connection.status != "active" or not links:
        return False
    if connection.valid_until and connection.valid_until <= now:
        return False
    newest = max((k.last_sync_at for k in links if k.last_sync_at), default=None)
    return newest is None or now - newest >= timedelta(minutes=OPEN_SKIP_MINUTES)


def sync_on_open(psu: dict, now: datetime | None = None) -> int:
    """The app was just opened: every connection of the open archive read now, with the user there (the bank does not
    count it among the four unattended reads of the day). Returns the movements saved or waiting."""
    if not configured():
        return 0
    moved = 0
    for connection in BankConnection.query.order_by(BankConnection.id).all():
        if not opened_due(connection, now):
            continue
        try:
            moved += sum(r.saved + r.waiting for r in sync_connection(connection, psu=psu, now=now, kind="open"))
        except BankingError:
            continue  # kept on the connection: the page and the reminders say it
    return moved


def run_on_open() -> None:
    """On the first page of a visit: the bank connections read in a thread, the page does not wait."""
    try:
        wanted = configured() and any(opened_due(c) for c in BankConnection.query.all())
    except Exception:  # noqa: BLE001 - an archive not upgraded yet: nothing to do
        db.session.rollback()
        return
    if not wanted:
        return
    psu = psu_headers()
    if current_app.config.get("BANK_SYNC_INLINE"):
        sync_on_open(psu)
        return
    current = studio.current()
    key = ("open", current.id if current is not None else None)
    with _lock:
        if key in _running:
            return
        _running.add(key)
    app = current_app._get_current_object()
    threading.Thread(target=_open_thread, args=(app, current, key, psu), daemon=True, name="bank-open").start()


def _open_thread(app, current, key, psu) -> None:
    try:
        with app.app_context(), app.test_request_context("/"):
            studio.activate(current)
            sync_on_open(psu)
    except Exception:  # noqa: BLE001 - a failed download must not hurt the app
        app.logger.exception("bank movements not downloaded when the app opened")
    finally:
        with _lock:
            _running.discard(key)


# ── Every archive at once (Gestione PSD2) ─────────────────────────────────────

LOG_SHOWN = 30


def archives_shown() -> list:
    """The archives the page shows: all of them to whoever moves between archives, else only the open one."""
    if studio.sees_archives():
        return [c for c in studio.clients() if not c.archived]
    return [studio.current() or studio.primary()]


def _connection_view(connection: BankConnection, now: datetime) -> dict:
    links = [k for k in connection.links if k.active]
    return {"id": connection.id, "bank": connection.aspsp_name, "country": connection.aspsp_country,
            "expired": connection.status != "active" or bool(connection.valid_until and connection.valid_until <= now),
            "valid_until": connection.valid_until, "accounts": len(links),
            "mapped": sum(1 for k in links if k.account_id), "waiting": sum(len(k.pending or []) for k in links),
            "at_bank": sum(len(k.at_bank or []) for k in links),
            "last_sync": max((k.last_sync_at for k in links if k.last_sync_at), default=None),
            "auto_sync": connection.auto_sync, "auto_today": unattended_today(connection, now),
            "error": connection.last_error}


def overview(now: datetime | None = None) -> tuple[list[dict], list[dict]]:
    """(the connections, the latest accesses) of every archive shown, each with its archive."""
    now = now or _utcnow()
    connections, accesses = [], []
    for item in archives_shown():
        try:
            with studio.using(item):
                for connection in BankConnection.query.order_by(BankConnection.aspsp_name, BankConnection.id):
                    connections.append({"archive": item, **_connection_view(connection, now)})
                for entry in BankAccessLog.query.order_by(BankAccessLog.at.desc()).limit(LOG_SHOWN):
                    accesses.append({"archive": item, "bank": entry.bank, "at": entry.at, "kind": entry.kind,
                                     "ok": entry.ok, "saved": entry.saved, "waiting": entry.waiting,
                                     "at_bank": entry.at_bank, "message": entry.message})
        except Exception:  # noqa: BLE001 - an archive not upgraded yet (or not reachable): left out of the list
            db.session.rollback()
    accesses.sort(key=lambda a: a["at"], reverse=True)
    return connections, accesses[:LOG_SHOWN]
