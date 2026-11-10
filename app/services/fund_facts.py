"""
A fund's characteristics (ETF, mutual or insurance fund): issuer, domicile (sede), TER, accumulating or distributing,
replication, index, launch date, currency hedging — all typed or corrected by hand on the holding's form.

The domicile, when not set, is the country of the ISIN (its first two letters: IE00B4L5Y983 → Ireland), which for a
fund is where it is domiciled. Country names come from Babel in the interface's language.
"""
from __future__ import annotations

import re

from babel import Locale
from flask_babel import get_locale

from app.services.i18n import N_

DISTRIBUTION = {"acc": N_("Accumulazione"), "dist": N_("Distribuzione")}
REPLICATION = {"full": N_("Fisica completa"), "sampling": N_("Fisica a campione"), "synthetic": N_("Sintetica (swap)"),
               "active": N_("Gestione attiva")}
UNKNOWN = N_("Non indicata")
NOT_COUNTRIES = {"XS": N_("Internazionale (Euroclear/Clearstream)"), "EU": N_("Unione Europea")}


def domicile_code(holding) -> str | None:
    """The domicile set on the holding, or the country of its ISIN."""
    code = (getattr(holding, "domicile", None) or "").strip().upper()
    if re.fullmatch(r"[A-Z]{2}", code):
        return code
    isin = (getattr(holding, "isin", None) or "").strip().upper()
    return isin[:2] if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", isin) else None


def country_name(code: str | None) -> str:
    if not code:
        return UNKNOWN
    if code in NOT_COUNTRIES:
        return NOT_COUNTRIES[code]
    try:
        locale = Locale.parse(str(get_locale() or "it"))
    except (ValueError, TypeError, RuntimeError):
        locale = Locale.parse("it")
    return locale.territories.get(code, code)


def domicile_name(holding) -> str:
    return country_name(domicile_code(holding))


def by_domicile(holdings) -> list[tuple[str, float]]:
    """The value of the holdings by domicile (sede), largest first."""
    totals: dict[str, float] = {}
    for h in holdings:
        name = domicile_name(h)
        totals[name] = totals.get(name, 0.0) + h.value
    return sorted(totals.items(), key=lambda item: item[1], reverse=True)
