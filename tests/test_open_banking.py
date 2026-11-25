"""F107: reading the bank through PSD2 (Enable Banking), against a fake API."""
import base64
import io
import json
import re
import urllib.error
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.models.account import Account
from app.models.bank_link import BankAccountLink, BankConnection
from app.models.transaction import Transaction
from app.services import field_crypto, open_banking
from app.services.open_banking import client as eb
from app.services.open_banking import credentials, store, sync
from tests.form_helper import form_data

IBAN = "IT60X0542811101000000123456"


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture()
def pem(rsa_key):
    return rsa_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption()).decode()


@pytest.fixture(autouse=True)
def fresh(monkeypatch, app):
    sync._banks_kept.clear()
    app.config["BANK_SYNC_WINDOW"] = (0, 24)  # the tests run at any hour; the 8–24 window has its own test
    monkeypatch.delenv(credentials.ENV_ID, raising=False)
    monkeypatch.delenv(credentials.ENV_KEY, raising=False)


def tx(ref, amount, day="2026-11-10", indicator="DBIT", text="PAGAMENTO POS ESSELUNGA", status="BOOK", **extra):
    item = {"entry_reference": ref, "transaction_amount": {"amount": str(amount), "currency": "EUR"},
            "credit_debit_indicator": indicator, "status": status, "booking_date": day,
            "remittance_information": [text]}
    item.update(extra)
    return item


class FakeBank:
    """The Enable Banking API as the tests need it: records the calls, answers from its fields."""

    def __init__(self):
        self.calls, self.movements, self.fail = [], [], {}
        self.accounts = [{"uid": "acc-1", "account_id": {"iban": IBAN}, "name": "Conto Fineco", "currency": "EUR"}]
        self.valid_until = (sync._utcnow() + timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    def __call__(self, creds, method, path, params=None, body=None, psu=None):
        self.calls.append((method, path, params, body, psu))
        if path in self.fail:
            raise self.fail[path]
        if path == "/aspsps":
            return {"aspsps": [{"name": "Fineco", "country": "IT", "maximum_consent_validity": 90 * 86400},
                               {"name": "Banca Sella", "country": "IT"}, {"country": "IT"}]}
        if path == "/auth":
            return {"url": "https://bank.example/consent", "authorization_id": "a-1"}
        if path == "/sessions":
            return {"session_id": "sess-1", "accounts": self.accounts, "access": {"valid_until": self.valid_until}}
        if path.endswith("/transactions"):
            if params.get("continuation_key"):
                return {"transactions": self.movements[1:], "continuation_key": None}
            return {"transactions": self.movements[:1], "continuation_key": "next" if len(self.movements) > 1 else None}
        if path.endswith("/balances"):
            return {"balances": [{"balance_type": "ITAV", "balance_amount": {"amount": "1000.00"}},
                                 {"balance_type": "CLBD", "balance_amount": {"amount": "1234.56"},
                                  "reference_date": "2026-11-20"}]}
        return {}


@pytest.fixture()
def bank(monkeypatch, app, pem):
    fake = FakeBank()
    monkeypatch.setattr(eb, "request", fake)
    credentials.save("app-123", pem)
    return fake


def _account(name="Fineco", **values):
    """The app's account a bank is linked from (made the first time)."""
    from app.extensions import db as _db

    found = Account.query.filter_by(name=name).first()
    if found is None:
        found = Account(name=name, kind=values.pop("kind", "current"), **values)
        _db.session.add(found)
        _db.session.commit()
    return found


def _state():
    """The latest consent waiting for the bank's answer (kept in the studio database)."""
    return list(sync.pending_states())[-1]


def _connect(client, bank, aspsp="Fineco", account=None):
    account = account or _account()
    response = client.post(f"/banking/accounts/{account.id}/connect", data={"aspsp": aspsp, "country": "IT"})
    assert response.status_code == 302 and response.headers["Location"] == "https://bank.example/consent"
    state = _state()
    return client.get(f"/banking/callback?state={state}&code=c-1", follow_redirects=True)


def _fineco(db):
    return _account("Fineco", iban=IBAN)


# ── The API client ───────────────────────────────────────────────────────────

def test_the_token_is_signed_with_the_application_key(rsa_key, pem):
    jwt = eb.token(eb.Credentials("app-123", pem), now=1_000_000)
    head, body, signature = jwt.split(".")
    pad = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))  # noqa: E731
    assert json.loads(pad(head)) == {"typ": "JWT", "alg": "RS256", "kid": "app-123"}
    claims = json.loads(pad(body))
    assert claims["aud"] == "api.enablebanking.com" and claims["exp"] - claims["iat"] == eb.TOKEN_SECONDS
    rsa_key.public_key().verify(pad(signature), f"{head}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())


def test_keys_that_are_not_rsa_private_keys_are_refused():
    from cryptography.hazmat.primitives.asymmetric import ec

    other = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    for text in ("not a key", other):
        with pytest.raises(ValueError):
            eb.load_private_key(text)


class _Answer:
    def __init__(self, raw):
        self.raw = raw

    def read(self):
        return self.raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_request_signs_sends_and_reads_json(app, monkeypatch, pem):
    seen = {}

    def urlopen(call, timeout):
        seen.update(url=call.full_url, method=call.get_method(), headers=dict(call.header_items()), data=call.data)
        return _Answer(b'{"ok": true}')

    monkeypatch.setattr(eb.urllib.request, "urlopen", urlopen)
    creds = eb.Credentials("app-123", pem)
    assert eb.request(creds, "POST", "/x", {"a": 1, "b": None}, {"k": "v"}, psu={"Psu-Ip-Address": "1.2.3.4"}) == {"ok": True}
    assert seen["url"] == "https://api.enablebanking.com/x?a=1" and seen["method"] == "POST"
    assert seen["headers"]["Authorization"].startswith("Bearer ") and seen["headers"]["Psu-ip-address"] == "1.2.3.4"
    assert json.loads(seen["data"]) == {"k": "v"}
    for raw, expected in ((b"", {}), (b"[1, 2]", {"items": [1, 2]})):
        monkeypatch.setattr(eb.urllib.request, "urlopen", lambda call, timeout, raw=raw: _Answer(raw))
        assert eb.request(creds, "GET", "/y") == expected
    monkeypatch.setattr(eb.urllib.request, "urlopen", lambda call, timeout: _Answer(b"<html>"))
    with pytest.raises(eb.ProviderError, match="invalid answer"):
        eb.request(creds, "GET", "/y")


def test_request_errors_become_provider_errors(app, monkeypatch, pem):
    creds = eb.Credentials("app-123", pem)

    def refuse(body, status=422):
        def urlopen(call, timeout):
            raise urllib.error.HTTPError(call.full_url, status, "x", {}, io.BytesIO(body))
        monkeypatch.setattr(eb.urllib.request, "urlopen", urlopen)

    refuse(b'{"message": "Session expired", "code": "EXPIRED_SESSION"}')
    with pytest.raises(eb.ProviderError) as caught:
        eb.request(creds, "GET", "/z")
    assert caught.value.status == 422 and caught.value.consent_gone
    for body in (b"oops", b"[1]"):
        refuse(body, 500)
        with pytest.raises(eb.ProviderError, match="HTTP 500") as caught:
            eb.request(creds, "GET", "/z")
        assert not caught.value.consent_gone

    def offline(call, timeout):
        raise urllib.error.URLError("no route")
    monkeypatch.setattr(eb.urllib.request, "urlopen", offline)
    with pytest.raises(eb.ProviderError, match="no route") as caught:
        eb.request(creds, "GET", "/z")
    assert caught.value.status == 0


def test_the_calls_use_the_documented_paths(app, monkeypatch, pem):
    calls = []

    def fake(creds, method, path, params=None, body=None, psu=None):
        calls.append((method, path))
        return {"aspsps": [], "balances": [], "transactions": []}

    monkeypatch.setattr(eb, "request", fake)
    creds = eb.Credentials("app", pem)
    eb.application(creds)
    eb.aspsps(creds, "IT")
    eb.start_authorization(creds, "Fineco", "IT", "https://x/cb", "st", datetime(2027, 1, 1))
    eb.create_session(creds, "code")
    eb.get_session(creds, "s/1")
    eb.delete_session(creds, "s/1")
    eb.balances(creds, "u 1")
    eb.transactions(creds, "u 1", date(2026, 1, 1), date(2026, 2, 1))
    assert calls == [("GET", "/application"), ("GET", "/aspsps"), ("POST", "/auth"), ("POST", "/sessions"),
                     ("GET", "/sessions/s%2F1"), ("DELETE", "/sessions/s%2F1"), ("GET", "/accounts/u%201/balances"),
                     ("GET", "/accounts/u%201/transactions")]


# ── The credentials ──────────────────────────────────────────────────────────

def test_credentials_saved_encrypted_in_the_studio_database(app, db, pem):
    assert credentials.current() is None and credentials.status()["configured"] is False
    with pytest.raises(ValueError):
        credentials.save(" ", pem)
    with pytest.raises(ValueError):
        credentials.save("app", "junk")
    credentials.save(" app-1 ", pem)
    stored = credentials._stored()
    assert stored.startswith(field_crypto.PREFIX) and "BEGIN" not in stored and "app-1" not in stored
    assert json.loads(field_crypto.decrypt(stored)) == {"app_id": "app-1", "key": pem, "redirect_url": None}
    assert credentials.current() == eb.Credentials("app-1", pem)
    assert credentials.status() == {"configured": True, "environment": False, "app_id": "app-1", "redirect_url": None}
    credentials.save("app-2", pem)  # replaced, not added
    assert credentials.current().app_id == "app-2"
    assert credentials.encrypted_row()[0][1] == "value"  # follows a change of the data key
    credentials._write(field_crypto.encrypt("{bad json"))
    assert credentials.current() is None
    credentials._write(json.dumps({"app_id": "x", "key": None}))
    assert credentials.current() is None
    credentials.remove()
    assert credentials._stored() is None and credentials.encrypted_row() == []


def test_the_older_file_moves_into_the_database(app, db, pem):
    credentials._legacy_path().write_text(json.dumps({"app_id": "old", "key": field_crypto.encrypt(pem)}))
    assert credentials.current() == eb.Credentials("old", pem)
    assert not credentials._legacy_path().exists() and credentials._stored().startswith(field_crypto.PREFIX)
    assert credentials.current() == eb.Credentials("old", pem)


def test_the_key_never_reaches_the_page(client, db, bank, pem):
    for url in ("/banking/manage", "/banking/"):
        html = client.get(url).get_data(as_text=True)
        assert "PRIVATE KEY-----\n" not in html and pem.splitlines()[1] not in html


def test_no_encrypted_row_from_a_client_archive(app, db, monkeypatch, pem):
    from app.services import studio

    credentials.save("app", pem)
    monkeypatch.setattr(studio, "current", lambda: type("C", (), {"is_primary": False})())
    assert credentials.encrypted_row() == []


def test_credentials_from_the_environment(app, monkeypatch, pem, tmp_path):
    key = tmp_path / "eb.pem"
    key.write_text(pem)
    monkeypatch.setenv(credentials.ENV_ID, "env-app")
    monkeypatch.setenv(credentials.ENV_KEY, str(key))
    assert credentials.current() == eb.Credentials("env-app", pem) and credentials.status()["environment"]
    monkeypatch.setenv(credentials.ENV_KEY, str(tmp_path / "missing.pem"))
    assert credentials.current() is None


def test_credentials_page(client, db, pem, monkeypatch):
    html = client.get("/banking/manage").get_data(as_text=True)
    assert "Da configurare" in html and "/banking/callback" in html
    assert "Nessuna banca collegata" in client.get("/banking/").get_data(as_text=True)
    response = client.post("/banking/credentials", data={"app_id": "app-9", "key_text": "nope"}, follow_redirects=True)
    assert "Servono l&#39;ID" in response.get_data(as_text=True)
    client.post("/banking/credentials", data={"app_id": "app-9", "file": (io.BytesIO(pem.encode()), "key.pem")},
                content_type="multipart/form-data")
    assert credentials.current().app_id == "app-9"
    client.post("/banking/credentials/delete")
    assert credentials.current() is None
    monkeypatch.setenv(credentials.ENV_ID, "env")
    monkeypatch.setenv(credentials.ENV_KEY, "/nowhere")
    response = client.post("/banking/credentials", data={"app_id": "x", "key_text": pem}, follow_redirects=True)
    assert "impostate dal server" in response.get_data(as_text=True)


# ── Linking a bank ───────────────────────────────────────────────────────────

def test_link_a_bank_end_to_end(client, db, bank):
    fineco = _fineco(db)
    bank.movements = [tx("e1", "42.10"), tx("e2", "1500", indicator="CRDT", text="STIPENDIO NOVEMBRE",
                                             debtor={"name": "ACME SPA"}),
                      tx("e3", "9.99", status="PDNG")]
    page = client.get(f"/accounts/{fineco.id}/edit").get_data(as_text=True)
    assert "Collega a Enable Banking" in page and "scegli la banca (2)" in page and '<option value="Fineco"' in page
    html = _connect(client, bank).get_data(as_text=True)
    assert "I movimenti arrivano sul conto «Fineco»" in html and "Puoi chiudere questa scheda" in html
    assert "Fineco collegata: 1 conti." in html and "0 movimenti salvati, 2 da controllare, 1 non ancora contabilizzati" in html
    connection = BankConnection.query.one()
    link = connection.links[0]
    assert open_banking.session_id(connection) == "sess-1" and connection.session_enc != "sess-1"
    assert link.account_id == fineco.id and link.iban == IBAN and link.balance == Decimal("1234.56")
    assert link.last_booked == date(2026, 11, 10) and len(link.pending) == 2
    auth = next(c for c in bank.calls if c[1] == "/auth")[3]
    assert auth["aspsp"] == {"name": "Fineco", "country": "IT"} and auth["redirect_url"].endswith("/banking/callback")
    assert auth["access"]["valid_until"][:10] == (sync._utcnow() + timedelta(days=90)).date().isoformat()
    assert all(c[4] and "Psu-User-Agent" in c[4] for c in bank.calls if c[1].endswith("/transactions"))
    assert "Controlla 2" in client.get("/banking/").get_data(as_text=True)

    preview = client.get(f"/banking/links/{link.id}/review").get_data(as_text=True)
    assert "STIPENDIO NOVEMBRE" in preview and re.search(rf'<option value="{fineco.id}" selected', preview)
    rows = sorted(set(re.findall(r'name="include" value="(\d+)"', preview)), key=int)
    salary = next(i for i in rows if re.search(rf'name="description-{i}"[^>]*title="STIPENDIO', preview))
    client.post("/export/bank/confirm", data=form_data(preview, "preview-form", include=[salary]))
    saved = Transaction.query.one()
    assert saved.type == "income" and saved.account_id == fineco.id and "psd2" in saved.tags
    assert saved.counterparty == "ACME SPA"
    db.session.refresh(link)
    assert link.pending is None and len(link.skipped) == 1  # the POS payment was left out on purpose

    # the next download brings neither the saved movement nor the one left out
    client.post(f"/banking/connections/{connection.id}/sync")
    db.session.refresh(link)
    assert link.pending is None and Transaction.query.count() == 1
    since = [c[2]["date_from"] for c in bank.calls if c[1].endswith("/transactions")][-1]
    assert since == "2026-11-03"  # a week before the last booked movement
    response = client.get(f"/banking/links/{link.id}/review", follow_redirects=True)
    assert "Nessun movimento in attesa" in response.get_data(as_text=True)


def test_auto_save_keeps_only_doubtful_movements_waiting(client, db, bank):
    fineco = _fineco(db)
    db.session.add(Transaction(date=date(2026, 11, 9), description="PAGAMENTO POS ESSELUNGA", amount=Decimal("42.10"),
                               type="expense", category="Spesa", tags=[], account_id=fineco.id))
    db.session.commit()
    bank.movements = [tx("e1", "42.10"), tx("e2", "12.00", text="NETFLIX"), tx(None, "3.00", text="CAFFE")]
    _connect(client, bank)
    connection = BankConnection.query.one()
    connection.auto_save = True
    db.session.commit()
    link = connection.links[0]
    link.pending, link.last_booked = None, None
    db.session.commit()
    results = open_banking.sync_connection(connection)
    assert results[0].saved == 2 and results[0].waiting == 1  # the POS payment looks like the one already saved
    assert {t.description for t in Transaction.query.filter(Transaction.tags.any("psd2"))} == {"NETFLIX", "CAFFE"}
    # downloaded again: the bank's own ids (and the text of the one without) recognise them
    results = open_banking.sync_connection(connection)
    assert results[0].saved == 0 and results[0].waiting == 1


def test_accounts_matched_kept_and_chosen(client, db, bank):
    _fineco(db)
    bank.accounts.append({"uid": "acc-2", "account_id": {}, "name": "Carta", "currency": "EUR"})
    bank.accounts.append({"uid": "", "name": "senza id"})
    _connect(client, bank)
    connection = BankConnection.query.one()
    card = next(k for k in connection.links if k.name == "Carta")
    assert len(connection.links) == 2 and card.account_id is None and not card.active  # not read: no account yet
    other = Account(name="Altro", kind="current")
    db.session.add(other)
    db.session.commit()
    client.post(f"/banking/links/{card.id}/account", data={"account_id": other.id})
    db.session.refresh(card)
    assert card.account_id == other.id and not card.active
    client.post(f"/banking/links/{card.id}/account", data={"account_id": "", "active": "1"})
    db.session.refresh(card)
    assert card.account_id is None and card.active

    # renewing: a new session, new uids, the same links and accounts; the old consent is withdrawn
    bank.accounts = [{"uid": "acc-1b", "account_id": {"iban": IBAN}, "name": "Conto Fineco"},
                     {"uid": "acc-2b", "account_id": {}, "name": "Carta"}]
    response = client.post(f"/banking/connections/{connection.id}/renew")
    assert response.headers["Location"] == "https://bank.example/consent"
    state = _state()
    client.get(f"/banking/callback?state={state}&code=c-2")
    db.session.refresh(connection)
    assert BankConnection.query.count() == 1 and sorted(k.uid for k in connection.links) == ["acc-1b", "acc-2b"]
    assert ("DELETE", "/sessions/sess-1") in [(c[0], c[1]) for c in bank.calls]


def test_callback_refusals(client, db, bank, app):
    start = f"/banking/accounts/{_account().id}/connect"
    response = client.get("/banking/callback?state=nope&code=x", follow_redirects=True)
    assert "non riconosciuto" in response.get_data(as_text=True)
    client.post(start, data={"aspsp": "Fineco", "country": "it"})
    state = _state()
    response = client.get(f"/banking/callback?state={state}&error=access_denied", follow_redirects=True)
    assert "non ha dato il consenso (access_denied)" in response.get_data(as_text=True)
    client.post(start, data={"aspsp": "Fineco"})
    state = _state()
    waiting = sync.pending_states()
    waiting[state]["client"] = 999
    store.put_json(sync.PENDING, waiting)
    response = client.get(f"/banking/callback?state={state}&code=x", follow_redirects=True)
    assert "altro archivio" in response.get_data(as_text=True)
    client.post(start, data={"aspsp": "Fineco"})
    state = _state()
    bank.fail["/sessions"] = eb.ProviderError("Invalid code", 400)
    response = client.get(f"/banking/callback?state={state}&code=x", follow_redirects=True)
    assert "Enable Banking: Invalid code" in response.get_data(as_text=True)
    assert BankConnection.query.count() == 0


def test_connect_refusals(client, db, bank):
    account = _account()
    start = f"/banking/accounts/{account.id}/connect"
    response = client.post(start, data={"aspsp": " "}, follow_redirects=True)
    assert "Scegli la banca" in response.get_data(as_text=True)
    bank.fail["/auth"] = eb.ProviderError("down", 0)
    response = client.post(start, data={"aspsp": "Fineco"}, follow_redirects=True)
    assert "non raggiungibile" in response.get_data(as_text=True)
    del bank.fail["/auth"]
    bank.fail["/aspsps"] = eb.ProviderError("Unauthorized", 401)
    sync._banks_kept.clear()
    html = client.get(f"/accounts/{account.id}/edit?country=XX").get_data(as_text=True)
    assert "rifiutato le credenziali" in html
    original = bank.__call__

    class NoUrl(FakeBank):
        def __call__(self, *args, **kwargs):
            return {} if args[2] == "/auth" else original(*args, **kwargs)

    sync.client.request = NoUrl()
    response = client.post(start, data={"aspsp": "Fineco"}, follow_redirects=True)
    assert "non ha indicato la pagina" in response.get_data(as_text=True)


    cash = _account("Contanti", kind="cash")
    response = client.post(f"/banking/accounts/{cash.id}/connect", data={"aspsp": "Fineco"}, follow_redirects=True)
    assert "Si collega a partire da un conto" in response.get_data(as_text=True)
    assert 'id="bank-link"' not in client.get(f"/accounts/{cash.id}/edit").get_data(as_text=True)


def test_nothing_works_without_credentials(client, db):
    account = _account()
    page = client.get(f"/accounts/{account.id}/edit").get_data(as_text=True)
    assert "non è ancora configurato" in page and "Configura in Gestione PSD2" in page
    response = client.post(f"/banking/accounts/{account.id}/connect", data={"aspsp": "Fineco"}, follow_redirects=True)
    assert "non configurato" in response.get_data(as_text=True)
    assert open_banking.sync_due() == 0


def test_options_and_disconnect(client, db, bank):
    _connect(client, bank)
    connection = BankConnection.query.one()
    client.post(f"/banking/connections/{connection.id}/options", data={"auto_save": "1"})
    db.session.refresh(connection)
    assert connection.auto_save and not connection.auto_sync
    bank.fail["/auth"] = eb.ProviderError("Bank unavailable", 503)
    response = client.post(f"/banking/connections/{connection.id}/renew", follow_redirects=True)
    assert "Bank unavailable" in response.get_data(as_text=True)
    bank.fail["/sessions/sess-1"] = eb.ProviderError("gone", 404)
    response = client.post(f"/banking/connections/{connection.id}/delete", follow_redirects=True)
    assert "scollegata" in response.get_data(as_text=True)
    assert BankConnection.query.count() == 0 and BankAccountLink.query.count() == 0


# ── Consents, errors, reminders ──────────────────────────────────────────────

def test_expired_and_withdrawn_consents(client, db, bank, app):
    from app.services import notifications

    _connect(client, bank)
    connection = BankConnection.query.one()
    bank.fail["/accounts/acc-1/transactions"] = eb.ProviderError("Session is EXPIRED", 401, "EXPIRED_SESSION")
    response = client.post(f"/banking/connections/{connection.id}/sync", follow_redirects=True)
    assert "Session is EXPIRED" in response.get_data(as_text=True)
    db.session.refresh(connection)
    assert connection.status == "expired" and connection.last_error
    with app.test_request_context("/"):
        titles = [n.title for n in notifications.collect()]
    assert "Consenso scaduto: Fineco" in titles

    connection.status, connection.valid_until = "active", sync._utcnow() - timedelta(days=1)
    db.session.commit()
    with pytest.raises(open_banking.BankingError, match="scaduto"):
        open_banking.sync_connection(connection)
    assert connection.status == "expired"
    assert "Consenso scaduto" in client.get("/banking/").get_data(as_text=True)


def test_reminders_of_the_connections(client, db, bank, app):
    from app.services import notifications

    bank.movements = [tx("e1", "5")]
    _connect(client, bank)
    connection = BankConnection.query.one()
    connection.valid_until = sync._utcnow() + timedelta(days=5)
    connection.last_error = "Enable Banking: timeout"
    connection.links[0].account_id = None
    db.session.commit()
    notifications._kept.clear()
    with app.test_request_context("/"):
        titles = [n.title for n in notifications.collect()]
    assert "Consenso in scadenza: Fineco" in titles and "Download non riuscito: Fineco" in titles
    assert "1 movimenti da controllare: Conto Fineco" in titles and "Scegli il conto dell'app per Conto Fineco" in titles
    html = client.get("/banking/").get_data(as_text=True)
    assert "Consenso in scadenza" in html and "Enable Banking: timeout" in html


def test_a_failed_balance_does_not_stop_the_download(client, db, bank):
    bank.movements = [tx("e1", "5")]
    bank.fail["/accounts/acc-1/balances"] = eb.ProviderError("no balances", 500)
    _connect(client, bank)
    link = BankAccountLink.query.one()
    assert link.balance is None and len(link.pending) == 1


# ── By itself ─────────────────────────────────────────────────────────────────

def test_automatic_download_when_due(client, db, bank, app, monkeypatch):
    _connect(client, bank)
    connection = BankConnection.query.one()
    assert not open_banking.due(connection)  # just downloaded
    assert open_banking.sync_due() == 0
    later = sync._utcnow() + timedelta(hours=7)  # another slot (6 hours each in the tests)
    assert open_banking.due(connection, later)
    bank.movements = [tx("e9", "7")]
    assert open_banking.sync_due(later) == 1
    assert open_banking.sync_all_archives(later + timedelta(hours=7)) == 1  # the same one, waiting
    connection = BankConnection.query.one()
    connection.auto_sync = False
    db.session.commit()
    assert not open_banking.due(connection, later)
    connection.auto_sync = True
    for link in connection.links:
        link.active = False
    db.session.commit()
    assert not open_banking.due(connection, later)
    for link in connection.links:
        link.active, link.last_sync_at = True, None
    db.session.commit()
    bank.fail["/accounts/acc-1/transactions"] = eb.ProviderError("boom", 500)
    assert open_banking.sync_due() == 0  # the error is kept on the connection


def test_run_in_background(client, db, bank, app, monkeypatch):
    _connect(client, bank)
    link = BankAccountLink.query.one()
    link.last_sync_at = None
    db.session.commit()
    bank.movements = [tx("e5", "3")]
    app.config["BANK_SYNC_INLINE"] = True
    client.get("/dashboard")
    db.session.refresh(link)
    assert link.last_sync_at is not None and len(link.pending) == 1

    app.config["BANK_SYNC_INLINE"] = False
    started = []
    monkeypatch.setattr(sync.threading, "Thread", lambda target, args, **kw: started.append((target, args)) or
                        type("T", (), {"start": lambda self: None})())
    link.last_sync_at = None
    db.session.commit()
    open_banking.run_in_background()
    open_banking.run_in_background()  # already running for this archive
    assert len(started) == 1
    target, args = started[0]
    target(*args)  # the thread's body: downloads, then frees the archive
    assert sync._running == set()
    monkeypatch.setattr(sync, "sync_due", lambda: 1 / 0)
    target(*args)  # a failure is only logged
    link.last_sync_at = sync._utcnow()
    db.session.commit()
    open_banking.run_in_background()  # nothing due
    assert len(started) == 1


def test_anything_due_survives_an_archive_not_upgraded(app, monkeypatch, bank):
    monkeypatch.setattr(sync, "configured", lambda: 1 / 0)
    assert sync.anything_due() is False


def test_desktop_round_downloads_the_banks(app, bank, monkeypatch):
    from desktop import main

    monkeypatch.setattr(open_banking, "sync_all_archives", lambda: 3)
    assert main.sync_banks(app) == 3


def test_session_ids_follow_a_change_of_key(client, db, bank):
    _connect(client, bank)
    connection = BankConnection.query.one()
    fields = open_banking.encrypted_fields()
    assert fields[0] == (connection, "session_enc") and fields[1][1] == "value"  # and the application's credentials
    connection.session_enc = "v1:broken"
    db.session.commit()
    assert open_banking.session_id(connection) is None
    open_banking.disconnect(connection)  # no session to withdraw: only forgotten


# ── Movements → rows ─────────────────────────────────────────────────────────

def test_movements_become_import_rows(app, db):
    items = [
        tx("r1", "10", text="BONIFICO", creditor={"name": "Mario Rossi"},
           creditor_account={"iban": "IT00 X123"}, bank_transaction_code={"description": "SEPA Credit Transfer"}),
        {"transaction_id": "t2", "transaction_amount": {"amount": "-4.5", "currency": "usd"}, "value_date": "2026-11-02",
         "remittance_information": "Coffee", "note": "card 1234"},
        {"transaction_amount": {"amount": "x"}, "booking_date": "2026-11-01"},
        {"transaction_amount": {"amount": "0"}, "booking_date": "2026-11-01"},
        {"transaction_amount": {"amount": "3"}},
        {"transaction_amount": {"amount": "8"}, "credit_debit_indicator": "DBIT", "booking_date": "2026-11-03",
         "creditor": {"name": "Amazon"}},
        tx("r9", "1", status="PDNG"),
    ]
    found = open_banking.to_rows(items, "u1")
    assert found.pending == 1 and len(found.rows) == 3
    transfer, coffee, amazon = found.rows
    assert transfer.amount == Decimal("-10.00") and transfer.counterparty == "Mario Rossi"
    assert transfer.details == "SEPA Credit Transfer · Mario Rossi · IT00X123"
    assert coffee.currency == "USD" and coffee.description == "Coffee" and coffee.details == "card 1234"
    assert amazon.description == "Amazon" and amazon.amount == Decimal("-8.00")
    assert found.refs[0] == open_banking.provider_ref(items[0], "u1") and found.refs[2] is None
    assert open_banking.provider_ref({}, "u1") is None


def test_small_readers(app, db):
    assert sync._parse_time(None) is None and sync._parse_time("soon") is None
    assert sync._parse_time("2027-05-01T10:00:00+02:00") == datetime(2027, 5, 1, 8, 0)
    assert sync._parse_time("2027-05-01T10:00:00") == datetime(2027, 5, 1, 10, 0)
    link = BankAccountLink(uid="u")
    sync._balance(link, [])
    assert link.balance is None
    sync._balance(link, [{"balance_type": "XYZ", "balance_amount": {"amount": "bad"}}])
    assert link.balance is None
    sync._balance(link, [{"balance_type": "XYZ", "balance_amount": {"amount": "7"}}])
    assert link.balance == Decimal("7.00") and link.balance_date == date.today()
    rows, refs = sync._from_stored([{"date": "2026-11-01", "amount": "nope"}, {"date": "never", "amount": "1"},
                                    {"date": "2026-11-01", "amount": "-2", "import_ref": "r"}])
    assert len(rows) == 1 and refs == ["r"] and rows[0].description == "Movimento"
    assert sync.match_account(None) is None
    ok = sync.SyncResult(link=link, saved=1, waiting=2)
    assert open_banking.summary([ok]) == "1 movimenti salvati, 2 da controllare."


def test_unknown_pages_answer_404(client, db):
    assert client.post("/banking/connections/99/sync").status_code == 404
    assert client.get("/banking/links/99/review").status_code == 404


def test_the_accounts_page_links_here(client, db):
    assert "/banking/" in client.get("/accounts/").get_data(as_text=True)


# ── Gestione PSD2: every archive, the accesses, the archive of a new consent ───

@pytest.fixture()
def office(app):
    """A second archive (its own database, migrated); dropped afterwards."""
    from app.extensions import db as _db
    from app.models.client import Client
    from app.services import studio

    yield
    _db.session.rollback()
    for item in Client.query.filter(Client.database.isnot(None)).all():
        studio._drop(item)


def test_manage_page_lists_every_archive_and_links_to_the_chosen_one(client, db, bank, office):
    from app.models.client import Client

    bank.movements = [tx("e1", "5"), tx("p1", "80", status="PDNG", text="HOTEL PREAUTORIZZAZIONE")]
    _connect(client, bank)  # the primary archive
    _connect(client, bank, account=_account("Fineco cointestato"))  # a second consent in the same archive
    primary = next(c for c in open_banking.archives_shown() if c.database is None)
    client.post("/clients/new", data={"name": "Mario Rossi", "color": "#16a34a"})  # now the open archive
    rossi = Client.query.filter_by(name="Mario Rossi").one()
    bank.movements = []
    _connect(client, bank, "Banca Sella", account=_account("Sella"))
    assert not sync.pending_states()  # every consent used

    page = client.get("/banking/manage").get_data(as_text=True)
    assert "Collega a Enable Banking" in page and 'name="aspsp"' not in page  # linking starts from an account
    connections, accesses = open_banking.overview()
    assert [(c["archive"].name, c["bank"]) for c in connections] == [
        (primary.name, "Fineco"), (primary.name, "Fineco"), (rossi.name, "Banca Sella")]
    assert connections[0]["at_bank"] == 1 and connections[0]["mapped"] == 1
    assert {a["kind"] for a in accesses} == {"consent", "manual"} and len(accesses) == 6
    assert "Registro degli accessi" in page and "Mario Rossi" in page and "Consenso" in page

    response = client.post(f"/banking/manage/open/{primary.id}", data={"connection": connections[0]["id"]})
    assert response.headers["Location"].endswith(f"/banking/#connection-{connections[0]['id']}")
    html = client.get("/banking/").get_data(as_text=True)
    assert "In attesa alla banca: 1" in html and "HOTEL PREAUTORIZZAZIONE" in html
    assert "letture automatiche oggi: 0 su 4" in html and "Per collegare un altro conto" in html
    response = client.post("/banking/manage/open/999", follow_redirects=True)
    assert "Archivio non disponibile" in response.get_data(as_text=True)


def test_an_archive_left_behind_is_skipped(app, db, monkeypatch):
    from app.services import studio

    class Broken:
        def __enter__(self):
            raise RuntimeError("not upgraded")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(studio, "using", lambda item: Broken())
    assert open_banking.overview() == ([], [])


def test_accesses_are_logged_with_their_kind(client, db, bank):
    from app.models.bank_link import BankAccessLog

    _connect(client, bank)
    connection = BankConnection.query.one()
    connection.links[0].last_sync_at = None
    db.session.commit()
    open_banking.sync_due()
    bank.fail["/accounts/acc-1/transactions"] = eb.ProviderError("boom", 500)
    with pytest.raises(open_banking.BankingError):
        open_banking.sync_connection(connection, psu={"Psu-Ip-Address": "1"})
    kinds = [(e.kind, e.ok) for e in BankAccessLog.query.order_by(BankAccessLog.id)]
    assert kinds == [("consent", True), ("manual", True), ("auto", True), ("manual", False)]
    assert open_banking.unattended_today(connection) == 1
    assert BankAccessLog.query.filter_by(ok=False).one().message == "Enable Banking: boom"


def test_merchant_codes_help_the_category(app, db):
    assert open_banking.mcc_word("5411") == "supermercati" and open_banking.mcc_word(3010) == "trasporti"
    assert open_banking.mcc_word("3700") == "viaggi" and open_banking.mcc_word("1234") is None
    assert open_banking.mcc_word(None) is None and open_banking.mcc_word("x") is None
    found = open_banking.to_rows([tx("m1", "23.40", text="POS 1234 SRL XYZ", merchant_category_code="5411")], "u")
    rows = open_banking.prepare(found.rows, found.refs, "u")
    assert rows[0].bank_category == "supermercati" and rows[0].category != "Altro"


def test_pending_movements_are_shown_not_saved(app, db):
    found = open_banking.to_rows([tx("p1", "50", status="PDNG"), tx("p2", "x", status="PDNG", booking_date=None)], "u")
    assert found.rows == [] and found.pending == 2
    assert found.at_bank[0]["amount"] == "-50.00" and found.at_bank[1]["amount"] is None
    assert found.at_bank[1]["date"] == date.today().isoformat()


def test_automatic_reads_fall_in_four_slots_between_8_and_24(app, db, bank, client, monkeypatch):
    from app.models.bank_link import BankAccessLog

    app.config["BANK_SYNC_WINDOW"] = (8, 24)
    monkeypatch.setattr(sync, "_local", lambda moment: moment)  # the computer's clock in UTC, for the test
    day = datetime(2026, 11, 21)
    at = lambda h, m=0: day.replace(hour=h, minute=m)  # noqa: E731
    assert open_banking.slots() == ["8:00", "12:00", "16:00", "20:00"]
    assert open_banking.slot_start(at(7, 59)) is None and open_banking.slot_start(at(8, 30)) == at(8)
    assert open_banking.slot_start(at(13)) == at(12) and open_banking.slot_start(at(23, 59)) == at(20)
    _connect(client, bank)
    connection = BankConnection.query.one()
    for link in connection.links:
        link.last_sync_at = at(12, 10)
    db.session.commit()
    assert not open_banking.due(connection, at(15))     # already read in the 12–16 slot
    assert open_banking.due(connection, at(16, 5))      # a new slot
    assert not open_banking.due(connection, at(7))      # before the window
    db.session.add_all([BankAccessLog(connection_id=connection.id, bank="Fineco", at=at(9 + i), kind="auto")
                        for i in range(4)])
    db.session.commit()
    assert not open_banking.due(connection, at(16, 5))  # four automatic reads already today
    assert open_banking.unattended_today(connection, at(16, 5)) == 4
    app.config["BANK_SYNC_PER_DAY"] = 9  # never more than PSD2's four
    assert open_banking.slots() == ["8:00", "12:00", "16:00", "20:00"]


# ── Linking from the account (the bank's account becomes that one) ───────────

def test_several_bank_accounts_ask_which_one(client, db, bank):
    mine = _account("Conto di casa")  # no IBAN: the bank's accounts cannot be recognised
    bank.accounts = [{"uid": "a1", "account_id": {"iban": "IT11A"}, "name": "Conto principale"},
                     {"uid": "a2", "account_id": {"iban": "IT22B"}, "name": "Conto deposito"}]
    response = _connect(client, bank, account=mine)
    html = response.get_data(as_text=True)
    assert "nessuno è riconoscibile come «Conto di casa»" in html  # chosen in the app, on the account
    connection = BankConnection.query.one()
    assert all(k.account_id is None and not k.active for k in connection.links)
    assert not [c for c in bank.calls if c[1].endswith("/transactions")]  # nothing read before the choice
    url = f"/banking/connections/{connection.id}/choose/{mine.id}"
    assert "Scegli il conto della banca" in client.post(url, follow_redirects=True).get_data(as_text=True)
    deposit = next(k for k in connection.links if k.name == "Conto deposito")
    response = client.post(url, data={"link_id": deposit.id})
    assert response.headers["Location"].endswith(f"/accounts/{mine.id}/edit#bank-link")
    db.session.refresh(deposit)
    assert deposit.account_id == mine.id and deposit.active
    other = next(k for k in connection.links if k.name == "Conto principale")
    assert other.account_id is None and not other.active
    assert client.get(url).status_code == 200

    # the other bank account, already authorised, becomes another account without a new consent
    savings = _account("Risparmi")
    page = client.get(f"/accounts/{savings.id}/edit").get_data(as_text=True)
    assert "Già autorizzato dalla banca" in page and "Conto principale" in page
    auths = sum(1 for c in bank.calls if c[1] == "/auth")
    client.post(f"/banking/accounts/{savings.id}/use/{other.id}")
    db.session.refresh(other)
    assert other.account_id == savings.id and other.active and sum(1 for c in bank.calls if c[1] == "/auth") == auths
    response = client.post(f"/banking/accounts/{mine.id}/use/{other.id}", follow_redirects=True)
    assert "già collegato a un altro conto" in response.get_data(as_text=True)

    # choosing again moves the account to the bank account picked
    client.post(url, data={"link_id": other.id})
    db.session.refresh(deposit)
    assert deposit.account_id is None and not deposit.active


def test_unlink_one_account_keeps_the_consent(client, db, bank):
    account = _account()
    _connect(client, bank, account=account)
    page = client.get(f"/accounts/{account.id}/edit").get_data(as_text=True)
    assert "Scollega questo conto" in page and "Aggiorna ora" in page
    response = client.post(f"/banking/accounts/{account.id}/detach", follow_redirects=True)
    assert "non è più collegato alla banca" in response.get_data(as_text=True)
    link = BankAccountLink.query.one()
    assert link.account_id is None and not link.active and BankConnection.query.count() == 1


def test_update_and_renew_from_the_account_page(client, db, bank):
    account = _account()
    _connect(client, bank, account=account)
    connection = BankConnection.query.one()
    here = f"/accounts/{account.id}/edit#bank-link"
    response = client.post(f"/banking/connections/{connection.id}/sync", data={"next": here})
    assert response.headers["Location"].endswith(here)
    connection.valid_until = sync._utcnow() + timedelta(days=3)
    db.session.commit()
    page = client.get(f"/accounts/{account.id}/edit").get_data(as_text=True)
    assert "Consenso in scadenza" in page and "Rinnova consenso" in page
    client.post(f"/banking/connections/{connection.id}/renew", data={"account_id": account.id})
    state = _state()
    response = client.get(f"/banking/callback?state={state}&code=c-5")
    assert "I movimenti arrivano sul conto" in response.get_data(as_text=True) and BankConnection.query.count() == 1
    bank.fail["/auth"] = eb.ProviderError("Bank unavailable", 503)
    response = client.post(f"/banking/connections/{connection.id}/renew", data={"account_id": account.id})
    assert response.headers["Location"].endswith(here)
    connection.status = "expired"
    db.session.commit()
    page = client.get(f"/accounts/{account.id}/edit").get_data(as_text=True)
    assert "Consenso scaduto" in page


def test_a_user_who_is_not_administrator_sees_only_their_archive(app, db, monkeypatch):
    from app.services import studio

    monkeypatch.setattr(studio, "sees_archives", lambda: False)
    with app.test_request_context("/"):
        assert open_banking.archives_shown() == [studio.primary()]


def test_check_the_application(client, db, bank):
    bank.app_info = {"name": "MFP", "environment": "production", "active": False,
                     "redirect_urls": ["https://elsewhere.example/cb"]}
    original = bank.__call__

    class WithApp(FakeBank):
        def __call__(self, *args, **kwargs):
            return dict(bank.app_info) if args[2] == "/application" else original(*args, **kwargs)

    sync.client.request = WithApp()
    html = client.post("/banking/credentials/check", follow_redirects=True).get_data(as_text=True)
    assert "non è attiva" in html and "non è tra quelli registrati" in html and "Production (banche vere)" in html
    bank.app_info = {"name": "MFP", "environment": "SANDBOX", "active": True,
                     "redirect_urls": ["http://localhost/banking/callback"]}
    info = open_banking.check_application("http://localhost/banking/callback")
    assert info["redirect_ok"] and not info["production"]
    messages = open_banking.describe_application(info, "http://localhost/banking/callback")
    assert messages == [("success", "Applicazione «MFP» · Sandbox (banche di prova) · attiva.")]
    bank.app_info = {}
    info = open_banking.check_application("x")
    assert info["redirect_ok"] is None and "stato non indicato" in open_banking.describe_application(info, "x")[0][1]


def test_check_reports_refused_credentials(client, db, bank, pem):
    bank.fail["/application"] = eb.ProviderError("Application does not exist", 403)
    response = client.post("/banking/credentials", data={"app_id": "app-9", "key_text": pem}, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert "Credenziali di Enable Banking salvate" in html and "Application does not exist" in html
    assert "Verifica applicazione" in html


# ── The https way back (Production) ─────────────────────────────────────────

RELAY = "https://nome.github.io/mfp-ritorno/"


def test_the_https_way_back_is_saved_and_used(client, db, bank, pem):
    response = client.post("/banking/credentials", data={"app_id": "app-123", "redirect_url": "http://x/cb"},
                           follow_redirects=True)
    assert "deve iniziare con https://" in response.get_data(as_text=True)
    client.post("/banking/credentials", data={"app_id": "app-123", "redirect_url": RELAY})  # the key is kept
    assert credentials.current() == eb.Credentials("app-123", pem, RELAY)
    page = client.get("/banking/manage").get_data(as_text=True)
    assert RELAY in page and "Va bene per la Sandbox" not in page
    _connect(client, bank)
    auth = next(c for c in bank.calls if c[1] == "/auth")[3]
    assert auth["redirect_url"] == RELAY
    state = auth["state"]
    token, origin = state.rsplit(".", 1)
    assert len(token) > 20 and base64.urlsafe_b64decode(origin + "=" * (-len(origin) % 4)) == b"localhost"
    with pytest.raises(ValueError):
        credentials.save("another-app", "")  # no key for another application
    with pytest.raises(ValueError):
        credentials.clean_redirect("ftp://x")
    assert credentials.clean_redirect("  ") is None


def test_a_pasted_address_completes_the_link(client, db, bank):
    account = _account()
    client.post(f"/banking/accounts/{account.id}/connect", data={"aspsp": "Fineco"})
    state = _state()
    pasted = f"https://nome.github.io/mfp-ritorno/?state={state}&code=c-7"
    response = client.post("/banking/callback/paste", data={"url": pasted})
    assert "/banking/callback?" in response.headers["Location"] and "code=c-7" in response.headers["Location"]
    client.get(response.headers["Location"])
    assert BankConnection.query.count() == 1
    response = client.post("/banking/callback/paste", data={"url": "https://example.com/nothing"}, follow_redirects=True)
    assert "non contiene la risposta della banca" in response.get_data(as_text=True)
    assert open_banking.pasted_return("x?state=s&error=access_denied") == {"state": "s", "error": "access_denied"}


def test_the_relay_page_only_sends_back_to_this_computer():
    from pathlib import Path

    page = (Path(__file__).resolve().parents[1] / "docs" / "psd2-ritorno" / "index.html").read_text(encoding="utf-8")
    assert "localhost|127\\.0\\.0\\.1" in page and "/banking/callback" in page and "location.replace" in page


def test_a_redirect_url_not_registered_says_which_one(client, db, bank):
    account = _account()
    bank.fail["/auth"] = eb.ProviderError("Redirect URI not allowed", 422)
    response = client.post(f"/banking/accounts/{account.id}/connect", data={"aspsp": "Fineco"}, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert "non accetta l&#39;indirizzo di ritorno http://localhost/banking/callback" in html


def test_the_bank_opens_in_the_whole_window_from_the_pop_up(client, db, bank):
    account = _account()
    page = client.get(f"/accounts/{account.id}/edit?embed=1").get_data(as_text=True)
    assert 'class="bank-connect-form" target="_blank"' in page  # a new tab: banks refuse to load inside a frame


def test_a_reversal_downloaded_by_itself_is_linked(client, db, bank):
    _connect(client, bank)
    connection = BankConnection.query.one()
    connection.auto_save = True
    link = connection.links[0]
    link.pending, link.last_booked = None, None
    db.session.commit()
    bank.movements = [tx("r1", "19.90", day="2026-11-12", text="PAGAMENTO POS LIBRERIA"),
                      tx("r2", "19.90", day="2026-11-14", indicator="CRDT", text="STORNO PAGAMENTO POS LIBRERIA")]
    results = open_banking.sync_connection(connection)
    assert results[0].saved == 2
    saved = Transaction.query.filter(Transaction.tags.any("psd2")).all()
    assert len(saved) == 2 and all(t.reversal_id for t in saved)


def test_nothing_in_the_panel_reloads_inside_the_pop_up(client, db, bank):
    account = _account()
    page = client.get(f"/accounts/{account.id}/edit?embed=1").get_data(as_text=True)
    panel = page[page.index('id="bank-link"'):]
    panel = panel[:panel.index("</div>\n</div>") if "</div>\n</div>" in panel else len(panel)]
    for tag in re.findall(r"<form [^>]*>", panel):
        assert 'target="_top"' in tag or 'target="_blank"' in tag, tag
    _connect(client, bank, account=account)
    page = client.get(f"/accounts/{account.id}/edit?embed=1").get_data(as_text=True)
    panel = page[page.index('id="bank-link"'):]
    for tag in re.findall(r"<form [^>]*>", panel):
        assert 'target="_top"' in tag or 'target="_blank"' in tag, tag



def test_the_way_back_works_in_a_browser_without_the_app(client, db, bank, app):
    """The desktop app opens the system's browser: no session of the app there, the consent completes all the same."""
    account = _account()
    client.post(f"/banking/accounts/{account.id}/connect", data={"aspsp": "Fineco"})
    state = _state()
    app.config["LOGIN_DISABLED"] = False
    other_browser = app.test_client()
    response = other_browser.get(f"/banking/callback?state={state}&code=c-1")
    html = response.get_data(as_text=True)
    assert response.status_code == 200 and "Fineco collegata" in html and "Puoi chiudere questa scheda" in html
    assert 'class="sidebar' not in html  # a page of its own, not the app
    assert BankConnection.query.count() == 1 and not sync.pending_states()
    response = other_browser.get(f"/banking/callback?state={state}&code=c-1")  # used once
    assert response.status_code == 400 and "non riconosciuto" in response.get_data(as_text=True)


def test_stale_consents_are_forgotten(app, db, bank):
    old = (sync._utcnow() - timedelta(hours=3)).isoformat()
    store.put_json(sync.PENDING, {"s1": {"at": old}, "s2": {"at": sync._utcnow().isoformat()}, "s3": "junk"})
    assert list(sync.pending_states()) == ["s2"] and sync.peek("s1") is None
    store.put(sync.PENDING, "{not json")
    assert sync.pending_states() == {}


def test_a_bank_with_no_accounts_says_why(client, db, bank):
    bank.accounts = []
    html = _connect(client, bank).get_data(as_text=True)
    assert "non ha indicato nessun conto" in html


def test_the_consent_lands_in_its_own_archive(client, db, bank, office):
    from app.models.client import Client
    from app.services import studio

    client.post("/clients/new", data={"name": "Mario Rossi", "color": "#16a34a"})  # now the open archive
    rossi = Client.query.filter_by(name="Mario Rossi").one()
    account = _account("Conto Rossi")
    client.post(f"/banking/accounts/{account.id}/connect", data={"aspsp": "Fineco"})
    state = _state()
    client.post(f"/clients/{studio.primary().id}/open")  # meanwhile another archive is opened
    client.get(f"/banking/callback?state={state}&code=c-1")
    with studio.using(studio.primary()):
        assert BankConnection.query.count() == 0  # not in the archive open meanwhile…
    with studio.using(rossi):
        assert BankConnection.query.count() == 1  # …in Rossi's, where it was started


def test_a_failed_first_download_is_said_on_the_page(client, db, bank):
    bank.fail["/accounts/acc-1/transactions"] = eb.ProviderError("Bank temporarily unavailable", 503)
    html = _connect(client, bank).get_data(as_text=True)
    assert "Fineco collegata" in html and "Bank temporarily unavailable" in html


def test_an_update_by_hand_points_to_the_waiting_movements(client, db, bank):
    _connect(client, bank)
    connection = BankConnection.query.one()
    bank.movements = [tx("w1", "8")]
    html = client.post(f"/banking/connections/{connection.id}/sync", follow_redirects=True).get_data(as_text=True)
    assert "Apri «Controlla» sui conti" in html


def test_opening_the_app_reads_the_banks_with_the_user_there(client, db, bank, app):
    from app.models.bank_link import BankAccessLog

    _connect(client, bank)
    connection = BankConnection.query.one()
    app.config.update(BANK_SYNC_ON_OPEN=True, BANK_SYNC_INLINE=True)
    reads = lambda: [c for c in bank.calls if c[1].endswith("/transactions")]  # noqa: E731
    before = len(reads())
    client.get("/dashboard")
    assert len(reads()) == before  # read just now (the consent): not again within half an hour
    connection.links[0].last_sync_at = sync._utcnow() - timedelta(hours=2)
    db.session.commit()
    with client.session_transaction() as s:
        s.pop("banks_opened_at", None)  # a new visit
    client.get("/dashboard")
    assert len(reads()) == before + 1 and reads()[-1][4]  # with the user's headers: not one of the four a day
    assert BankAccessLog.query.order_by(BankAccessLog.id.desc()).first().kind == "open"
    assert open_banking.unattended_today(connection) == 0
    connection.links[0].last_sync_at = sync._utcnow() - timedelta(hours=2)
    db.session.commit()
    client.get("/transactions/")  # the same visit, within the hour: nothing
    assert len(reads()) == before + 1
    assert "Apertura app" in client.get("/banking/manage").get_data(as_text=True)


def test_opening_reads_in_a_thread_and_skips_what_is_not_due(client, db, bank, app, monkeypatch):
    _connect(client, bank)
    connection = BankConnection.query.one()
    assert not sync.opened_due(connection)
    later = sync._utcnow() + timedelta(hours=1)
    assert sync.opened_due(connection, later)
    connection.auto_sync = False
    assert not sync.opened_due(connection, later)
    connection.auto_sync, connection.valid_until = True, sync._utcnow() - timedelta(days=1)
    assert not sync.opened_due(connection, later)
    connection.valid_until = None
    connection.links[0].last_sync_at = None
    db.session.commit()
    started = []
    monkeypatch.setattr(sync.threading, "Thread", lambda target, args, **kw: started.append((target, args)) or
                        type("T", (), {"start": lambda self: None})())
    with app.test_request_context("/"):
        open_banking.run_on_open()
        open_banking.run_on_open()  # already running for this archive
    assert len(started) == 1
    target, args = started[0]
    target(*args)
    assert sync._running == set()
    bank.fail["/accounts/acc-1/transactions"] = eb.ProviderError("boom", 500)
    connection.links[0].last_sync_at = None
    db.session.commit()
    assert sync.sync_on_open({"Psu-Ip-Address": "1"}) == 0  # kept on the connection
    monkeypatch.setattr(sync, "sync_on_open", lambda psu: 1 / 0)
    target(*args)  # a failure is only logged
    monkeypatch.setattr(sync, "configured", lambda: 1 / 0)
    with app.test_request_context("/"):
        open_banking.run_on_open()  # an archive not upgraded: nothing


def test_nothing_is_read_on_open_without_credentials(app, db):
    assert sync.sync_on_open({}) == 0


def test_opening_with_a_failing_bank_and_without_signing_in(client, db, bank, app):
    _connect(client, bank)
    link = BankAccountLink.query.one()
    link.last_sync_at = None
    db.session.commit()
    bank.fail["/accounts/acc-1/transactions"] = eb.ProviderError("Bank down", 503)
    assert sync.sync_on_open({"Psu-Ip-Address": "1"}) == 0
    assert BankConnection.query.one().last_error == "Enable Banking: Bank down"
    app.config.update(BANK_SYNC_ON_OPEN=True, BANK_SYNC_INLINE=True, LOGIN_DISABLED=False)
    calls = len(bank.calls)
    client.get("/auth/login")  # nobody signed in: nothing is read
    assert len(bank.calls) == calls


# ── The account follows the bank's balance (22 Nov 2026) ─────────────────────

def _auto_saving(client, bank):
    _fineco(None)
    _connect(client, bank)
    connection = BankConnection.query.one()
    connection.auto_save = True
    link = connection.links[0]
    link.pending, link.last_booked = None, None
    from app.extensions import db as _db
    _db.session.commit()
    return connection, link


def test_the_first_read_puts_the_missing_money_in_the_opening_balance(client, db, bank):
    from app.services import accounts as account_service
    bank.movements = [tx("e1", "100.00", text="NETFLIX")]
    connection, link = _auto_saving(client, bank)
    results = open_banking.sync_connection(connection)
    fineco = link.account
    assert results[0].aligned == Decimal("1334.56")  # the bank says 1234,56 after the 100 € paid
    assert fineco.opening_balance == Decimal("1334.56") and fineco.reconciled_on == date(2026, 11, 20)
    assert account_service.balance(fineco, date(2026, 11, 20)) == pytest.approx(1234.56)
    assert not account_service.reconciliations(fineco)  # no movement: the history starts right
    assert "saldo allineato alla banca (differenza +1334,56)" in open_banking.summary(results)
    # later the app has 50 € less than the bank (a movement edited, a fee missed): a «Riconciliazione» movement
    bank.movements = [tx("e1", "100.00", text="NETFLIX"), tx("e2", "50.00", day="2026-11-15", text="AMAZON")]
    results = open_banking.sync_connection(connection)
    assert results[0].aligned == Decimal("50.00")
    adjustment = account_service.reconciliations(fineco)[0]
    assert adjustment.type == "income" and adjustment.amount == Decimal("50.00") and adjustment.date == date(2026, 11, 20)
    assert fineco.opening_balance == Decimal("1334.56")  # unchanged
    # the same again: nothing more to align
    assert open_banking.sync_connection(connection)[0].aligned is None


def test_no_alignment_while_movements_wait_or_without_a_booked_balance(client, db, bank, monkeypatch):
    bank.movements = [tx("e1", "100.00", text="NETFLIX")]
    connection, link = _auto_saving(client, bank)
    link.pending = [{"import_ref": "x", "date": "2026-11-12"}]
    db.session.commit()
    assert open_banking.align(link) is None  # the bank's balance counts what still waits in the preview
    link.pending = None
    db.session.commit()
    real = FakeBank.__call__

    def available_only(self, creds, method, path, params=None, body=None, psu=None):
        if path.endswith("/balances"):
            return {"balances": [{"balance_type": "ITAV", "balance_amount": {"amount": "999.00", "currency": "EUR"}}]}
        return real(self, creds, method, path, params, body, psu)
    monkeypatch.setattr(FakeBank, "__call__", available_only)
    results = open_banking.sync_connection(connection)
    assert results[0].aligned is None and link.account.opening_balance in (None, 0)  # with pending: not comparable


# ── A period refused, an account refused (25 Nov 2026) ───────────────────────

def test_the_first_day_asked_to_the_bank(app):
    today = date(2026, 11, 25)
    link = BankAccountLink(uid="x")
    assert sync._since(link, today) == today - timedelta(days=sync.INITIAL_DAYS)  # never read
    link.last_sync_at = datetime(2026, 11, 22, 18, 46)  # read, but nothing booked ever came
    assert sync._since(link, today) == date(2026, 11, 15)
    link.last_booked = date(2026, 11, 20)
    assert sync._since(link, today) == date(2026, 11, 13)
    link.last_booked = date(2026, 12, 15)  # a booking dated ahead: never a period in the future
    assert sync._since(link, today) == today
    link.last_booked = date(2025, 1, 1)  # a sleeping account: no further back than the first read
    assert sync._since(link, today) == today - timedelta(days=sync.INITIAL_DAYS)


def test_a_period_refused_is_asked_again_nearer(client, db, bank, monkeypatch):
    _connect(client, bank)
    link = BankAccountLink.query.one()
    link.last_booked = link.last_sync_at = None
    db.session.commit()
    asked, refused = [], eb.ProviderError("Wrong transactions period requested", 422, "WRONG_TRANSACTIONS_PERIOD")
    fake = eb.request

    def picky(creds, method, path, params=None, body=None, psu=None):
        if path.endswith("/transactions"):
            asked.append(date.fromisoformat(params["date_from"]))
            if asked[-1] < date.today() - timedelta(days=sync.SHORTER_DAYS[-1]):
                raise refused
        return fake(creds, method, path, params, body, psu)

    monkeypatch.setattr(eb, "request", picky)
    bank.movements = [tx("w1", "4", day=date.today().isoformat())]
    results = open_banking.sync_connection(BankConnection.query.one())
    assert [date.today() - d for d in asked] == [timedelta(days=n) for n in (sync.INITIAL_DAYS, *sync.SHORTER_DAYS)]
    assert results[0].waiting == 1 and BankConnection.query.one().last_error is None
    # another error is not asked again; nor is a period refused even from the nearest day
    asked.clear()
    link = BankAccountLink.query.one()
    link.last_booked = link.last_sync_at = None
    db.session.commit()
    refused = eb.ProviderError("Wrong transactions period requested", 422, "WRONG_TRANSACTIONS_PERIOD")
    monkeypatch.setattr(sync.client, "transactions", lambda *a, **k: (asked.append(1), (_ for _ in ()).throw(refused))[1])
    with pytest.raises(open_banking.BankingError, match="Wrong transactions period"):
        open_banking.sync_connection(BankConnection.query.one())
    assert len(asked) == 1 + len(sync.SHORTER_DAYS)


def test_an_account_refused_does_not_stop_the_others(client, db, bank):
    _connect(client, bank, account=_fineco(db))
    connection = BankConnection.query.one()
    other = _account("Deposito Fineco")
    db.session.add(BankAccountLink(connection=connection, uid="acc-2", name="Deposito", account=other, active=True))
    db.session.commit()
    bank.movements = [tx("d1", "8", day=date.today().isoformat())]
    bank.fail["/accounts/acc-2/transactions"] = eb.ProviderError("boom", 500)
    response = client.post(f"/banking/connections/{connection.id}/sync", follow_redirects=True)
    html = response.get_data(as_text=True)
    assert "Fineco aggiornata" in html and "Deposito Fineco — Enable Banking: boom" in html
    first = BankAccountLink.query.filter_by(uid="acc-1").one()
    assert first.pending and BankConnection.query.one().last_error == "Deposito Fineco — Enable Banking: boom"
    assert sync._link_name(BankAccountLink(uid="u", iban="IT001234")) == "•••• 1234"
    assert sync._link_name(BankAccountLink(uid="u")) == "u"
