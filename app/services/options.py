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


# ── Expiry and exercise (F120.2) ───────────────────────────────────────────────

OUTCOMES = {"worthless": N_("Scaduta senza valore"), "cash": N_("Liquidata in contanti"),
            "exercise": N_("Esercitata o assegnata: consegna del sottostante")}


def open_options():
    """The options still held (bought or written)."""
    from app.models.wealth import Holding

    return [h for h in Holding.query.filter(Holding.option_kind.isnot(None)).order_by(Holding.option_expiry, Holding.id)
            if h.quantity and h.quantity != 0]


def to_settle(today: date | None = None) -> list:
    """Open options whose expiry has come: to be closed (worthless, in cash or by exercise)."""
    today = today or date.today()
    return [h for h in open_options() if h.option_expiry and h.option_expiry <= today]


def underlying_price(holding, on: date) -> Decimal | None:
    """The underlying's price on the expiry day, in its own currency: its close in the price database, else the
    price of the underlying held in the archive (in euro, turned back into the option's currency)."""
    from app.models.wealth import Holding
    from app.services import currency, market_data

    symbol = (holding.underlying or "").strip().upper()
    if not symbol:
        return None
    if market_data.available():
        found = market_data.close_on(symbol, on)
        if found:
            return Decimal(found[1])
    held = Holding.query.filter(Holding.ticker.ilike(symbol), Holding.option_kind.is_(None)).first()
    if held is not None and held.current_price is not None:
        rate = currency.rate_on(holding.currency, on) or Decimal(1)
        return Decimal(held.current_price) / rate
    return None


def suggested(holding, price: Decimal | None) -> str:
    """What most likely happened: worthless when out of the money (or no price), otherwise its settlement."""
    if price is None or intrinsic(holding, float(price)) <= 0:
        return "worthless"
    return "cash" if holding.settlement == "cash" else "exercise"


def _euro(value: Decimal, holding, on: date) -> Decimal:
    from app.services import currency

    return currency.to_base(value, holding.currency, on, target="EUR") if holding.currency else Decimal(value)


def _underlying_holding(holding):
    """The underlying's holding in the archive (by ticker), made when it is not there yet."""
    from app.extensions import db
    from app.models.wealth import Holding

    symbol = holding.underlying.strip().upper()
    found = Holding.query.filter(Holding.ticker.ilike(symbol), Holding.option_kind.is_(None)).first()
    if found is None:
        found = Holding(name=symbol, ticker=symbol, asset_class="Azione", currency=holding.currency, quantity=0,
                        avg_price=0, opening_quantity=0, opening_price=0)
        db.session.add(found)
        db.session.flush()
    return found


def settle(holding, outcome: str, on: date, price: Decimal | None = None) -> list:
    """Close an expired option, each of its positions where it sits: «worthless» at zero, «cash» at its intrinsic
    value (the underlying's price given or found), «exercise» at zero with the underlying bought or sold at the
    strike — a call bought or a put written buy it, a put bought or a call written sell it. The transactions."""
    from app.extensions import db
    from app.models.securities import Portfolio, SecuritiesAccount
    from app.models.transaction import Transaction
    from app.services import money, portfolio_ops, securities

    if outcome not in OUTCOMES:
        raise ValueError(_("Scegli come si è chiusa l'opzione."))
    if not holding.is_option or not holding.quantity:
        raise ValueError(_("Questa opzione non è più aperta."))
    if outcome in ("cash", "exercise") and price is None:
        price = underlying_price(holding, on)
    if outcome == "cash" and price is None:
        raise ValueError(_("Scrivi il prezzo del sottostante alla scadenza: serve per il valore intrinseco."))
    if outcome == "exercise" and not holding.underlying:
        raise ValueError(_("Per l'esercizio serve il sottostante (il suo ticker)."))
    per_unit = _euro(Decimal(str(intrinsic(holding, float(price)))), holding, on) if outcome == "cash" else Decimal(0)
    size = Decimal(holding.multiplier or 1)
    label_text = label(holding)
    created = []
    for position in securities.positions([holding]):
        units = -position.quantity  # back to zero
        if not units:
            continue
        place = db.session.get(SecuritiesAccount, position.securities_account_id) if position.securities_account_id else None
        account = place.settlement_account if place is not None else None
        title = {"worthless": _("Scadenza senza valore"), "cash": _("Liquidazione a scadenza"),
                 "exercise": _("Esercizio")}[outcome]
        trade = Transaction(date=on, description=f"{title} {label_text}", amount=money.cents(abs(units) * per_unit * size),
                            currency="EUR", type="transfer", category="Investimenti", holding_id=holding.id, units=units,
                            unit_price=per_unit, tags=[], account_id=account.id if account and units > 0 else None,
                            counter_account_id=account.id if account and units < 0 else None)
        db.session.add(trade)
        db.session.flush()
        securities.assign([trade], place, db.session.get(Portfolio, position.portfolio_id))
        created.append(trade)
        if outcome == "exercise":
            # a call bought or a put written: the underlying is bought at the strike; the opposite: sold
            buys = (holding.option_kind == "call") == (position.quantity > 0)
            stock = _underlying_holding(holding)
            created += portfolio_ops.record(stock, portfolio_ops.Operation(
                "buy" if buys else "sell", on, account, units=abs(position.quantity) * size,
                price=_euro(Decimal(holding.strike), holding, on), notes=f"{title} {label_text}",
                securities_account=place, exact_place=True, portfolio=db.session.get(Portfolio, position.portfolio_id)))
    portfolio_ops.recompute(holding)
    return created


# ── An option in a broker's statement (F120.4) ─────────────────────────────────

MONTHS = {"JAN": 1, "GEN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "MAG": 5, "JUN": 6, "GIU": 6, "JUL": 7, "LUG": 7,
          "AUG": 8, "AGO": 8, "SEP": 9, "SET": 9, "OCT": 10, "OTT": 10, "NOV": 11, "DEC": 12, "DIC": 12}
# an index option's name in a statement → (the index's ticker, the multiplier)
INDICES = {"MIBO": ("FTSEMIB.MI", Decimal("2.5")), "FTSEMIB": ("FTSEMIB.MI", Decimal("2.5")),
           "FTSE MIB": ("FTSEMIB.MI", Decimal("2.5")), "OESX": ("^STOXX50E", Decimal(10)),
           "SX5E": ("^STOXX50E", Decimal(10)), "EURO STOXX 50": ("^STOXX50E", Decimal(10)),
           "ESTX50": ("^STOXX50E", Decimal(10))}
_OCC_IN_TEXT = re.compile(r"\b([A-Z]{1,6})\s*(\d{6})([CP])(\d{8})\b")
_KIND = re.compile(r"\b(CALL|PUT|C|P)\b")
_KIND_STRIKE = re.compile(r"\b([CP])(\d+(?:[.,]\d+)?)\b")  # Degiro: «C200.00»
_DAY_MON_YY = re.compile(r"(?<![\d,.])\b(\d{1,2})\s?(" + "|".join(MONTHS) + r")\s?(\d{2}|\d{4})\b")
_MON_YY = re.compile(r"\b(" + "|".join(MONTHS) + r")\s?(\d{2}|\d{4})\b")
_DMY = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})\b")
_STRIKE = re.compile(r"(?<![\d/.-])[CP]?(\d+(?:[.,]\d+)?)(?![\d/.-])")
_WORDS = {"CALL", "PUT", "C", "P", "OPZ", "OPZIONE", "OPTION", "OPT", "SU", "ON", "IDEM", "EUREX"}


def third_friday(year: int, month: int) -> date:
    """The usual expiry when a statement gives only the month (IDEM, Eurex, US monthly options)."""
    first = date(year, month, 1)
    return date(year, month, 1 + (4 - first.weekday()) % 7 + 14)


def _year(text: str) -> int:
    return int(text) + (2000 if len(text) == 2 else 0)


def from_description(text: str | None) -> dict | None:
    """The terms of an option in a statement's description — the OCC symbol (IBKR: «AAPL  261218C00200000»),
    «AAPL 18DEC26 200 C», «AAPL C200.00 18DEC26» (Degiro), «CALL ENEL 6,5 DIC26», «MIBO 34000 P 19/12/2026» — with
    the usual multiplier (2,5 € a point on the FTSE MIB, 10 on the Euro Stoxx 50, 100 for shares); None when the
    text is not an option."""
    upper = (text or "").upper()
    found = _OCC_IN_TEXT.search(upper)
    if found:
        terms = parse_occ("".join(found.groups()))
        if terms:
            return {**terms, "multiplier": Decimal(100)}
    joined = _KIND_STRIKE.search(upper)
    kind = _KIND.search(upper)
    if not kind and not joined:
        return None
    kind_word = (kind or joined).group(1)
    expiry, rest = None, upper
    for pattern in (_DAY_MON_YY, _DMY, _MON_YY):
        hit = pattern.search(rest)
        if not hit:
            continue
        try:
            if pattern is _DAY_MON_YY:
                expiry = date(_year(hit.group(3)), MONTHS[hit.group(2)], int(hit.group(1)))
            elif pattern is _DMY:
                expiry = date(_year(hit.group(3)), int(hit.group(2)), int(hit.group(1)))
            else:
                expiry = third_friday(_year(hit.group(2)), MONTHS[hit.group(1)])
        except ValueError:
            continue
        rest = rest[:hit.start()] + " " + rest[hit.end():]
        break
    if expiry is None:
        return None
    if joined and not kind:
        strike_text = joined.group(2)
    else:
        strikes = [m for m in _STRIKE.finditer(rest) if m.group(1)]
        if not strikes:
            return None
        strike_text = strikes[-1].group(1)
    strike = Decimal(strike_text.replace(",", "."))
    index = next((key for key in INDICES if key in upper), None)
    words = [w.strip(".") for w in re.findall(r"[A-Z][A-Z0-9.&-]*", rest)]
    words = [w for w in words if w and w not in _WORDS and not re.fullmatch(r"[CP]\d.*", w)]
    underlying = INDICES[index][0] if index else (words[0] if words else None)
    return {"option_kind": "call" if kind_word.startswith("C") else "put", "strike": strike, "option_expiry": expiry,
            "underlying": underlying, "multiplier": INDICES[index][1] if index else Decimal(100)}
