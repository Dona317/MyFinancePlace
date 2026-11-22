"""
The Enable Banking API (https://enablebanking.com/docs/api/reference): the PSD2 aggregator MyFinancePlace reads the
banks through. Every call is signed with a short JWT (RS256) made from the application's id and private key; no
library beyond `cryptography`, HTTP through urllib like the other online sources of the app.

The calls used:
  GET  /aspsps?country=IT            the banks of a country
  POST /auth                         start a consent → the bank's page the user is sent to
  POST /sessions {code}              the consent given → session id + the accounts it covers
  GET  /sessions/{id}                is the consent still valid?
  DELETE /sessions/{id}              withdraw it
  GET  /accounts/{uid}/balances      the balances of an account
  GET  /accounts/{uid}/transactions  its movements, page after page (continuation_key)
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from flask import current_app

API_URL = "https://api.enablebanking.com"
TIMEOUT = 30          # seconds
TOKEN_SECONDS = 3600  # the JWT lives one hour (the API accepts up to 24)
MAX_PAGES = 50        # continuation pages read for one account in one download


class ProviderError(Exception):
    """The aggregator refused a call or could not be reached; `status` is the HTTP status (0: no answer)."""

    def __init__(self, message: str, status: int = 0, code: str | None = None):
        super().__init__(message)
        self.status, self.code = status, code

    @property
    def consent_gone(self) -> bool:
        """The consent expired or was withdrawn at the bank: it must be given again."""
        text = f"{self.code or ''} {self}".upper()
        return any(word in text for word in ("EXPIRED", "REVOKED", "CLOSED_SESSION", "INVALID_SESSION"))


@dataclass(frozen=True)
class Credentials:
    app_id: str
    private_key_pem: str
    redirect_url: str | None = None  # the https page the bank sends back to (a relay to this app), when set


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def load_private_key(pem: str):
    """The RSA private key of the application; ValueError when the text is not one."""
    try:
        key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    except (ValueError, TypeError) as exc:
        raise ValueError("not a private key") from exc
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("not an RSA key")
    return key


def token(credentials: Credentials, now: float | None = None) -> str:
    """The signed JWT of a call (header kid = application id)."""
    issued = int(now if now is not None else time.time())
    header = {"typ": "JWT", "alg": "RS256", "kid": credentials.app_id}
    payload = {"iss": "enablebanking.com", "aud": "api.enablebanking.com", "iat": issued, "exp": issued + TOKEN_SECONDS}
    signing_input = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(payload).encode())}"
    signature = load_private_key(credentials.private_key_pem).sign(signing_input.encode("ascii"), padding.PKCS1v15(),
                                                                   hashes.SHA256())
    return f"{signing_input}.{_b64(signature)}"


def _base_url() -> str:
    return (current_app.config.get("ENABLE_BANKING_API_URL") or API_URL).rstrip("/")


def _error_message(raw: bytes, fallback: str) -> tuple[str, str | None]:
    try:
        data = json.loads(raw.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return fallback, None
    if not isinstance(data, dict):
        return fallback, None
    message = data.get("message") or data.get("detail") or data.get("error") or fallback
    return str(message), data.get("code") or data.get("error")


def request(credentials: Credentials, method: str, path: str, params: dict | None = None,
            body: dict | None = None, psu: dict | None = None) -> dict:
    """One call to the API, its JSON answer; ProviderError on any failure. `psu`: the headers that tell the bank the
    user is there (Psu-Ip-Address, Psu-User-Agent) — a download the user asked for does not count against the four
    a day PSD2 allows without them."""
    url = _base_url() + path
    query = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Authorization": f"Bearer {token(credentials)}", "Accept": "application/json",
               "User-Agent": "MyFinancePlace"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    headers.update({k: v for k, v in (psu or {}).items() if v})
    call = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(call, timeout=TIMEOUT) as response:  # noqa: S310 - fixed https endpoint
            raw = response.read()
    except urllib.error.HTTPError as exc:
        message, code = _error_message(exc.read() or b"", f"HTTP {exc.code}")
        raise ProviderError(message, exc.code, code) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(str(getattr(exc, "reason", exc))) from exc
    if not raw:
        return {}
    try:
        answer = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProviderError("invalid answer") from exc
    return answer if isinstance(answer, dict) else {"items": answer}


# ── The calls ────────────────────────────────────────────────────────────────

def application(credentials: Credentials) -> dict:
    """The registered application (name, redirect URLs, whether it is active): checks the credentials."""
    return request(credentials, "GET", "/application")


def aspsps(credentials: Credentials, country: str) -> list[dict]:
    return list(request(credentials, "GET", "/aspsps", {"country": country}).get("aspsps") or [])


def start_authorization(credentials: Credentials, aspsp: str, country: str, redirect_url: str, state: str,
                        valid_until: datetime, psu_type: str = "personal") -> dict:
    """{"url": the bank's page, "authorization_id": …}."""
    body = {"access": {"valid_until": valid_until.strftime("%Y-%m-%dT%H:%M:%S.000000+00:00")},
            "aspsp": {"name": aspsp, "country": country}, "state": state, "redirect_url": redirect_url,
            "psu_type": psu_type}
    return request(credentials, "POST", "/auth", body=body)


def create_session(credentials: Credentials, code: str) -> dict:
    return request(credentials, "POST", "/sessions", body={"code": code})


def get_session(credentials: Credentials, session_id: str) -> dict:
    return request(credentials, "GET", f"/sessions/{urllib.parse.quote(session_id, safe='')}")


def delete_session(credentials: Credentials, session_id: str) -> None:
    request(credentials, "DELETE", f"/sessions/{urllib.parse.quote(session_id, safe='')}")


def balances(credentials: Credentials, uid: str, psu: dict | None = None) -> list[dict]:
    return list(request(credentials, "GET", f"/accounts/{urllib.parse.quote(uid, safe='')}/balances", psu=psu)
                .get("balances") or [])


def transactions(credentials: Credentials, uid: str, date_from: date, date_to: date | None = None,
                 psu: dict | None = None) -> list[dict]:
    """Every movement from `date_from`, following the continuation keys (MAX_PAGES at most)."""
    path = f"/accounts/{urllib.parse.quote(uid, safe='')}/transactions"
    params = {"date_from": date_from.isoformat(), "date_to": date_to.isoformat() if date_to else None}
    found: list[dict] = []
    for _ in range(MAX_PAGES):
        page = request(credentials, "GET", path, params, psu=psu)
        found.extend(page.get("transactions") or [])
        key = page.get("continuation_key")
        if not key:
            break
        params = {**params, "continuation_key": key}
    return found
