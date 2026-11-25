"""
Options (25 Nov 2026, F120): a holding of the instrument «Derivato» with its option terms filled in — call or put,
strike, expiry, underlying, style, settlement — kept in the portfolio like the other holdings.

    quantity   the contracts: positive when bought, negative when sold (written: the premium was cashed in)
    price      per unit of the underlying, as quoted (2,35 $ for an option on Apple shares)
    multiplier the units of the underlying a contract is on: 100 for most share options (US, IDEM), 2,5 € a point
               for the IDEM options on the FTSE MIB (MIBO), 10 for the Eurex ones on the Euro Stoxx 50
    value      quantity × multiplier × price: below zero for a sold option (what it would cost to buy it back)

US options are found on Yahoo by their OCC symbol (AAPL261218C00200000: underlying, expiry, C/P, strike × 1000 in
eight digits), built here from the terms; the IDEM and Eurex ones have no free source: price by hand or from the
broker's file.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from app.services import display
from app.services.i18n import N_
from app.services.i18n import gettext as _

KINDS = {"call": N_("Call"), "put": N_("Put")}
STYLES = {"american": N_("Americana (esercitabile ogni giorno)"), "european": N_("Europea (solo a scadenza)")}
SETTLEMENTS = {"physical": N_("Consegna del sottostante"), "cash": N_("Liquidazione in contanti")}
# the usual multipliers, offered in the form: share options, IDEM FTSE MIB (2,5 € a point), Eurex Euro Stoxx 50
MULTIPLIERS = (100, Decimal("2.5"), 10, 1)
OCC = re.compile(r"^([A-Z]{1,6})(\d{6})([CP])(\d{8})$")


def is_us(underlying: str | None) -> bool:
    """A US listing: a Yahoo ticker without an exchange suffix (AAPL, SPY; not ENEL.MI or ^STOXX50E)."""
    text = (underlying or "").strip().upper()
    return bool(text) and "." not in text and not text.startswith("^") and text.replace("-", "").isalpha()


def occ_symbol(underlying: str, expiry: date, kind: str, strike: Decimal) -> str:
    """The OCC symbol of a US option, as Yahoo quotes it: AAPL + 261218 + C + 00200000."""
    root = underlying.strip().upper().replace("-", "")
    return f"{root}{expiry:%y%m%d}{'C' if kind == 'call' else 'P'}{int(round(Decimal(strike) * 1000)):08d}"


def parse_occ(symbol: str) -> dict | None:
    """The terms in an OCC symbol (the ticker of a US option), None when it is not one."""
    found = OCC.match((symbol or "").strip().upper())
    if not found:
        return None
    root, ymd, cp, strike = found.groups()
    try:
        expiry = date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:]))
    except ValueError:
        return None
    return {"underlying": root, "option_expiry": expiry, "option_kind": "call" if cp == "C" else "put",
            "strike": Decimal(strike) / 1000}


def label(holding) -> str:
    """«AAPL call 200 · 18/12/2026»: what the option is, in a few words."""
    parts = [holding.underlying or holding.name, str(KINDS.get(holding.option_kind, holding.option_kind or "")).lower()]
    if holding.strike is not None:
        parts.append(display.plain(holding.strike))
    text = " ".join(p for p in parts if p)
    return f"{text} · {display.day(holding.option_expiry)}" if holding.option_expiry else text


def days_left(holding, today: date | None = None) -> int | None:
    if not holding.option_expiry:
        return None
    return (holding.option_expiry - (today or date.today())).days


def intrinsic(holding, underlying_price: float) -> float:
    """What it is worth if exercised now, per unit of the underlying (never below zero)."""
    strike = float(holding.strike or 0)
    gap = underlying_price - strike if holding.option_kind == "call" else strike - underlying_price
    return max(gap, 0.0)


def moneyness(holding, underlying_price: float) -> str:
    """"itm" (in the money: worth exercising), "atm" (within 1 % of the strike) or "otm"."""
    strike = float(holding.strike or 0)
    if strike and abs(underlying_price - strike) / strike <= 0.01:
        return "atm"
    return "itm" if intrinsic(holding, underlying_price) > 0 else "otm"


def validate(holding) -> None:
    """The terms that go together: a kind needs a strike and an expiry; the strike is above zero."""
    if not holding.option_kind:
        if holding.strike is not None or holding.option_expiry:
            raise ValueError(_("Opzione: scegli se è una call o una put."))
        return
    if holding.option_kind not in KINDS:
        raise ValueError(_("Opzione: il tipo è call o put."))
    if holding.strike is None or holding.strike <= 0:
        raise ValueError(_("Opzione: scrivi lo strike, il prezzo d'esercizio, maggiore di zero."))
    if not holding.option_expiry:
        raise ValueError(_("Opzione: scrivi la data di scadenza."))
