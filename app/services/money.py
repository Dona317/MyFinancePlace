"""Rounding of amounts and prices, in one place: euro cents for amounts, six decimals for prices per unit."""
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
PRICE_STEP = Decimal("0.000001")


def cents(value, half_up: bool = False) -> Decimal:
    """`value` rounded to the cent: banker's rounding (Python's default), or half up as tax and brokers do."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP) if half_up else Decimal(value).quantize(CENT)


def price(value) -> Decimal:
    """A price per unit, to six decimals."""
    return Decimal(value).quantize(PRICE_STEP)


def share(part, total, digits: int = 1) -> float:
    """`part` as a percent of `total`, rounded; 0 when there is no total."""
    return round(part / total * 100, digits) if total else 0.0
