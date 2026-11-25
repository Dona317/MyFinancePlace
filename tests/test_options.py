"""F120: options as holdings — call or put, strike, expiry, underlying, style, settlement; bought (long) or sold
(written: the premium cashed in, the position below zero); the multiplier in the money that moves."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import options, portfolio_ops, securities

EXPIRY = date(2026, 12, 18)


def _option(db, kind="call", strike="200", quantity=0, price="0", multiplier=100, underlying="AAPL"):
    holding = Holding(name=f"{underlying} {kind}", asset_class="Derivato", option_kind=kind, strike=Decimal(strike),
                      option_expiry=EXPIRY, underlying=underlying, multiplier=multiplier, quantity=quantity,
                      avg_price=Decimal(price), opening_quantity=quantity, opening_price=Decimal(price))
    db.session.add(holding)
    db.session.commit()
    return holding


def test_the_terms(app):
    assert options.occ_symbol("AAPL", EXPIRY, "call", Decimal("200")) == "AAPL261218C00200000"
    assert options.occ_symbol("brk-b", EXPIRY, "put", Decimal("412.5")) == "BRKB261218P00412500"
    assert options.parse_occ("aapl261218c00200000") == {"underlying": "AAPL", "option_expiry": EXPIRY,
                                                       "option_kind": "call", "strike": Decimal("200")}
    assert options.parse_occ("VWCE.MI") is None and options.parse_occ("AAPL261340C00200000") is None
    assert options.is_us("AAPL") and options.is_us("brk-b") and not options.is_us("ENEL.MI")
    assert not options.is_us("^STOXX50E") and not options.is_us("") and not options.is_us(None)
    with app.test_request_context():
        call = Holding(name="x", asset_class="Derivato", option_kind="call", strike=Decimal("200"), option_expiry=EXPIRY,
                       underlying="AAPL")
        assert options.label(call) == "AAPL call 200 · 18/12/2026"
        assert options.label(Holding(name="Opzione", option_kind="put")) == "Opzione put"
        assert options.days_left(call, date(2026, 12, 8)) == 10 and options.days_left(Holding(name="x")) is None
        assert options.intrinsic(call, 215.0) == 15.0 and options.intrinsic(call, 190.0) == 0.0
        put = Holding(name="x", option_kind="put", strike=Decimal("200"))
        assert options.intrinsic(put, 190.0) == 10.0
        assert [options.moneyness(call, p) for p in (215.0, 201.0, 190.0)] == ["itm", "atm", "otm"]
        assert options.moneyness(Holding(name="x", option_kind="call"), 10.0) == "itm"  # no strike: as a zero strike
        options.validate(Holding(name="ETF"))  # not an option: nothing to check
        for bad, message in ((Holding(name="x", strike=Decimal(1)), "call o una put"),
                             (Holding(name="x", option_kind="swap", strike=Decimal(1), option_expiry=EXPIRY), "call o put"),
                             (Holding(name="x", option_kind="call", option_expiry=EXPIRY), "strike"),
                             (Holding(name="x", option_kind="call", strike=Decimal(5)), "scadenza")):
            with pytest.raises(ValueError, match=message):
                options.validate(bad)


def test_the_form(client, db):
    base = {"asset_class": "Derivato", "quantity": "2", "avg_price": "2,50", "price_source": "auto", "multiplier": "100"}
    assert client.post("/portfolio/new", data={**base, "name": "Apple call", "option_kind": "call", "strike": "200",
                                               "option_expiry": "2026-12-18", "underlying": "aapl",
                                               "exercise_style": "american", "settlement": "physical"}).status_code == 302
    call = Holding.query.filter_by(name="Apple call").one()
    assert (call.ticker, call.underlying, call.option_kind, call.strike, call.option_expiry) == (
        "AAPL261218C00200000", "AAPL", "call", Decimal("200"), EXPIRY)
    assert (call.exercise_style, call.settlement, call.value) == ("american", "physical", 500.0)  # 2 × 100 × 2,50
    # the OCC ticker alone says the terms; a written option has a quantity below zero
    assert client.post("/portfolio/new", data={**base, "name": "Apple put", "ticker": "AAPL261218P00180000",
                                               "quantity": "-1"}).status_code == 302
    put = Holding.query.filter_by(name="Apple put").one()
    assert (put.option_kind, put.strike, put.is_short, put.value) == ("put", Decimal("180"), True, -250.0)
    # an IDEM option: no OCC ticker, the price by hand
    assert client.post("/portfolio/new", data={**base, "name": "MIBO", "option_kind": "put", "strike": "34000",
                                               "option_expiry": "2026-12-18", "underlying": "FTSEMIB.MI",
                                               "multiplier": "2,5", "settlement": "cash"}).status_code == 302
    assert Holding.query.filter_by(name="MIBO").one().ticker is None
    bad = client.post("/portfolio/new", data={**base, "name": "Senza strike", "option_kind": "call",
                                              "option_expiry": "2026-12-18"}).get_data(as_text=True)
    assert "strike" in bad and Holding.query.filter_by(name="Senza strike").count() == 0
    short_etf = client.post("/portfolio/new", data={**base, "name": "ETF", "asset_class": "ETF",
                                                    "quantity": "-3"}).get_data(as_text=True)
    assert "sotto zero solo per un" in short_etf


def test_bought_sold_written_and_bought_back(app, db):
    cash = Account(name="Conto broker", currency="EUR")
    db.session.add(cash)
    db.session.commit()
    with app.test_request_context():
        call = _option(db)
        portfolio_ops.record(call, portfolio_ops.Operation("buy", date(2026, 11, 2), cash, units=Decimal(2),
                                                           price=Decimal("2.50"), fee=Decimal(2)))
        trade = Transaction.query.filter(Transaction.holding_id == call.id, Transaction.units.isnot(None)).one()
        assert trade.amount == Decimal("500.00")  # 2 contracts × 100 shares × 2,50: the multiplier moves the money
        assert call.quantity == 2 and call.avg_price == Decimal("2.51")  # the commission: 2 € on 200 shares
        portfolio_ops.record(call, portfolio_ops.Operation("sell", date(2026, 11, 10), cash, units=Decimal(2),
                                                           price=Decimal(4)))
        assert call.quantity == 0
        # written: sold without holding it — the premium cashed in, the position below zero
        put = _option(db, kind="put", strike="180")
        portfolio_ops.record(put, portfolio_ops.Operation("sell", date(2026, 11, 3), cash, units=Decimal(3),
                                                          price=Decimal("1.20"), fee=Decimal(3)))
        assert put.quantity == -3 and put.avg_price == Decimal("1.19")  # 1,20 cashed in less 1 cent of commission
        put.current_price = Decimal("0.50")
        assert put.value == -150.0 and put.cost == pytest.approx(-357.0) and put.gain == pytest.approx(207.0)
        (position,) = securities.positions([put])
        assert position.quantity == -3 and position.avg_price == Decimal("1.19")
        assert position.value == -150.0 and position.gain == pytest.approx(207.0)
        # bought back in two goes: the short gets smaller, then closed; then a long position on the same contract
        portfolio_ops.record(put, portfolio_ops.Operation("buy", date(2026, 11, 12), cash, units=Decimal(1),
                                                          price=Decimal("0.60")))
        assert put.quantity == -2 and put.avg_price == Decimal("1.19")
        portfolio_ops.record(put, portfolio_ops.Operation("buy", date(2026, 11, 13), cash, units=Decimal(3),
                                                          price=Decimal("0.40")))
        assert put.quantity == 1 and put.avg_price == Decimal("0.40")
        (position,) = securities.positions([put])
        assert position.quantity == 1 and position.avg_price == Decimal("0.40")


def test_only_an_option_goes_below_zero(app, db):
    cash = Account(name="Conto", currency="EUR")
    etf = Holding(name="ETF", asset_class="ETF", quantity=1, avg_price=100, opening_quantity=1, opening_price=100)
    db.session.add_all([cash, etf])
    db.session.commit()
    with app.test_request_context():
        with pytest.raises(ValueError, match="più quote di quelle che hai"):
            portfolio_ops.record(etf, portfolio_ops.Operation("sell", date(2026, 11, 3), cash, units=Decimal(2),
                                                              price=Decimal(100)))
        # an option written before the records here (an opening position below zero) shows in the positions
        written = _option(db, kind="call", strike="250", quantity=-1, price="3")
        (position,) = securities.positions([written])
        assert position.quantity == -1 and position.avg_price == Decimal("3")


def test_the_holding_page(client, db):
    put = _option(db, kind="put", strike="180", quantity=-2, price="1.5")
    put.exercise_style, put.settlement, put.currency = "american", "physical", "USD"
    db.session.commit()
    page = client.get(f"/portfolio/{put.id}").get_data(as_text=True)
    assert "AAPL put 180 · 18/12/2026" in page and "venduta" in page and "Premio incassato" in page
    assert "Americana" in page and "Consegna del sottostante" in page
    etf = Holding(name="ETF", asset_class="ETF", quantity=1, avg_price=1)
    db.session.add(etf)
    db.session.commit()
    assert 'id="option-card"' not in client.get(f"/portfolio/{etf.id}").get_data(as_text=True)
