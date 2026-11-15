"""
Fictitious investments to try the Portfolio section: ETFs of ten different asset classes, shares, bonds, mutual,
insurance and pension funds, on two securities accounts, with almost three years of trades, a model portfolio out of
balance (to try the rebalancing) and the broker statements of both accounts to import.

    DATABASE_URL=postgresql://.../an_EMPTY_scratch_database python samples/dati_fittizi/genera_investimenti.py

What it builds (every operation through services.portfolio_ops, so quantities, average prices, positions per
securities account and per portfolio agree with the app's own computations):
- a current account with the salary, which funds the two securities accounts every month:
  «Dossier Fineco» (2,95 € a trade) and «Conto titoli Directa» (0,19 %, min 1,50, max 18); the insurance and the
  pension fund, paid from the current account, sit in a third container, «Polizza e previdenza (Intesa)»;
- two portfolios: «Crescita» (the default: the ETFs, the growth shares, the mutual fund) and «Reddito» (the bonds,
  the bond ETFs, the dividend shares), each split over both securities accounts where it makes sense;
- 10 ETFs, one per asset class: world and emerging equities, euro government and corporate bonds, money market,
  gold, commodities, real estate, bitcoin, balanced (60/40);
- 6 shares (two in US dollars), 5 bonds (BTP, BTP Valore, BOT already repaid, Bund, a corporate one), a mutual
  fund, a money-market fund, an insurance fund (unit linked) and a pension fund;
- trades from January 2024 to the end of last month: lump sums, a monthly PAC, sales at a gain and at a loss with the
  tax withheld, dividends and coupons net of tax, the yearly stamp duty, a BOT repaid at maturity; a price at the end
  of every month for everything quoted;
- the model portfolio of all the investments (8 parts by asset class, 5 points of band) and one for «Reddito», a
  monthly PAC of 600 € for «Crescita» in the Fineco dossier (F52), to confirm on the 12th, three rules (drift,
  -15 % from the average price, a holding over 25 %).

Written next to this file, in investimenti/:
- backup_investimenti.zip — everything up to the end of last month (Esporta → Backup completo → Ripristina)
- conti_titoli/ — the trades of each securities account as the broker exports them: the whole history
  (storico_*.csv) and only the current month (mese_corrente_*.csv). After the restore, importing either adds only
  this month's trades: the older ones are recognized as already there.
"""
from __future__ import annotations

import csv
import io
import math
import random
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.account import Account  # noqa: E402
from app.models.portfolio_model import InvestmentPlan, PortfolioRule, PortfolioTemplate  # noqa: E402
from app.models.transaction import Transaction  # noqa: E402
from app.models.wealth import Holding  # noqa: E402
from app.services import backup, broker_import, categories, portfolio_models, securities, wealth  # noqa: E402
from app.services.portfolio_ops import Operation, record  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "investimenti"
STATEMENTS = OUT / "conti_titoli"
SEED = 2024
START = date(2024, 1, 1)
CENT = Decimal("0.01")
USD_PER_EUR = {2024: Decimal("1.08"), 2025: Decimal("1.10"), 2026: Decimal("1.15")}


def cents(value) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


# ── The instruments ────────────────────────────────────────────────────────────

@dataclass
class Instrument:
    key: str
    name: str
    kind: str                 # Holding.asset_class: the instrument
    klass: str                # Holding.allocation_class: what it is exposed to
    isin: str | None
    ticker: str | None
    price: float              # price in euro at the start (bonds: per euro of nominal)
    drift: float              # expected change a month
    vol: float                # monthly volatility
    currency: str = "EUR"
    facts: dict | None = None
    bond: dict | None = None
    region: str | None = None
    sector: str | None = None


def etf(issuer, ter, dist, repl, index, domicile="IE"):
    return {"issuer": issuer, "ter": Decimal(str(ter)), "distribution": dist, "replication": repl,
            "index_name": index, "domicile": domicile}


INSTRUMENTS = [
    # ten ETFs, ten asset classes
    Instrument("vwce", "Vanguard FTSE All-World UCITS ETF Acc", "ETF", "Azionario", "IE00BK5BQT80", "VWCE.MI", 108.0,
               0.007, 0.035, facts=etf("Vanguard", 0.22, "acc", "sampling", "FTSE All-World"), region="Globale",
               sector="Diversificato"),
    Instrument("eimi", "iShares Core MSCI EM IMI UCITS ETF", "ETF", "Azionario", "IE00BKM4GZ66", "EIMI.MI", 29.5,
               0.005, 0.045, facts=etf("iShares", 0.18, "acc", "sampling", "MSCI Emerging Markets IMI"),
               region="Mercati emergenti", sector="Diversificato"),
    Instrument("sega", "iShares Core Euro Government Bond UCITS ETF", "ETF", "Obbligazionario", "IE00B4WXJJ64",
               "SEGA.MI", 112.0, 0.002, 0.012, facts=etf("iShares", 0.07, "dist", "sampling",
                                                          "Bloomberg Euro Treasury"),
               region="Europa", sector="Obbligazioni governative"),
    Instrument("ieac", "iShares Core Euro Corporate Bond UCITS ETF", "ETF", "Obbligazionario", "IE00B3F81R35",
               "IEAC.MI", 121.0, 0.003, 0.010, facts=etf("iShares", 0.09, "dist", "sampling",
                                                          "Bloomberg Euro Corporate"),
               region="Europa", sector="Obbligazioni societarie"),
    Instrument("xeon", "Xtrackers II EUR Overnight Rate Swap UCITS ETF", "ETF", "Monetario e liquidità",
               "LU0290358497", "XEON.MI", 140.0, 0.0028, 0.0005,
               facts=etf("Xtrackers", 0.10, "acc", "synthetic", "€STR", "LU"), region="Europa", sector="Monetario"),
    Instrument("sgld", "Invesco Physical Gold ETC", "ETF", "Oro e metalli preziosi", "IE00B579F325", "SGLD.MI", 180.0,
               0.014, 0.040, facts=etf("Invesco", 0.12, "acc", "full", "LBMA Gold Price PM"), region="Globale",
               sector="Oro"),
    Instrument("icom", "iShares Diversified Commodity Swap UCITS ETF", "ETF", "Commodities", "IE00BDFL4P12",
               "ICOM.MI", 6.2, 0.002, 0.045, facts=etf("iShares", 0.19, "acc", "synthetic",
                                                       "Bloomberg Roll Select Commodity"),
               region="Globale", sector="Materie prime"),
    Instrument("iwdp", "iShares Developed Markets Property Yield UCITS ETF", "ETF", "Immobiliare", "IE00B1FZS350",
               "IWDP.MI", 19.5, 0.002, 0.040, facts=etf("iShares", 0.59, "dist", "full", "FTSE EPRA Nareit Developed"),
               region="Paesi sviluppati", sector="Immobiliare"),
    Instrument("abtc", "21Shares Bitcoin ETP", "ETF", "Criptovalute", "CH0454664001", "ABTC.MI", 21.0, 0.030, 0.150,
               facts=etf("21Shares", 1.49, "acc", "full", "Bitcoin", "CH"), region="Altro", sector="Criptovalute"),
    Instrument("v60a", "Vanguard LifeStrategy 60% Equity UCITS ETF Acc", "ETF", "Misto", "IE00BMVB5R75", "V60A.MI",
               27.0, 0.006, 0.022, facts=etf("Vanguard", 0.25, "acc", "sampling", "LifeStrategy 60/40"),
               region="Globale", sector="Diversificato"),
    # shares
    Instrument("enel", "Enel S.p.A.", "Azione", "Azionario", "IT0003128367", "ENEL.MI", 6.10, 0.006, 0.050,
               region="Italia", sector="Utilities"),
    Instrument("isp", "Intesa Sanpaolo S.p.A.", "Azione", "Azionario", "IT0000072618", "ISP.MI", 2.75, 0.014, 0.055,
               region="Italia", sector="Finanza"),
    Instrument("asml", "ASML Holding N.V.", "Azione", "Azionario", "NL0010273215", "ASML.AS", 720.0, 0.004, 0.090,
               region="Europa", sector="Tecnologia"),
    Instrument("lvmh", "LVMH Moët Hennessy Louis Vuitton", "Azione", "Azionario", "FR0000121014", "MC.PA", 760.0,
               -0.007, 0.060, region="Europa", sector="Beni di consumo"),
    Instrument("aapl", "Apple Inc.", "Azione", "Azionario", "US0378331005", "AAPL", 172.0, 0.010, 0.060,
               currency="USD", region="Stati Uniti", sector="Tecnologia"),
    Instrument("msft", "Microsoft Corporation", "Azione", "Azionario", "US5949181045", "MSFT", 350.0, 0.009, 0.050,
               currency="USD", region="Stati Uniti", sector="Tecnologia"),
    # bonds: quantity = nominal, price per euro of nominal
    Instrument("btp33", "BTP 4,40% Mg33", "Obbligazione", "Obbligazionario", "IT0005518128", None, 1.012, 0.001,
               0.012, bond={"bond_type": "btp", "coupon_rate": Decimal("4.40"), "coupon_frequency": 2,
                            "maturity_date": date(2033, 5, 1)}, region="Italia", sector="Obbligazioni governative"),
    Instrument("btpval", "BTP Valore Mg28", "Obbligazione", "Obbligazionario", "IT0005547408", None, 1.000, 0.0006,
               0.004, bond={"bond_type": "btp_valore", "coupon_rate": Decimal("3.70"), "coupon_frequency": 4,
                            "maturity_date": date(2028, 6, 13)}, region="Italia", sector="Obbligazioni governative"),
    Instrument("bot", "BOT 12 mesi Mz26", "Obbligazione", "Obbligazionario", "IT0005638820", None, 0.9725, 0.0, 0.0,
               bond={"bond_type": "bot", "coupon_rate": Decimal("0"), "coupon_frequency": 1,
                     "maturity_date": date(2026, 3, 13)}, region="Italia", sector="Obbligazioni governative"),
    Instrument("bund", "Bund 2,60% Ag34 (Germania)", "Obbligazione", "Obbligazionario", "DE000BU2Z031", None, 0.985,
               0.0008, 0.010, bond={"bond_type": "other", "coupon_rate": Decimal("2.60"), "coupon_frequency": 1,
                                    "maturity_date": date(2034, 8, 15)}, region="Germania",
               sector="Obbligazioni governative"),
    Instrument("eni", "Eni bond 3,625% Gn29", "Obbligazione", "Obbligazionario", "XS2623957078", None, 0.995,
               0.0008, 0.008, bond={"bond_type": "corporate", "coupon_rate": Decimal("3.625"), "coupon_frequency": 1,
                                    "maturity_date": date(2029, 6, 19)}, region="Italia",
               sector="Obbligazioni societarie"),
    # funds of other kinds
    Instrument("fidelity", "Fidelity World Fund A-Acc-EUR", "Fondo comune", "Azionario", "LU0261950470", None, 31.0,
               0.008, 0.038, facts={"issuer": "Fidelity", "ter": Decimal("1.89"), "distribution": "acc",
                                    "replication": "active", "domicile": "LU"}, region="Globale",
               sector="Diversificato"),
    Instrument("monetario", "Amundi Euro Liquidity Short Term SRI", "Fondo comune", "Monetario e liquidità",
               "FR0007435920", None, 1050.0, 0.0029, 0.0004,
               facts={"issuer": "Amundi", "ter": Decimal("0.12"), "distribution": "acc", "replication": "active",
                      "domicile": "FR"}, region="Europa", sector="Monetario"),
    Instrument("unit", "Generali Valore Futuro (unit linked)", "Fondo assicurativo", "Misto", None, None, 10.0, 0.003,
               0.015, facts={"issuer": "Generali", "ter": Decimal("1.60"), "distribution": "acc",
                             "replication": "active"}, region="Globale", sector="Diversificato"),
    Instrument("pensione", "Fondo pensione aperto Amundi SecondaPensione", "Fondo Pensione", "Misto", None, None,
               12.0, 0.004, 0.012),
]
BY_KEY = {i.key: i for i in INSTRUMENTS}
QUOTED_MONTHLY = [i.key for i in INSTRUMENTS if i.key not in ("unit", "pensione")]


def month_ends(first: date, last: date) -> list[date]:
    out, day = [], first
    while True:
        end = date(day.year + (day.month == 12), day.month % 12 + 1, 1) - timedelta(days=1)
        if end > last:
            return out
        out.append(end)
        day = end + timedelta(days=1)


def price_paths(ends: list[date]) -> dict[str, dict[date, Decimal]]:
    """A random walk for each instrument, one point at the end of every month; bonds are pulled to par as they near
    maturity, the BOT grows to 1 by its maturity."""
    rnd = random.Random(SEED)
    paths = {}
    market = [rnd.gauss(0, 1) for _ in ends]  # a shared shock: equities fall together
    for inst in INSTRUMENTS:
        price, points = inst.price, {}
        for k, end in enumerate(ends):
            if inst.key == "bot":
                span = (inst.bond["maturity_date"] - date(2025, 3, 13)).days
                done = min(1.0, max(0.0, (end - date(2025, 3, 13)).days / span))
                price = 0.9725 + (1 - 0.9725) * done
            else:
                shock = 0.6 * market[k] + 0.8 * rnd.gauss(0, 1) if inst.klass in ("Azionario", "Misto", "Immobiliare") \
                    else rnd.gauss(0, 1)
                price *= math.exp(inst.drift + inst.vol * shock - inst.vol ** 2 / 2)
                if inst.bond:
                    price += (1.0 - price) * 0.02  # towards the redemption at par
            digits = 4 if inst.bond else (2 if price > 5 else 3)
            points[end] = Decimal(str(round(price, digits)))
        paths[inst.key] = points
    return paths


# ── The operations ─────────────────────────────────────────────────────────────

@dataclass
class Trade:
    on: date
    key: str
    side: str                 # buy | sell
    units: Decimal
    price: Decimal            # in euro
    dossier: str              # fineco | directa
    portfolio: str            # crescita | reddito


@dataclass
class Income:
    on: date
    key: str
    kind: str                 # dividend | coupon | tax
    amount: Decimal
    dossier: str
    portfolio: str


class Book:
    """The plan of every operation, written down before any is recorded."""

    def __init__(self, paths: dict, today: date):
        self.paths, self.today = paths, today
        self.trades: list[Trade] = []
        self.incomes: list[Income] = []

    def price(self, key: str, on: date) -> Decimal:
        """The price on a day: between the two month-end points around it."""
        series = sorted(self.paths[key].items())
        before = [p for d, p in series if d <= on]
        after = [p for d, p in series if d > on]
        if not before:
            return Decimal(str(BY_KEY[key].price)) if not after else after[0]
        if not after:
            return before[-1]
        digits = Decimal("0.0001") if BY_KEY[key].bond else CENT
        return ((before[-1] + after[0]) / 2).quantize(digits)

    def buy(self, on, key, dossier, portfolio, money=None, units=None, price=None):
        price = price or self.price(key, on)
        if units is None:
            step = Decimal(1000) if key in BY_KEY and BY_KEY[key].bond else Decimal(1)
            units = (Decimal(money) / price / step).quantize(Decimal(1)) * step
        self.trades.append(Trade(on, key, "buy", Decimal(units), price, dossier, portfolio))

    def sell(self, on, key, dossier, portfolio, units, price=None):
        self.trades.append(Trade(on, key, "sell", Decimal(units), price or self.price(key, on), dossier, portfolio))

    def income(self, on, key, kind, amount, dossier, portfolio):
        if on <= self.today:
            self.incomes.append(Income(on, key, kind, cents(amount), dossier, portfolio))


def first_weekday(year: int, month: int, day: int) -> date:
    on = date(year, month, day)
    while on.weekday() >= 5:
        on += timedelta(days=1)
    return on


def plan(book: Book, last: date) -> None:
    """Every trade from January 2024 to `last` (the current month included: it goes to the statements only)."""
    months = [(y, m) for y in range(2024, last.year + 1) for m in range(1, 13) if date(y, m, 1) <= last]
    # lump sums at the start
    for key, money in (("vwce", 20000), ("eimi", 4000), ("sgld", 4000), ("icom", 1500), ("iwdp", 2000),
                       ("v60a", 3000), ("xeon", 3000), ("abtc", 1000)):
        book.buy(first_weekday(2024, 1, 15), key, "fineco", "crescita", money)
    book.buy(first_weekday(2024, 2, 5), "sega", "directa", "reddito", 6000)
    book.buy(first_weekday(2024, 2, 5), "ieac", "directa", "reddito", 4000)
    book.buy(first_weekday(2024, 2, 20), "btpval", "directa", "reddito", units=10000, price=Decimal("1.0000"))
    book.buy(first_weekday(2024, 3, 4), "enel", "directa", "reddito", units=1000)
    book.buy(first_weekday(2024, 3, 4), "isp", "directa", "reddito", units=1500)
    book.buy(first_weekday(2024, 3, 18), "asml", "directa", "crescita", units=5)
    book.buy(first_weekday(2024, 3, 18), "lvmh", "directa", "crescita", units=6)
    book.buy(first_weekday(2024, 4, 8), "aapl", "directa", "crescita", units=15)
    book.buy(first_weekday(2024, 4, 8), "msft", "directa", "crescita", units=8)
    book.buy(first_weekday(2024, 4, 22), "fidelity", "fineco", "crescita", 5000)
    book.buy(first_weekday(2024, 6, 10), "btp33", "directa", "reddito", units=8000)
    book.buy(first_weekday(2024, 9, 16), "monetario", "fineco", "reddito", units=3)
    book.buy(first_weekday(2025, 1, 13), "bund", "directa", "reddito", units=5000)
    book.buy(date(2025, 3, 13), "bot", "directa", "reddito", units=5000, price=Decimal("0.9725"))
    book.buy(first_weekday(2025, 6, 23), "eni", "directa", "reddito", units=4000)
    book.buy(first_weekday(2025, 2, 10), "enel", "fineco", "reddito", units=500)  # the same share on both dossiers
    # the monthly PAC on Fineco (12th)
    for year, month in months:
        day = first_weekday(year, month, 12)
        if (year, month) > (2024, 1) and day <= last:
            book.buy(day, "vwce", "fineco", "crescita", 500)
            book.buy(day, "eimi", "fineco", "crescita", 100)
    # sales: gold taken back to target after its rise, half of LVMH at a loss, part of Apple at a gain, BOT repaid
    book.sell(first_weekday(2025, 3, 17), "sgld", "fineco", "crescita", 6)
    book.sell(first_weekday(2025, 9, 15), "lvmh", "directa", "crescita", 3)
    book.sell(first_weekday(2025, 12, 1), "aapl", "directa", "crescita", 5)
    book.sell(date(2026, 3, 13), "bot", "directa", "reddito", 5000, price=Decimal("1.0000"))
    book.sell(first_weekday(2026, 5, 18), "abtc", "fineco", "crescita", 15)
    # this month (in the statements only): money-market top-up, a new small-cap ETF, a new BTP, more Enel, part of
    # Microsoft and of the world ETF sold
    now = last.replace(day=1)
    book.buy(first_weekday(now.year, now.month, 3), "xeon", "fineco", "crescita", 2000)
    book.buy(first_weekday(now.year, now.month, 5), "wsml", "fineco", "crescita", 3000, price=NEW_THIS_MONTH["wsml"][3])
    book.buy(first_weekday(now.year, now.month, 4), "btppiu", "directa", "reddito", units=5000,
             price=NEW_THIS_MONTH["btppiu"][3])
    book.buy(first_weekday(now.year, now.month, 6), "enel", "directa", "reddito", units=300)
    book.sell(first_weekday(now.year, now.month, 9), "msft", "directa", "crescita", 3)
    book.sell(first_weekday(now.year, now.month, 6), "vwce", "fineco", "crescita", 20)


NEW_THIS_MONTH = {  # instruments that appear only in this month's statements (created by the import)
    "wsml": ("iShares MSCI World Small Cap UCITS ETF", "IE00BF4RFH31", "WSML.MI", Decimal("7.45")),
    "btppiu": ("BTP Più Fb33", "IT0005634800", None, Decimal("1.0035")),
}


def held(book: Book, key: str, dossier: str, portfolio: str, on: date) -> Decimal:
    units = Decimal(0)
    for t in book.trades:
        if t.key == key and t.dossier == dossier and t.portfolio == portfolio and t.on <= on:
            units += t.units if t.side == "buy" else -t.units
    return units


def incomes(book: Book, last: date) -> None:
    """Dividends (net of 26 %), coupons (net of 12,5 %) and the tax withheld on the gains of the sales."""
    dividends = {  # key: (months, gross per share in euro)
        "enel": ((1, 7), Decimal("0.215")), "isp": ((5, 11), Decimal("0.17")), "asml": ((2, 5, 8, 11), Decimal("1.6")),
        "lvmh": ((4, 12), Decimal("6.5")), "aapl": ((2, 5, 8, 11), Decimal("0.23")),
        "msft": ((3, 6, 9, 12), Decimal("0.72")), "sega": ((6, 12), Decimal("0.95")), "ieac": ((6, 12), Decimal("1.15")),
        "iwdp": ((3, 6, 9, 12), Decimal("0.18")),
    }
    places = {(t.key, t.dossier, t.portfolio) for t in book.trades}
    for year in range(2024, last.year + 1):
        for key, (when, gross) in dividends.items():
            for month in when:
                on = first_weekday(year, month, 22)
                for _k, dossier, portfolio in [p for p in places if p[0] == key]:
                    units = held(book, key, dossier, portfolio, on)
                    if units > 0 and on < last.replace(day=1):
                        book.income(on, key, "dividend", units * gross * Decimal("0.74"), dossier, portfolio)
    for key in ("btp33", "btpval", "bund", "eni"):
        inst = BY_KEY[key]
        rate, freq, maturity = inst.bond["coupon_rate"], inst.bond["coupon_frequency"], inst.bond["maturity_date"]
        step = 12 // freq
        for year in range(2024, last.year + 1):
            for month in range(maturity.month % step or step, 13, step):
                on = date(year, month, min(maturity.day, 28))
                units = held(book, key, "directa", "reddito", on - timedelta(days=1))
                if units > 0 and on < last.replace(day=1):
                    tax = Decimal("0.125") if inst.bond["bond_type"] != "corporate" else Decimal("0.26")
                    book.income(on, key, "coupon", units * rate / 100 / freq * (1 - tax), "directa", "reddito")
    # the tax on the gains, withheld by the broker (amministrato) on the day of the sale
    for sale in [t for t in book.trades if t.side == "sell" and t.on < last.replace(day=1)]:
        buys = [t for t in book.trades if t.key == sale.key and t.side == "buy" and t.on <= sale.on
                and t.dossier == sale.dossier]
        cost = sum((t.units * t.price for t in buys), Decimal(0)) / sum((t.units for t in buys), Decimal(0))
        gain = (sale.price - cost) * sale.units
        rate = Decimal("0.125") if BY_KEY[sale.key].bond and BY_KEY[sale.key].bond["bond_type"] != "corporate" \
            else Decimal("0.26")
        if gain > 0:
            book.income(sale.on, sale.key, "tax", gain * rate, sale.dossier, sale.portfolio)


# ── The broker statements ──────────────────────────────────────────────────────

def _it(value: Decimal, digits: int = 2) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def fee(dossier: str, gross: Decimal) -> Decimal:
    if dossier == "fineco":
        return Decimal("2.95")
    return min(Decimal(18), max(Decimal("1.50"), cents(gross * Decimal("0.0019"))))


def instrument(key: str) -> tuple[str, str | None, str | None]:
    if key in NEW_THIS_MONTH:
        name, isin, ticker, _p = NEW_THIS_MONTH[key]
        return name, isin, ticker
    inst = BY_KEY[key]
    return inst.name, inst.isin, inst.ticker


def fineco_csv(trades: list[Trade]) -> str:
    """The «Movimenti dossier» of Fineco: semicolon, A/V sign, the price in the instrument's currency with the
    exchange rate, the value in euro, bonds in % of the nominal."""
    out = io.StringIO()
    w = csv.writer(out, delimiter=";", lineterminator="\n")
    w.writerow(["Data operazione", "Data valuta", "Descrizione", "Titolo", "Isin", "Segno", "Quantita", "Divisa",
                "Prezzo", "Cambio", "Controvalore", "Commissioni amministrato"])
    for t in trades:
        name, isin, _ticker = instrument(t.key)
        gross = cents(t.units * t.price)
        bond = BY_KEY.get(t.key) and BY_KEY[t.key].bond or t.key == "btppiu"
        w.writerow([t.on.strftime("%d/%m/%Y"), (t.on + timedelta(days=2)).strftime("%d/%m/%Y"),
                    "Compravendita titoli", name, isin, "A" if t.side == "buy" else "V", _it(t.units, 0), "EUR",
                    _it(t.price * 100, 3) if bond else _it(t.price, 4), "1,0000", _it(gross),
                    _it(fee("fineco", gross))])
    return out.getvalue()


def directa_csv(trades: list[Trade], extras: list[Income]) -> str:
    """Directa's «Movimenti»: comma, the type of operation in words, no price (the value in euro and, for US
    shares, in dollars), dividends and coupons among the rows (with no quantity: not trades)."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["Data Operazione", "Data Valuta", "Tipo Operazione", "Ticker", "Isin", "Descrizione", "Quantità",
                "Importo euro", "Importo Divisa", "Divisa", "Commissioni"])
    rows = []
    for t in trades:
        name, isin, ticker = instrument(t.key)
        gross = cents(t.units * t.price)
        usd = BY_KEY.get(t.key) and BY_KEY[t.key].currency == "USD"
        rate = USD_PER_EUR[t.on.year]
        rows.append((t.on, [t.on.strftime("%d-%m-%Y"), (t.on + timedelta(days=2)).strftime("%d-%m-%Y"),
                            "Acquisto" if t.side == "buy" else "Vendita", (ticker or "").split(".")[0], isin, name,
                            f"{t.units:f}", f"{(-gross if t.side == 'buy' else gross):.2f}",
                            f"{(-gross if t.side == 'buy' else gross) * rate:.2f}" if usd else "",
                            "USD" if usd else "EUR", f"{fee('directa', gross):.2f}"]))
    for i in extras:
        name, isin, ticker = instrument(i.key)
        word = {"dividend": "Dividendo", "coupon": "Cedola", "tax": "Ritenuta capital gain"}[i.kind]
        amount = i.amount if i.kind != "tax" else -i.amount
        rows.append((i.on, [i.on.strftime("%d-%m-%Y"), i.on.strftime("%d-%m-%Y"), word, (ticker or "").split(".")[0],
                            isin, name, "", f"{amount:.2f}", "", "EUR", ""]))
    for _on, row in sorted(rows, key=lambda r: r[0]):
        w.writerow(row)
    return out.getvalue()


def statements(book: Book, cutoff: date) -> dict[str, str]:
    """{file name: content}: the whole history and this month only, for each securities account."""
    files = {}
    for dossier in ("fineco", "directa"):
        trades = sorted((t for t in book.trades if t.dossier == dossier), key=lambda t: (t.on, t.key))
        extras = [i for i in book.incomes if i.dossier == dossier]
        recent = [t for t in trades if t.on >= cutoff]
        write = (lambda ts, xs: fineco_csv(ts)) if dossier == "fineco" else directa_csv
        files[f"storico_{dossier}.csv"] = write(trades, extras)
        files[f"mese_corrente_{dossier}.csv"] = write(recent, [i for i in extras if i.on >= cutoff])
    return files


# ── The database ───────────────────────────────────────────────────────────────

def fill(today: date) -> dict:
    categories.ensure_defaults()
    cutoff = today.replace(day=1)              # the backup ends the day before; this month is in the statements
    ends = month_ends(START, cutoff - timedelta(days=1))
    paths = price_paths(ends)
    book = Book(paths, today)
    plan(book, today)
    incomes(book, today)
    files = statements(book, cutoff)

    current = Account(name="Conto corrente Intesa", kind="current", opening_balance=Decimal("8000"), bank="Intesa Sanpaolo",
                      iban_tail="5531", favorite=True)
    fineco = Account(name="Liquidità Fineco", kind="other", opening_balance=Decimal("56000"), bank="Fineco",
                     iban_tail="1187", fee_fixed=Decimal("2.95"))
    directa = Account(name="Liquidità Directa", kind="other", opening_balance=Decimal("62000"), bank="Directa",
                      iban_tail="9042", fee_percent=Decimal("0.19"), fee_min=Decimal("1.50"), fee_max=Decimal(18))
    db.session.add_all([current, fineco, directa])
    db.session.flush()
    dossiers = {
        "fineco": securities.save_account(None, {"name": "Dossier Fineco", "settlement_account_id": fineco.id,
                                                 "broker": "Fineco", "fee_fixed": Decimal("2.95")}),
        "directa": securities.save_account(None, {"name": "Conto titoli Directa", "settlement_account_id": directa.id,
                                                  "broker": "Directa", "fee_percent": Decimal("0.19"),
                                                  "fee_min": Decimal("1.50"), "fee_max": Decimal(18)}),
        # not a broker: where the insurance fund and the pension fund sit, paid from the current account
        "previdenza": securities.save_account(None, {"name": "Polizza e previdenza (Intesa)",
                                                     "settlement_account_id": current.id,
                                                     "broker": "Generali · Amundi SGR"}),
    }
    folios = {"crescita": securities.save_portfolio(None, "Crescita", "Lungo periodo: ETF, azioni di crescita, fondo"),
              "reddito": securities.save_portfolio(None, "Reddito", "Cedole e dividendi: obbligazioni e azioni da dividendo")}
    securities.set_default(folios["crescita"])

    holdings = {}
    for inst in INSTRUMENTS:
        h = Holding(name=inst.name, asset_class=inst.kind, allocation_class=inst.klass, isin=inst.isin,
                    ticker=inst.ticker, currency=inst.currency, quantity=Decimal(0), avg_price=Decimal(0),
                    opening_quantity=Decimal(0), opening_price=Decimal(0), region=inst.region, sector=inst.sector,
                    price_source="manual" if inst.key in ("unit", "pensione") else "auto")
        for field, value in {**(inst.facts or {}), **(inst.bond or {})}.items():
            setattr(h, field, value)
        if inst.currency == "USD":
            h.abroad = False  # held through an Italian broker: stamp duty, not IVAFE
        holdings[inst.key] = h
    db.session.add_all(holdings.values())
    db.session.flush()

    # every event in date order: money in, prices, trades, incomes, so a sale always finds its units
    events: list[tuple[date, int, object]] = []
    for key in QUOTED_MONTHLY:
        for on, price in paths[key].items():
            events.append((on, 9, ("price", key, price)))
    for t in book.trades:
        if t.on < cutoff:
            events.append((t.on, 2 if t.side == "buy" else 1, t))
    for i in book.incomes:
        if i.on < cutoff:
            events.append((i.on, 3, i))
    for year, month in [(y, m) for y in range(2024, today.year + 1) for m in range(1, 13)
                        if date(y, m, 1) < cutoff]:
        events.append((date(year, month, 27), 0, ("salary", year, month)))
        events.append((date(year, month, 10), 0, ("transfer", year, month)))
        events.append((date(year, month, 16), 0, ("pension", year, month)))
        if month == 12:
            events.append((date(year, 12, 31), 8, ("stamp", year, month)))
    events.append((first_weekday(2024, 5, 6), 0, ("unit", 2024, 5)))
    events.append((date(2024, 1, 31), 9, ("manual", "unit", Decimal("10.00"))))
    for k, end in enumerate(ends):
        if end.month in (3, 6, 9, 12):
            events.append((end, 9, ("manual", "unit", Decimal(str(round(10 * 1.004 ** (k + 1), 3))))))
        events.append((end, 9, ("manual", "pensione", Decimal(str(round(12 * 1.004 ** (k + 1), 3))))))
    events.sort(key=lambda e: (e[0], e[1]))

    trade_rows: dict[int, Transaction] = {}   # id(Trade) → its transaction
    pension_units = Decimal(0)
    for on, _order, item in events:
        if isinstance(item, Trade):
            h, place = holdings[item.key], dossiers[item.dossier]
            gross = cents(item.units * item.price)
            made = record(h, Operation(item.side, on, place.settlement_account, units=item.units, price=item.price,
                                       fee=fee(item.dossier, gross), securities_account=place,
                                       portfolio=folios[item.portfolio]))
            trade_rows[id(item)] = made[0]
        elif isinstance(item, Income):
            place = dossiers[item.dossier]
            record(holdings[item.key], Operation(item.kind, on, place.settlement_account, amount=item.amount,
                                                 securities_account=place, portfolio=folios[item.portfolio]))
        elif item[0] in ("price", "manual"):
            wealth.record_price(holdings[item[1]], item[2], on)
        elif item[0] == "salary":
            raise_ = Decimal(150) if item[1] >= 2025 else Decimal(0)
            db.session.add(Transaction(date=on, description="Stipendio", amount=Decimal(3100) + raise_, type="income",
                                       category="Stipendio", account_id=current.id, counterparty="Datore di lavoro",
                                       tags=[]))
            db.session.add(Transaction(date=on.replace(day=3), description="Spese di casa e famiglia",
                                       amount=Decimal(1650), type="expense", category="Casa", account_id=current.id,
                                       counterparty="Varie", tags=[]))
        elif item[0] == "transfer":
            for target, amount in ((fineco, Decimal(700)), (directa, Decimal(150))):
                db.session.add(Transaction(date=on, description=f"Giroconto verso {target.name}", amount=amount,
                                           type="transfer", category="Giroconto", account_id=current.id,
                                           counter_account_id=target.id, counterparty=target.bank, tags=[]))
        elif item[0] == "pension":
            price = Decimal(holdings["pensione"].current_price or 12)
            units = (Decimal(150) / price).quantize(Decimal("0.0001"))
            pension_units += units
            record(holdings["pensione"], Operation("buy", on, current, units=units, price=price,
                                                   securities_account=dossiers["previdenza"],
                                                   portfolio=folios["crescita"]))
        elif item[0] == "unit":
            record(holdings["unit"], Operation("buy", on, current, units=Decimal(500), price=Decimal("10.00"),
                                               securities_account=dossiers["previdenza"],
                                               portfolio=folios["crescita"]))
        elif item[0] == "stamp":
            for place in (dossiers["fineco"], dossiers["directa"]):
                value = sum((Decimal(str(p.value)) for p in securities.positions()
                             if p.securities_account_id == place.id), Decimal(0))
                db.session.add(Transaction(date=on, description=f"Imposta di bollo titoli {item[1]}",
                                           amount=cents(value * Decimal("0.002")), type="expense",
                                           category="Tasse e imposte", account_id=place.settlement_account_id,
                                           securities_account_id=place.id, counterparty=place.broker, tags=[]))
    db.session.flush()

    # the trades of the backup carry the fingerprint the import would give them: importing the statements again adds
    # only what is new
    for name, content in files.items():
        if not name.startswith("storico_"):
            continue
        dossier = name.removeprefix("storico_").removesuffix(".csv")
        trades = sorted((t for t in book.trades if t.dossier == dossier), key=lambda t: (t.on, t.key))
        preview = broker_import.read(name, content.encode("utf-8"))
        by_line = {row.line: row for row in preview.rows}
        lines = sorted(by_line)
        if len(lines) != len(trades):
            raise SystemExit(f"{name}: {len(lines)} trades read, {len(trades)} written")
        # the rows come back in file order (by date, then line): pair them with the trades written
        for line, trade in zip(lines, trades):
            tx = trade_rows.get(id(trade))
            if tx is not None:
                tx.import_ref = by_line[line].ref

    model_and_rules(holdings, folios, fineco, dossiers["fineco"])
    db.session.commit()
    return {"files": files, "cutoff": cutoff, "trades": len(trade_rows), "holdings": holdings}


def model_and_rules(holdings: dict, folios: dict, fineco: Account, dossier) -> None:
    """The model portfolio of everything, by asset class (out of band on purpose: equities grew, bonds lag), the one
    of «Reddito», the monthly PAC and three watches."""
    ids = {key: h.id for key, h in holdings.items()}
    parts = [("Azioni", 50, ["vwce", "eimi", "enel", "isp", "asml", "lvmh", "aapl", "msft", "fidelity"]),
             ("Obbligazioni", 28, ["sega", "ieac", "btp33", "btpval", "bot", "bund", "eni"]),
             ("Monetario", 5, ["xeon", "monetario"]),
             ("Oro", 5, ["sgld"]),
             ("Materie prime", 2, ["icom"]),
             ("Immobiliare", 3, ["iwdp"]),
             ("Bitcoin", 1, ["abtc"]),
             ("Bilanciato", 6, ["v60a", "unit"])]
    every = PortfolioTemplate(name="Allocazione per classi", band=5)
    db.session.add(every)
    portfolio_models.save(every, "Allocazione per classi", "Otto classi di attivo, tolleranza 5 punti", Decimal(5),
                          [portfolio_models.SlotInput(label, Decimal(target), isin=holdings[keys[0]].isin,
                                                      holding_ids=[ids[k] for k in keys])
                           for label, target, keys in parts])
    portfolio_models.activate(every)
    income = PortfolioTemplate(name="Reddito 75/25", band=5, portfolio_id=folios["reddito"].id)
    db.session.add(income)
    portfolio_models.save(income, "Reddito 75/25", "Obbligazioni e azioni da dividendo", Decimal(5),
                          [portfolio_models.SlotInput("Obbligazioni", Decimal(75), holding_ids=[
                              ids[k] for k in ("sega", "ieac", "btp33", "btpval", "bot", "bund", "eni", "monetario")]),
                           portfolio_models.SlotInput("Azioni da dividendo", Decimal(25),
                                                      holding_ids=[ids["enel"], ids["isp"]])])
    portfolio_models.activate(income)
    db.session.add(InvestmentPlan(name="PAC mensile Fineco", amount=Decimal(600), frequency="monthly", day=12,
                                  account_id=fineco.id, template_id=every.id, fractional=False, start=date(2024, 2, 12),
                                  portfolio_id=folios["crescita"].id, securities_account_id=dossier.id))
    db.session.add_all([PortfolioRule(kind="drift"), PortfolioRule(kind="drawdown", threshold=Decimal(15)),
                        PortfolioRule(kind="concentration", threshold=Decimal(25))])


def main() -> None:
    app = create_app()
    app.instance_path = tempfile.mkdtemp(prefix="mfp_inv_")
    today = date.today()
    with app.test_request_context():
        if db.inspect(db.engine).get_table_names():
            sys.exit("The database is not empty: use an empty scratch database (see the top of this file).")
        db.create_all()
        result = fill(today)
        OUT.mkdir(exist_ok=True)
        STATEMENTS.mkdir(exist_ok=True)
        (OUT / "backup_investimenti.zip").write_bytes(backup.create_archive())
        for name, content in result["files"].items():
            (STATEMENTS / name).write_text(content, encoding="utf-8")
        template = portfolio_models.active()
        lines, total = portfolio_models.standing(template)
        print(f"{result['trades']} trades up to {result['cutoff'] - timedelta(days=1)}; investments {total} €")
        for line in lines:
            print(f"  {line.label:<16} target {line.target:>5} %  now {line.weight:>6} %  {line.value:>10} €")
        print("files:", ", ".join(sorted(result["files"])))


if __name__ == "__main__":
    main()
