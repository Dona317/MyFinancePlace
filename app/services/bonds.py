"""
Bonds as real instruments (F53): BTP, BOT, CCT and corporate bonds with their coupon schedule, the next coupon, the
accrued interest (rateo), the yield to maturity (gross and net) and the years to maturity.

Conventions, as for the prices of the MOT (services.instrument_sources.borsaitaliana):

- the **quantity is the nominal** (face value) and a price is **per unit of nominal**: 0.98 means a price of 98 % of
  the nominal; the functions here take and give prices in **% of the nominal** (98);
- the coupon rate is the **gross yearly** rate in % of the nominal, paid `coupon_frequency` times a year (1, 2 or 4);
- the coupon dates are the grid that steps back from the maturity date by 12 / frequency months (clamped to the
  month's length); a `first_coupon_date` only drops the dates of the grid before it;
- redemption at maturity is `redemption` % of the nominal (100 when not set);
- the tax is the holding's `tax_rate` when set, otherwise 12.5 % for Italian government bonds (and the white list)
  and 26 % for everything else.

What is simplified (and why the figures are estimates, not the broker's):

- **BTP Italia and BTP€i**: the inflation indexation of the nominal (and of the coupons) is not modelled: coupons are
  the real rate on the nominal as it is, the yield is a real yield before inflation;
- **BTP Valore**: the step-up coupons and the final loyalty bonus (premio fedeltà) are not modelled: the coupon rate
  typed is used for every coupon (type the average rate for a closer yield);
- **CCT**: floating coupons (6-month Euribor + spread): the coupon rate typed (the current one) is assumed to stay;
- **BOT and zero coupons**: no coupons, the whole return is the difference to the redemption;
- the accrued interest is simple ACT/ACT on the current coupon period, at the date given (no T+2 settlement);
- a long or short first coupon is paid as a regular one;
- the yield is the internal rate of return of the cash flows (coupons and redemption) against the price plus the
  accrued interest, with annual compounding and times in days / 365, solved by bisection;
- the net yield takes the tax on every coupon in full and on the gain to the redemption (redemption − price, when
  positive) at maturity; it ignores the accrued interest's own tax treatment, the stamp duty and the fees.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services import periods
from app.services.i18n import N_
from app.services.tax_rules import GOVERNMENT_BOND_RATE

BOND_TYPES = {"btp": N_("BTP"), "btp_italia": N_("BTP Italia"), "btp_valore": N_("BTP Valore"),
              "btp_ei": N_("BTP€i"), "bot": N_("BOT / zero coupon"), "cct": N_("CCT"),
              "corporate": N_("Corporate"), "other": N_("Altro")}
GOVERNMENT = ("btp", "btp_italia", "btp_valore", "btp_ei", "bot", "cct")
ZERO_COUPON = ("bot",)
FREQUENCIES = {1: N_("Annuale"), 2: N_("Semestrale"), 4: N_("Trimestrale")}
CORPORATE_RATE = Decimal(26)
DEFAULT_REDEMPTION = Decimal(100)


@dataclass
class Coupon:
    on: date
    gross: float       # the coupon, in euro, on the holding's nominal (0 for a zero coupon)
    net: float
    redemption: float = 0.0  # the nominal paid back on this date (at maturity), in euro


def is_bond(holding) -> bool:
    """A bond: its instrument says so, or it has a bond's terms."""
    return holding.asset_class == "Obbligazione" or bool(holding.bond_type) or holding.maturity_date is not None


def tax_rate(holding) -> float:
    """The rate on its coupons and gains, %: the holding's own, else 12.5 for government bonds, 26 otherwise."""
    if holding.tax_rate is not None:
        return float(holding.tax_rate)
    return float(GOVERNMENT_BOND_RATE if holding.bond_type in GOVERNMENT else CORPORATE_RATE)


def coupon_rate(holding) -> float:
    """The gross yearly coupon, % of the nominal (0 for BOT and zero coupons)."""
    if holding.bond_type in ZERO_COUPON or holding.coupon_rate is None:
        return 0.0
    return float(holding.coupon_rate)


def frequency(holding) -> int:
    return int(holding.coupon_frequency) if holding.coupon_frequency in FREQUENCIES else 1


def redemption(holding) -> float:
    """What is paid back at maturity, % of the nominal."""
    return float(holding.redemption if holding.redemption is not None else DEFAULT_REDEMPTION)


def nominal(holding) -> float:
    return holding.units


def price_pct(holding) -> float:
    """The price in % of the nominal (prices are kept per unit of nominal: 0.98 → 98)."""
    return holding.price * 100


def _grid(holding, k: int) -> date:
    """The k-th coupon date back from the maturity (k = 0 is the maturity itself)."""
    return periods.add_months(holding.maturity_date, -k * 12 // frequency(holding))


def _period(holding, on: date) -> tuple[date, date] | None:
    """The coupon period holding `on`: (previous coupon date, next coupon date), previous ≤ on < next."""
    if holding.maturity_date is None or on >= holding.maturity_date:
        return None
    k = 0
    while _grid(holding, k + 1) > on:
        k += 1
    return _grid(holding, k + 1), _grid(holding, k)


def years_to_maturity(holding, on: date | None = None) -> float | None:
    on = on or date.today()
    if holding.maturity_date is None:
        return None
    return max(0.0, (holding.maturity_date - on).days / 365.25)


def schedule(holding, after: date | None = None, until: date | None = None) -> list[Coupon]:
    """The coupons (and the redemption, on the last one) paid after `after` (default today) up to `until` (default
    the maturity), on the holding's nominal, gross and net of the tax."""
    after = after or date.today()
    if holding.maturity_date is None or holding.maturity_date <= after:
        return []
    each = nominal(holding) * coupon_rate(holding) / 100 / frequency(holding)
    keep = 1 - tax_rate(holding) / 100
    dates, k = [], 0
    while (on := _grid(holding, k)) > after:
        if holding.first_coupon_date is None or on >= holding.first_coupon_date or k == 0:
            dates.append(on)
        k += 1
    found = []
    for on in reversed(dates):
        if until is not None and on > until:
            break
        last = on == holding.maturity_date
        found.append(Coupon(on, each, each * keep, nominal(holding) * redemption(holding) / 100 if last else 0.0))
    return [c for c in found if c.gross or c.redemption]


def next_coupon(holding, after: date | None = None) -> Coupon | None:
    """The next coupon paid (not the redemption alone of a zero coupon)."""
    return next((c for c in schedule(holding, after) if c.gross), None)


def accrued_pct(holding, on: date | None = None) -> float:
    """The accrued interest (rateo) at `on`, % of the nominal: simple ACT/ACT on the current coupon period."""
    on = on or date.today()
    period = _period(holding, on)
    if period is None or not coupon_rate(holding):
        return 0.0
    start, end = period
    if holding.first_coupon_date is not None and end < holding.first_coupon_date:
        return 0.0  # before the first coupon's period: the grid is not yet running
    return coupon_rate(holding) / frequency(holding) * (on - start).days / (end - start).days


def accrued(holding, on: date | None = None) -> tuple[float, float]:
    """The accrued interest at `on` in euro on the holding's nominal: (gross, net)."""
    gross = nominal(holding) * accrued_pct(holding, on) / 100
    return gross, gross * (1 - tax_rate(holding) / 100)


def _cash_flows(holding, on: date, price: float, net: bool) -> list[tuple[float, float]]:
    """(years from `on`, amount in % of the nominal) of every coupon and of the redemption."""
    keep = 1 - tax_rate(holding) / 100 if net else 1.0
    each = coupon_rate(holding) / frequency(holding) * keep
    flows = []
    for c in schedule(holding, on):
        amount = each if c.gross else 0.0
        if c.redemption:
            paid_back = redemption(holding)
            gain = paid_back - price
            amount += paid_back - (gain * tax_rate(holding) / 100 if net and gain > 0 else 0.0)
        flows.append(((c.on - on).days / 365, amount))
    return flows


def yield_to_maturity(holding, price: float | None = None, on: date | None = None, net: bool = False) -> float | None:
    """The yield to maturity, % a year (annual compounding), buying at `price` (% of the nominal, clean; default the
    holding's) on `on`: the rate that makes the cash flows worth the price plus the accrued interest. None without a
    maturity in the future or a price, or when no rate between −99 % and +100 % solves it."""
    on = on or date.today()
    price = price_pct(holding) if price is None else price
    flows = _cash_flows(holding, on, price, net)
    if not flows or price <= 0:
        return None
    dirty = price + accrued_pct(holding, on)

    def gap(rate: float) -> float:
        return sum(amount / (1 + rate) ** years for years, amount in flows) - dirty

    low, high = -0.99, 1.0
    if gap(low) < 0 or gap(high) > 0:
        return None
    for _ in range(200):
        middle = (low + high) / 2
        if gap(middle) > 0:
            low = middle
        else:
            high = middle
        if high - low < 1e-10:
            break
    return (low + high) / 2 * 100


def summary(holding, on: date | None = None, coupons: int = 6) -> dict | None:
    """What the holding's page shows of a bond with a maturity: coupon, maturity, next coupon, accrued interest,
    yields and the next coupons. None when it is not a bond or has no maturity."""
    if not is_bond(holding) or holding.maturity_date is None:
        return None
    on = on or date.today()
    gross_accrued, net_accrued = accrued(holding, on)
    return {"type": BOND_TYPES.get(holding.bond_type), "coupon_rate": coupon_rate(holding),
            "frequency": FREQUENCIES.get(frequency(holding)), "maturity": holding.maturity_date,
            "redemption": redemption(holding), "tax_rate": tax_rate(holding),
            "years": years_to_maturity(holding, on), "expired": holding.maturity_date <= on,
            "next": next_coupon(holding, on), "accrued_pct": accrued_pct(holding, on),
            "accrued": gross_accrued, "accrued_net": net_accrued, "price_pct": price_pct(holding),
            "ytm": yield_to_maturity(holding, on=on), "ytm_net": yield_to_maturity(holding, on=on, net=True),
            "coupons": schedule(holding, on)[:coupons]}


def upcoming(holdings, on: date | None = None, months: int = 12) -> dict:
    """The coupons expected in the next `months` months from the bonds held, soonest first, with their totals."""
    on = on or date.today()
    until = periods.add_months(on, months)
    rows = sorted(((h, c) for h in holdings if is_bond(h) and h.units > 0
                   for c in schedule(h, on, until) if c.gross), key=lambda row: (row[1].on, row[0].name))
    return {"rows": rows, "gross": sum(c.gross for _, c in rows), "net": sum(c.net for _, c in rows)}
