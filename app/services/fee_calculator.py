"""
The fee calculator: what a fee in basis points a year costs on the portfolio as it is today — each asset's price
times its quantity, plus the liquidity — with the funds' ongoing charges (TER) and the stamp duty next to it.

With the average buying price (ABP) of each asset it also tells what was spent on commissions and costs so far:
the money put in, less what it bought at the ABP (quantity × ABP) and the liquidity left, is what went elsewhere —
commissions, stamp duty, taxes withheld (dividends and coupons received lower it).

The rows start from the positions (all, one portfolio or one securities account) and the liquidity from the
securities accounts' settlement accounts; on the page every number can be changed, and rows added, to try "what
if" (another adviser's fee, a bigger portfolio).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.services import securities

BASIS_POINT = Decimal("0.0001")      # 1 bp = 0,01 %
STAMP_RATE = Decimal("0.002")        # stamp duty on investments, 0,2 % a year (services.stamp_duty)
CENT = Decimal("0.01")
EMPTY_ROWS = 3                       # blank rows on the page, to add assets by hand


@dataclass
class Row:
    name: str
    units: Decimal
    price: Decimal
    ter: Decimal | None = None       # % a year
    abp: Decimal | None = None       # average buying price (prezzo medio di carico)

    @property
    def value(self) -> Decimal:
        return self.units * self.price

    @property
    def cost(self) -> Decimal:
        """Quantity × ABP (the value when the ABP is not known)."""
        return self.units * (self.abp if self.abp is not None else self.price)

    @property
    def gain(self) -> Decimal:
        return self.value - self.cost

    @property
    def ter_cost(self) -> Decimal:
        return self.value * (self.ter or 0) / 100


@dataclass
class Result:
    rows: list[Row]
    cash: Decimal
    bps: Decimal
    with_ter: bool = True
    with_stamp: bool = True
    years: int = 10
    deposited: Decimal | None = None  # the money put in, net of withdrawals: with it, the costs paid so far

    @property
    def cost(self) -> Decimal:
        return sum((r.cost for r in self.rows), Decimal(0))

    @property
    def gain(self) -> Decimal:
        return self.invested - self.cost

    @property
    def paid(self) -> Decimal | None:
        """Commissions and costs paid so far: money put in − (quantity × ABP of each asset + liquidity)."""
        return _round(self.deposited - self.cost - self.cash) if self.deposited is not None else None

    @property
    def paid_pct(self) -> Decimal | None:
        if self.paid is None or not self.deposited:
            return None
        return (self.paid / self.deposited * 100).quantize(Decimal("0.01"))

    @property
    def invested(self) -> Decimal:
        return sum((r.value for r in self.rows), Decimal(0))

    @property
    def total(self) -> Decimal:
        return self.invested + self.cash

    @property
    def fee(self) -> Decimal:
        """The fee of a year: bps of the total, liquidity included."""
        return _round(self.total * self.bps * BASIS_POINT)

    @property
    def ter(self) -> Decimal:
        return _round(sum((r.ter_cost for r in self.rows), Decimal(0))) if self.with_ter else Decimal(0)

    @property
    def stamp(self) -> Decimal:
        return _round(self.invested * STAMP_RATE) if self.with_stamp else Decimal(0)

    @property
    def costs(self) -> Decimal:
        return self.fee + self.ter + self.stamp

    @property
    def costs_pct(self) -> Decimal:
        return (self.costs / self.total * 100).quantize(Decimal("0.001")) if self.total else Decimal(0)

    @property
    def over_years(self) -> Decimal:
        """The costs over `years`, the portfolio staying as it is (no growth, no compounding)."""
        return self.costs * self.years


def _round(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def number(value, default: Decimal | None = None) -> Decimal | None:
    """A number typed on the page, Italian (1.234,5) or plain (1234.5); `default` when empty or unreadable."""
    text = str(value or "").strip().replace(" ", "").replace("€", "").replace("%", "")
    if not text:
        return default
    if "," in text or re.fullmatch(r"\d{1,3}(\.\d{3})+", text):  # 1.234,5 or 1.000: dots are thousands
        text = text.replace(".", "").replace(",", ".")
    try:
        found = Decimal(text)
    except InvalidOperation:
        return default
    return found if found.is_finite() else default


def starting_rows(portfolio_id: int | None = None, securities_account_id: int | None = None) -> tuple[list[Row], Decimal]:
    """The positions as rows (one per holding) and the liquidity of the securities accounts in scope."""
    by_holding: dict[int, Row] = {}
    for position in securities.positions(portfolio_id=portfolio_id, securities_account_id=securities_account_id):
        holding = position.holding
        row = by_holding.setdefault(holding.id, Row(holding.name, Decimal(0), Decimal(str(holding.price)),
                                                    Decimal(holding.ter) if holding.ter is not None else None,
                                                    Decimal(0)))
        row.units += Decimal(str(position.units))
        row.abp += Decimal(str(position.cost))  # the cost first, divided by the units below
    for row in by_holding.values():
        row.abp = (row.abp / row.units).quantize(Decimal("0.000001")) if row.units else None
    dossiers = [d for d in securities.accounts() if securities_account_id in (None, d.id)]
    cash = sum((Decimal(str(securities.cash(d))) for d in dossiers), Decimal(0)) if portfolio_id is None else Decimal(0)
    return sorted(by_holding.values(), key=lambda r: -r.value), _round(cash)


def from_form(form) -> Result:
    """The calculation from the page's form: rows name-i / units-i / price-i / abp-i / ter-i, cash, bps, ter, stamp,
    years, deposited."""
    rows = []
    for index in range(int(number(form.get("count"), Decimal(0)) or 0)):
        units, price = number(form.get(f"units-{index}")), number(form.get(f"price-{index}"))
        if units is None or price is None or units < 0 or price < 0:
            continue
        ter, abp = number(form.get(f"ter-{index}")), number(form.get(f"abp-{index}"))
        rows.append(Row((form.get(f"name-{index}") or "").strip() or "—", units, price,
                        ter if ter is not None and ter >= 0 else None, abp if abp is not None and abp >= 0 else None))
    years = int(number(form.get("years"), Decimal(10)) or 10)
    return Result(rows, number(form.get("cash"), Decimal(0)) or Decimal(0),
                  max(number(form.get("bps"), Decimal(0)) or Decimal(0), Decimal(0)),
                  with_ter=bool(form.get("with_ter")), with_stamp=bool(form.get("with_stamp")),
                  years=min(max(years, 1), 50), deposited=number(form.get("deposited")))
