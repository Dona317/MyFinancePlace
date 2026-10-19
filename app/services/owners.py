"""
Who owns the accounts: the holders' names and the full IBAN of each account (Impostazioni → Titolari e IBAN).

A bank transfer naming one of the holders, or the IBAN of one of the accounts, is money moved between own accounts:
the import reads it as a giroconto even with only one of the two statements, and with the IBAN it also knows the
other account.
"""
from __future__ import annotations

import re

from flask_babel import gettext as _

from app.models.account import Account
from app.services import settings_store
from app.services.parsing import normalize

HOLDERS_KEY = "profile.holders"
MAX_HOLDERS = 10
_IBAN = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")


def holders() -> list[str]:
    return settings_store.get_json(HOLDERS_KEY, [], expect=list)


def set_holders(names) -> list[str]:
    """Save the holders' names (one per entry, first and last name at least)."""
    clean, seen = [], set()
    for name in names:
        name = " ".join((name or "").split())[:80]
        if not name or normalize(name) in seen:
            continue
        if len(normalize(name).split()) < 2:
            raise ValueError(_("«%(name)s»: scrivi nome e cognome (una sola parola riconoscerebbe troppi movimenti).",
                               name=name))
        clean.append(name)
        seen.add(normalize(name))
    if len(clean) > MAX_HOLDERS:
        raise ValueError(_("Al massimo %(count)s titolari.", count=MAX_HOLDERS))
    settings_store.set_json(HOLDERS_KEY, clean)
    return clean


def clean_iban(text: str | None) -> str | None:
    """The IBAN without spaces, in capitals; ValueError when it is not a valid IBAN (check digits included)."""
    iban = re.sub(r"[\s-]", "", text or "").upper()
    if not iban:
        return None
    if not _IBAN.match(iban):
        raise ValueError(_("«%(iban)s» non è un IBAN valido.", iban=text.strip()))
    digits = "".join(str(int(c, 36)) for c in iban[4:] + iban[:4])
    if int(digits) % 97 != 1:
        raise ValueError(_("«%(iban)s» non è un IBAN valido: controlla le cifre.", iban=text.strip()))
    return iban


def set_iban(account: Account, text: str | None) -> None:
    """The account's IBAN (also its last digits, when those were not given); never the IBAN of another account."""
    iban = clean_iban(text)
    if iban and Account.query.filter(Account.iban == iban, Account.id != account.id).first():
        raise ValueError(_("L'IBAN %(iban)s è già di un altro conto.", iban=iban))
    account.iban = iban
    if iban and not account.iban_tail:
        account.iban_tail = iban[-4:]


class Recognizer:
    """Reads, for a whole statement, whether a movement names a holder or the IBAN of one of the accounts."""

    def __init__(self):
        self.ibans = {a.iban: a.id for a in Account.query.filter(Account.iban.isnot(None))}
        self.names = [normalize(name).split() for name in holders()]

    def account_named(self, *texts: str | None) -> int | None:
        """The account whose IBAN appears in the text."""
        compact = re.sub(r"\s", "", " ".join(t for t in texts if t)).upper()
        return next((account_id for iban, account_id in self.ibans.items() if iban in compact), None)

    def names_holder(self, *texts: str | None) -> bool:
        words = set(normalize(" ".join(t for t in texts if t)).split())
        return any(all(part in words for part in name) for name in self.names)
