"""
Asset classes (F70): what a holding is exposed to — equities, bonds, gold… — kept apart from the instrument it is
held through (`Holding.asset_class`: ETF, share, fund, bond…). An ETF on the MSCI World is an ETF (instrument) and
equities (asset class); a gold ETC is an ETF and gold.

The user can set the class on the holding; until then it is estimated from the instrument and the name, so the
portfolio's charts by asset class work from the first day.
"""
from __future__ import annotations

import re

from app.services.i18n import N_

EQUITY = N_("Azionario")
BONDS = N_("Obbligazionario")
CASH = N_("Monetario e liquidità")
GOLD = N_("Oro e metalli preziosi")
COMMODITIES = N_("Materie prime")
REAL_ESTATE = N_("Immobiliare")
CRYPTO = N_("Criptovalute")
BALANCED = N_("Bilanciato")
OTHER = N_("Altro")
CLASSES = [EQUITY, BONDS, CASH, GOLD, COMMODITIES, REAL_ESTATE, CRYPTO, BALANCED, OTHER]

# the instrument decides when it says it all
BY_INSTRUMENT = {"Azione": EQUITY, "Obbligazione": BONDS, "Criptovaluta": CRYPTO, "Conto Risparmio": CASH,
                 "Immobile": REAL_ESTATE, "Fondo Pensione": BALANCED, "Veicolo": OTHER, "Derivato": OTHER,
                 "Altro": OTHER}
# otherwise the words in the name or the ticker (an ETF, a fund, valuables), first match wins
BY_WORDS = [
    (GOLD, r"\bgold\b|\boro\b|xau|physical (silver|platinum|precious)|precious metal|metalli preziosi|argento|"
           r"silver|platinum|platino|\bsgld\b|\bphau\b|\b4gld\b"),
    (COMMODITIES, r"commodit|materie prime|\bbcom\b"),
    (CASH, r"money market|monetari|overnight|€str|\bestr\b|ester|liquidit|\bcash\b|ultrashort|ultra short"),
    (BONDS, r"\bbond|aggregate|treasur|\bgovt\b|government|govern|obblig|\bbtp|corporate|\bcorp\b|high yield|"
            r"inflation|\bbund\b|\btips\b|fixed income|\bagg\b|\baggh\b|\bt-bill"),
    (REAL_ESTATE, r"\breit|real estate|immobil|property"),
    (BALANCED, r"balanced|bilanciat|multi.?asset|lifestrategy|allocation|60/40|80/20|portfolio"),
]


def estimate(instrument: str | None, name: str | None = None, ticker: str | None = None) -> str:
    """The asset class a holding most likely belongs to, from its instrument and its name."""
    text = f"{name or ''} {ticker or ''}".lower()
    if instrument in ("ETF", "Fondo", "Oggetti di valore", "Derivato", "Altro", None, ""):
        for asset_class, pattern in BY_WORDS:
            if re.search(pattern, text):
                return asset_class
    if instrument in BY_INSTRUMENT:
        return BY_INSTRUMENT[instrument]
    if instrument == "Oggetti di valore":
        return OTHER
    return EQUITY  # an ETF or a fund that says nothing else: most of them are equity funds


def of(holding) -> str:
    """The holding's asset class: the one set by the user, or the estimate."""
    chosen = getattr(holding, "allocation_class", None)
    return chosen if chosen in CLASSES else estimate(holding.asset_class, holding.name, holding.ticker)


def is_estimated(holding) -> bool:
    return getattr(holding, "allocation_class", None) not in CLASSES
