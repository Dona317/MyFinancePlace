"""
Model portfolios (F19d): how far the investments are from the active template, and what to buy or sell to get back.

- Each investment holding falls in one slot: the slot it was placed in by hand, else the slot with its ISIN, else the
  one with its ticker, else the first one of its asset class. Holdings in no slot are «outside the model» (target 0).
- Rebalancing «with new money only» buys with the amount to invest, filling the slots furthest below their target
  first; «full» also sells what is above it.
- Ready models are examples to copy and change (ETFs listed in Milan), not advice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal

from flask_babel import gettext as _

from app.extensions import db
from app.models.portfolio_model import PortfolioTemplate, SlotHolding, TemplateSlot
from app.models.wealth import Holding
from app.services import money
from app.services.i18n import N_
from app.services.wealth import ASSET_CLASSES

HUNDRED = Decimal(100)
UNITS = Decimal("0.0001")

# Example instruments (UCITS ETFs listed on Borsa Italiana)
_WORLD = ("IE00BK5BQT80", "VWCE.MI")      # Vanguard FTSE All-World Acc
_AGG = ("IE00BDBRDM35", "AGGH.MI")        # iShares Core Global Aggregate Bond EUR Hedged
_LONG = ("IE00B1FZS913", "IBGL.MI")       # iShares Euro Government Bond 15-30yr
_MID = ("IE00B1FZS806", "IBGM.MI")        # iShares Euro Government Bond 7-10yr
_GOLD = ("IE00B579F325", "SGLD.MI")       # Invesco Physical Gold
_CASH = ("LU0290358497", "XEON.MI")       # Xtrackers II EUR Overnight Rate Swap
_COMMOD = ("IE00BDFL4P12", "ICOM.MI")     # iShares Diversified Commodity Swap
_DEVELOPED = ("IE00B4L5Y983", "SWDA.MI")  # iShares Core MSCI World
_EMERGING = ("IE00BKM4GZ66", "EIMI.MI")   # iShares Core MSCI EM IMI

STOCKS, BONDS = N_("Azioni globali"), N_("Obbligazioni globali")
READY = {
    "all-equity": (N_("Tutto azionario globale"), N_("Un solo ETF su tutte le borse del mondo: massima crescita attesa, ma il valore può anche dimezzarsi."),
                   [(STOCKS, 100, _WORLD)]),
    "80-20": (N_("80/20"), N_("Molto azionario, con un cuscinetto di obbligazioni."),
              [(STOCKS, 80, _WORLD), (BONDS, 20, _AGG)]),
    "60-40": (N_("60/40"), N_("Il bilanciato classico: azioni per crescere, obbligazioni per attutire i cali."),
              [(STOCKS, 60, _WORLD), (BONDS, 40, _AGG)]),
    "30-70": (N_("30/70 conservativo"), N_("Prudente: soprattutto obbligazioni, una parte di azioni."),
              [(STOCKS, 30, _WORLD), (BONDS, 70, _AGG)]),
    "permanent": (N_("Permanent Portfolio"), N_("Di Harry Browne: quattro parti uguali che reagiscono in modo diverso a crescita, inflazione, recessione e deflazione."),
                  [(N_("Azionario"), 25, _WORLD), (N_("Obbligazioni a lungo termine"), 25, _LONG), (N_("Oro"), 25, _GOLD),
                   (N_("Liquidità"), 25, _CASH)]),
    "all-weather": (N_("All Weather"), N_("Ispirato a Ray Dalio: tante obbligazioni, oro e materie prime per ogni fase dell'economia."),
                    [(N_("Azionario"), 30, _WORLD), (N_("Obbligazioni a lungo termine"), 40, _LONG),
                     (N_("Obbligazioni a medio termine"), 15, _MID), (N_("Oro"), Decimal("7.5"), _GOLD),
                     (N_("Materie prime"), Decimal("7.5"), _COMMOD)]),
    "three-fund": (N_("Three-fund portfolio"), N_("Tre fondi indicizzati: paesi sviluppati, emergenti e obbligazioni."),
                   [(N_("Azioni paesi sviluppati"), 50, _DEVELOPED), (N_("Azioni paesi emergenti"), 10, _EMERGING),
                    (BONDS, 40, _AGG)]),
}


class TemplateError(ValueError):
    """The template cannot be saved as it is; the message is shown to the user."""


def investment_classes() -> list[str]:
    return [name for name, (_line, investing) in ASSET_CLASSES.items() if investing]


def active() -> PortfolioTemplate | None:
    return PortfolioTemplate.query.filter_by(active=True).first()


def activate(template: PortfolioTemplate) -> None:
    PortfolioTemplate.query.filter(PortfolioTemplate.id != template.id).update({"active": False})
    template.active = True


def copy_ready(key: str) -> PortfolioTemplate:
    name, description, slots = READY[key]
    template = PortfolioTemplate(name=_(name), description=_(description), band=5,
                                 active=PortfolioTemplate.query.count() == 0)
    for position, (label, target, (isin, ticker)) in enumerate(slots):
        template.slots.append(TemplateSlot(position=position, label=_(label), target=Decimal(target), isin=isin,
                                           ticker=ticker))
    db.session.add(template)
    return template


@dataclass
class SlotInput:
    label: str
    target: Decimal
    asset_class: str | None = None
    isin: str | None = None
    ticker: str | None = None
    holding_ids: list[int] = field(default_factory=list)


def save(template: PortfolioTemplate, name: str, description: str | None, band: Decimal | None,
         slots: list[SlotInput]) -> None:
    """Replace the template's slots; the targets must add up to 100 %."""
    if not name.strip():
        raise TemplateError(_("Dai un nome al portafoglio modello."))
    if not slots:
        raise TemplateError(_("Aggiungi almeno una parte al modello."))
    if any(s.target <= 0 or s.target > HUNDRED for s in slots):
        raise TemplateError(_("Ogni parte deve avere un obiettivo tra 0 e 100 %."))
    total = sum((s.target for s in slots), Decimal(0))
    if abs(total - HUNDRED) > Decimal("0.01"):
        raise TemplateError(_("Gli obiettivi sommano %(total)s %%: devono fare 100 %%.", total=f"{total:f}".replace(".", ",")))
    if band is not None and not Decimal(0) <= band <= Decimal(50):
        raise TemplateError(_("La tolleranza va da 0 a 50 punti."))
    template.name, template.description = name.strip(), (description or "").strip() or None
    template.band = band if band is not None else Decimal(5)
    template.slots.clear()
    db.session.flush()
    for position, s in enumerate(slots):
        slot = TemplateSlot(position=position, label=s.label.strip(), target=s.target, asset_class=s.asset_class or None,
                            isin=(s.isin or "").strip().upper() or None, ticker=(s.ticker or "").strip().upper() or None)
        slot.links = [SlotHolding(holding_id=h) for h in dict.fromkeys(s.holding_ids)]
        template.slots.append(slot)


# ── Where the portfolio stands ─────────────────────────────────────────────────

def _base(ticker: str | None) -> str:
    return (ticker or "").upper().split(".")[0]


def assign(template: PortfolioTemplate, holdings: list[Holding]) -> tuple[dict[int, list[Holding]], list[Holding]]:
    """{slot position: its holdings} and the holdings in no slot."""
    placed: dict[int, list[Holding]] = {index: [] for index in range(len(template.slots))}
    outside = []
    tests = (lambda s, h: h.id in s.holding_ids,
             lambda s, h: bool(s.isin) and s.isin == (h.isin or "").upper(),
             lambda s, h: bool(s.ticker) and _base(s.ticker) == _base(h.ticker),
             lambda s, h: bool(s.asset_class) and s.asset_class == h.asset_class)
    for holding in holdings:
        index = next((i for test in tests for i, s in enumerate(template.slots) if test(s, holding)), None)
        (outside if index is None else placed[index]).append(holding)
    return placed, outside


def investments() -> list[Holding]:
    return Holding.query.filter(Holding.asset_class.in_(investment_classes())).order_by(Holding.name).all()


@dataclass
class Line:
    label: str
    target: Decimal                 # %
    value: Decimal                  # €
    holdings: list[Holding]
    suggestion: str | None = None   # ticker or ISIN to buy when the slot holds nothing
    weight: Decimal = Decimal(0)    # % of the portfolio now
    move: Decimal = Decimal(0)      # € to buy (+) or sell (−)
    units: Decimal | None = None    # the move in units of the slot's main holding
    via: Holding | None = None      # the holding the move is made with
    outside: bool = False

    @property
    def drift(self) -> Decimal:
        return self.weight - self.target


@dataclass
class Plan:
    template: PortfolioTemplate
    lines: list[Line]
    total: Decimal                  # value of the investments now
    amount: Decimal                 # new money to invest
    mode: str                       # "new" | "full"

    @property
    def out_of_band(self) -> list[Line]:
        return [line for line in self.lines if abs(line.drift) > self.template.band]

    @property
    def leftover(self) -> Decimal:
        return self.amount - sum((line.move for line in self.lines), Decimal(0))


def _value(holdings: list[Holding]) -> Decimal:
    return money.cents(sum((Decimal(str(h.value)) for h in holdings), Decimal(0)))


def standing(template: PortfolioTemplate, holdings: list[Holding] | None = None) -> tuple[list[Line], Decimal]:
    """The lines of the template with what each holds now, and the total."""
    holdings = investments() if holdings is None else holdings
    placed, outside = assign(template, holdings)
    lines = [Line(s.label, Decimal(s.target), _value(placed[i]), placed[i], s.ticker or s.isin)
             for i, s in enumerate(template.slots)]
    if outside:
        lines.append(Line(_("Fuori dal modello"), Decimal(0), _value(outside), outside, outside=True))
    total = sum((line.value for line in lines), Decimal(0))
    for line in lines:
        line.weight = (line.value / total * HUNDRED).quantize(Decimal("0.01")) if total else Decimal(0)
    return lines, total


def _with_new_money(lines: list[Line], total: Decimal, amount: Decimal) -> None:
    """Buy only: first what each slot lacks to reach its target on the new total, then the rest by target."""
    after = total + amount
    gaps = {id(line): max(Decimal(0), after * line.target / HUNDRED - line.value) for line in lines}
    lacking = sum(gaps.values(), Decimal(0))
    if lacking >= amount:
        for line in lines:
            line.move = money.cents(amount * gaps[id(line)] / lacking) if lacking else Decimal(0)
    else:
        spare = amount - lacking
        for line in lines:
            line.move = money.cents(gaps[id(line)] + spare * line.target / HUNDRED)
    _round_to(lines, amount)


def _round_to(lines: list[Line], amount: Decimal) -> None:
    """The cents lost rounding each share go to the biggest purchase, so the purchases add up to the amount."""
    biggest = max(lines, key=lambda line: line.move, default=None)
    if biggest is not None and biggest.move > 0:
        biggest.move += amount - sum((line.move for line in lines), Decimal(0))


def _full(lines: list[Line], total: Decimal, amount: Decimal) -> None:
    after = total + amount
    for line in lines:
        line.move = money.cents(after * line.target / HUNDRED - line.value)


def rebalance(template: PortfolioTemplate, mode: str = "new", amount: Decimal = Decimal(0),
              holdings: list[Holding] | None = None) -> Plan:
    lines, total = standing(template, holdings)
    amount = max(Decimal(0), amount)
    (_full if mode == "full" else _with_new_money)(lines, total, amount)
    for line in lines:
        line.via = max(line.holdings, key=lambda h: h.value, default=None)
        if line.via is not None and line.move and line.via.price:
            line.units = (line.move / Decimal(str(line.via.price))).quantize(UNITS, rounding=ROUND_DOWN)
    return Plan(template, lines, total, amount, "full" if mode == "full" else "new")
