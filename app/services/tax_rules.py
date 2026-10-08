"""
The Italian tax parameters the Fisco pages use (F15), by tax year: what the 730 lets one deduct, the rates on
capital gains, the stamp duty and IVAFE. Figures from the Agenzia delle Entrate instructions and the budget laws
(L. 207/2024, L. 199/2025); a year without its own figures uses the latest known year. Estimates for planning:
the return itself is the CAF's or the accountant's.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from app.services.i18n import N_

D = Decimal
FIRST_YEAR = 2024
DETRAZIONE, DEDUZIONE = "detrazione", "deduzione"


@dataclass(frozen=True)
class Item:
    """A line of the 730's quadro E: what kind of expense, where it goes and how much of it counts."""
    code: str               # our key
    label: str              # shown name (translated at display)
    form_line: str          # quadro E line and code
    kind: str               # DETRAZIONE (a percent of it off the tax) or DEDUZIONE (off the taxable income)
    rate: Decimal           # percent of the expense taken off the tax (detrazioni)
    threshold: Decimal      # franchigia: the first euros do not count
    ceiling: Decimal | None  # massimale: what counts at most (None: no limit)
    per_person: bool = False  # the ceiling is per student / child
    note: str = ""


_ITEMS_2024 = (
    Item("sanitarie", N_("Spese sanitarie"), "E1", DETRAZIONE, D(19), D("129.11"), None,
         note=N_("Farmaci e dispositivi anche in contanti; visite e altro solo con pagamento tracciabile.")),
    Item("veterinarie", N_("Spese veterinarie"), "E8-E10 cod. 29", DETRAZIONE, D(19), D("129.11"), D(550)),
    Item("istruzione", N_("Istruzione (infanzia, primaria, secondaria)"), "E8-E10 cod. 12", DETRAZIONE, D(19), D(0),
         D(800), per_person=True),
    Item("universita", N_("Università"), "E8-E10 cod. 13", DETRAZIONE, D(19), D(0), None,
         note=N_("Per le università non statali vale il limite ministeriale per area e corso.")),
    Item("mutuo", N_("Interessi del mutuo prima casa"), "E7 cod. 7", DETRAZIONE, D(19), D(0), D(4000),
         note=N_("Solo gli interessi passivi e gli oneri accessori, non la quota capitale della rata.")),
    Item("assicurazioni", N_("Assicurazioni vita e infortuni"), "E8-E10 cod. 36", DETRAZIONE, D(19), D(0), D(530)),
    Item("sport", N_("Attività sportive dei ragazzi (5-18 anni)"), "E8-E10 cod. 30", DETRAZIONE, D(19), D(0), D(210),
         per_person=True),
    Item("trasporto", N_("Abbonamenti al trasporto pubblico"), "E8-E10 cod. 40", DETRAZIONE, D(19), D(0), D(250)),
    Item("asilo", N_("Asilo nido"), "E8-E10 cod. 33", DETRAZIONE, D(19), D(0), D(632), per_person=True),
    Item("affitto_studenti", N_("Affitto studenti fuori sede"), "E8-E10 cod. 18", DETRAZIONE, D(19), D(0), D(2633)),
    Item("funebri", N_("Spese funebri"), "E8-E10 cod. 14", DETRAZIONE, D(19), D(0), D(1550)),
    Item("donazioni", N_("Erogazioni liberali a enti del terzo settore"), "E8-E10 cod. 71", DETRAZIONE, D(30), D(0),
         D(30000)),
    Item("previdenza", N_("Previdenza complementare"), "E27", DEDUZIONE, D(0), D(0), D("5164.57")),
    Item("colf", N_("Contributi per colf e badanti"), "E23", DEDUZIONE, D(0), D(0), D("1549.37")),
)
_ISTRUZIONE_FROM_2025 = D(1000)  # L. 207/2024: 1.000 euro per student from the 2025 tax year


def items(year: int) -> tuple[Item, ...]:
    if year < 2025:
        return _ITEMS_2024
    return tuple(replace(item, ceiling=_ISTRUZIONE_FROM_2025) if item.code == "istruzione" else item
                 for item in _ITEMS_2024)


def item(year: int, code: str) -> Item | None:
    return next((i for i in items(year) if i.code == code), None)


# The IRPEF brackets, to show what a deduction is worth at one's marginal rate
IRPEF_RATES = {2024: (D(23), D(35), D(43)), 2025: (D(23), D(35), D(43)), 2026: (D(23), D(33), D(43))}


def irpef_rates(year: int) -> tuple[Decimal, ...]:
    return IRPEF_RATES.get(year) or IRPEF_RATES[max(IRPEF_RATES)]


# ── Capital gains ──────────────────────────────────────────────────────────────

REGIMES = {"amministrato": N_("Amministrato: il broker calcola e versa le imposte"),
           "dichiarativo": N_("Dichiarativo: plusvalenze in dichiarazione (quadro RT)")}

MARKET_CLASSES = ("Azione", "ETF", "Fondo", "Obbligazione", "Criptovaluta")
CRYPTO = "Criptovaluta"
FUND_CLASSES = ("ETF", "Fondo")  # their gains are redditi di capitale: not offset by past losses
GOVERNMENT_BOND_RATE = D("12.5")
GOVERNMENT_BOND_WEIGHT = D("0.4808")  # a loss offsets gains taxed at 12,5% for 48,08% of its amount
LOSS_YEARS = 4  # a loss can be used until 31 December of the fourth following year


def gain_rate(asset_class: str, year: int, own_rate: Decimal | None = None) -> Decimal:
    """The rate on a capital gain realized in `year`: the holding's own (12,5 for government bonds) or its class's."""
    if own_rate is not None:
        return D(own_rate)
    if asset_class == CRYPTO:
        return D(33) if year >= 2026 else D(26)  # L. 207/2024: 33% on crypto gains from 2026
    return D(26)


# ── Stamp duty and IVAFE ───────────────────────────────────────────────────────

ACCOUNT_DUTY = D("34.20")       # current accounts and savings books of individuals, per year
ACCOUNT_DUTY_THRESHOLD = D(5000)  # not due when the average balance is not above this
SECURITIES_RATE = D("0.2")      # percent of the value of securities and deposit accounts (bollo, IVAFE, crypto)
