"""F120: options as holdings — call or put, strike, expiry, underlying, style, settlement; bought (long) or sold
(written: the premium cashed in, the position below zero); the multiplier in the money that moves."""
from datetime import date, timedelta
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
    assert "non può essere negativo" in short_etf  # only an option is sold without being held


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


# ── Expiry and exercise (F120.2) ───────────────────────────────────────────────

@pytest.fixture()
def store(app, tmp_path, monkeypatch):
    from app.services import market_data
    monkeypatch.delenv(market_data.ENV, raising=False)
    app.instance_path = str(tmp_path)
    yield


def _bought(db, app, holding, units="1", price="2.5"):
    cash = Account.query.filter_by(name="Broker").first() or Account(name="Broker", currency="EUR")
    db.session.add(cash)
    db.session.commit()
    side = "buy" if Decimal(units) > 0 else "sell"
    portfolio_ops.record(holding, portfolio_ops.Operation(side, date(2026, 11, 2), cash, units=abs(Decimal(units)),
                                                         price=Decimal(price)))
    db.session.commit()
    return cash


def test_what_is_suggested_and_where_the_underlying_price_comes_from(app, db, store):
    from app.services import market_data
    with app.test_request_context():
        call = _option(db)
        assert options.suggested(call, None) == "worthless" and options.suggested(call, Decimal(190)) == "worthless"
        assert options.suggested(call, Decimal(215)) == "exercise"
        call.settlement = "cash"
        assert options.suggested(call, Decimal(215)) == "cash"
        assert options.underlying_price(call, EXPIRY) is None
        call.underlying = None
        assert options.underlying_price(call, EXPIRY) is None
        call.underlying = "AAPL"
        held = Holding(name="Apple", ticker="aapl", asset_class="Azione", quantity=1, avg_price=1, current_price=Decimal(210))
        db.session.add(held)
        db.session.commit()
        assert options.underlying_price(call, EXPIRY) == Decimal(210)  # the share held in the archive
        market_data.store("AAPL", market_data.Daily("USD", None, None, [(EXPIRY, Decimal("214.5"), None)]))
        assert options.underlying_price(call, EXPIRY) == Decimal("214.5")  # its close in the price database
        assert options.open_options() == [] and options.to_settle(EXPIRY) == []  # nothing held yet
        _bought(db, app, call)
        assert options.open_options() == [call] and options.to_settle(EXPIRY) == [call]
        assert options.to_settle(date(2026, 12, 17)) == []


def test_worthless_in_cash_and_exercised(app, db, store):
    with app.test_request_context():
        # bought and out of the money: closed at zero
        call = _option(db, strike="250")
        _bought(db, app, call)
        created = options.settle(call, "worthless", EXPIRY)
        assert call.quantity == 0 and created[0].amount == 0 and created[0].description.startswith("Scadenza senza valore")
        # an IDEM put on the FTSE MIB, settled in cash: (34.000 − 33.000) × 2,5 € a point
        mibo = _option(db, kind="put", strike="34000", multiplier=Decimal("2.5"), underlying="FTSEMIB.MI")
        mibo.settlement = "cash"
        _bought(db, app, mibo, price="300")
        with pytest.raises(ValueError, match="prezzo del sottostante"):
            options.settle(mibo, "cash", EXPIRY)
        (trade,) = options.settle(mibo, "cash", EXPIRY, Decimal(33000))
        assert trade.amount == Decimal("2500.00") and mibo.quantity == 0
        # a call bought and in the money, exercised: 100 shares bought at the strike
        apple = _option(db, strike="200")
        _bought(db, app, apple)
        created = options.settle(apple, "exercise", EXPIRY, Decimal(215))
        stock = Holding.query.filter_by(ticker="AAPL", option_kind=None).one()
        assert apple.quantity == 0 and stock.quantity == 100 and stock.avg_price == Decimal(200)
        assert len(created) == 2
        # a put written and in the money, assigned: 100 more shares bought at its strike
        put = _option(db, kind="put", strike="190")
        _bought(db, app, put, units="-1", price="3")
        options.settle(put, "exercise", EXPIRY, Decimal(180))
        assert put.quantity == 0 and stock.quantity == 200 and stock.avg_price == Decimal(195)
        # a call written and in the money, assigned: the shares sold at the strike
        written = _option(db, strike="210")
        _bought(db, app, written, units="-1", price="4")
        options.settle(written, "exercise", EXPIRY, Decimal(220))
        assert written.quantity == 0 and stock.quantity == 100
        with pytest.raises(ValueError, match="non è più aperta"):
            options.settle(written, "worthless", EXPIRY)
        with pytest.raises(ValueError, match="come si è chiusa"):
            options.settle(written, "swap", EXPIRY)
        no_underlying = _option(db, underlying=None)
        no_underlying.underlying = None
        _bought(db, app, no_underlying)
        with pytest.raises(ValueError, match="sottostante"):
            options.settle(no_underlying, "exercise", EXPIRY, Decimal(215))


def test_the_strike_in_dollars_is_turned_into_euro(app, db, store):
    from app.models.currency import ExchangeRate
    db.session.add(ExchangeRate(currency="USD", on=date(2026, 12, 1), rate=Decimal("0.9"), source="ecb"))
    db.session.commit()
    with app.test_request_context():
        call = _option(db, strike="200")
        call.currency = "USD"
        _bought(db, app, call)
        options.settle(call, "exercise", EXPIRY, Decimal(215))
        stock = Holding.query.filter_by(ticker="AAPL", option_kind=None).one()
        assert stock.avg_price == Decimal(180) and stock.currency == "USD"  # 200 $ at 0,9


def test_the_reminder_and_the_page(client, app, db, store):
    from app.services import deadlines
    with app.test_request_context():
        put = _option(db, kind="put", strike="180")
        _bought(db, app, put, units="-2", price="1.5")
        (item,) = deadlines._options(date(2026, 12, 1), date(2026, 12, 31))
        assert item.title == "Scade l'opzione AAPL put 180 · 18/12/2026" and "Venduta: 2 contratti" in item.detail
        assert item.icon == "hourglass-split"
        call = _option(db, strike="300")
        _bought(db, app, call)
        assert len(deadlines._options(date(2026, 12, 1), date(2026, 12, 31))) == 2
    assert "arrivata a scadenza" not in client.get(f"/portfolio/{put.id}").get_data(as_text=True)  # not yet
    put = db.session.get(Holding, put.id)
    put.option_expiry = date.today() - timedelta(days=1)
    db.session.commit()
    page = client.get(f"/portfolio/{put.id}").get_data(as_text=True)
    assert "arrivata a scadenza" in page and 'value="worthless" checked' in page  # no underlying price: worthless
    bad = client.post(f"/portfolio/{put.id}/scadenza", data={"outcome": "cash"}, follow_redirects=True).get_data(as_text=True)
    assert "prezzo del sottostante" in bad
    done = client.post(f"/portfolio/{put.id}/scadenza", data={"outcome": "worthless"}, follow_redirects=True).get_data(as_text=True)
    assert "chiusa: scaduta senza valore" in done and db.session.get(Holding, put.id).quantity == 0


# ── US chains through yfinance (F120.3) ────────────────────────────────────────

class _Frame:
    def __init__(self, rows):
        self.rows = rows
        self.columns = list(rows[0]) if rows else []
        self.index = list(range(len(rows)))
        self.empty = not rows

    def __getitem__(self, column):
        return [r.get(column) for r in self.rows]


class _Chains:
    """A fake yfinance: AAPL with two expiries, its chain of the first."""

    def __init__(self):
        outer = self

        class Ticker:
            def __init__(self, symbol):
                self.options = ("2026-12-18", "2027-01-15") if symbol == "AAPL" else ()

            def option_chain(self, expiry):
                outer.asked = expiry
                calls = _Frame([{"contractSymbol": "AAPL261218C00210000", "strike": 210.0, "lastPrice": 6.2, "bid": 6.1,
                                 "ask": 6.4, "impliedVolatility": 0.25, "openInterest": 100, "volume": 5,
                                 "inTheMoney": True, "contractSize": "REGULAR"},
                                {"contractSymbol": "AAPL261218C00200000", "strike": 200.0, "lastPrice": float("nan"),
                                 "bid": None, "ask": None, "impliedVolatility": 0.3, "openInterest": 1, "volume": 0,
                                 "inTheMoney": True, "contractSize": "REGULAR"},
                                {"contractSymbol": None, "strike": 190.0}])
                puts = _Frame([{"contractSymbol": "AAPL261218P00210000", "strike": 210.0, "lastPrice": 3.0, "bid": 2.9,
                                "ask": 3.1, "impliedVolatility": 0.27, "openInterest": 50, "volume": 2,
                                "inTheMoney": False, "contractSize": "MINI"}])
                return type("Chain", (), {"calls": calls, "puts": puts,
                                          "underlying": {"regularMarketPrice": 214.5, "currency": "USD"}})()
        self.Ticker = Ticker


def test_the_chain_reader(app):
    from app.services import option_chains
    library = _Chains()
    assert option_chains.expiries("aapl", library) == [date(2026, 12, 18), date(2027, 1, 15)]
    assert option_chains.expiries("ENEL", library) == []
    found = option_chains.chain("aapl", EXPIRY, library)
    assert (found["underlying"], found["expiry"], found["price"], found["currency"]) == ("AAPL", "2026-12-18", 214.5, "USD")
    assert [r["strike"] for r in found["calls"]] == [200.0, 210.0] and found["calls"][0]["last"] is None
    assert found["calls"][1] == {"symbol": "AAPL261218C00210000", "strike": 210.0, "last": 6.2, "bid": 6.1, "ask": 6.4,
                                 "iv": 0.25, "open_interest": 100.0, "volume": 5.0, "itm": True, "multiplier": 100}
    assert found["puts"][0]["multiplier"] == 1 and library.asked == "2026-12-18"
    empty = type("L", (), {"Ticker": lambda self, s: type("T", (), {"option_chain": lambda self, e: type("C", (), {
        "calls": None, "puts": _Frame([]), "underlying": None})()})()})()
    assert option_chains.chain("AAPL", EXPIRY, empty) == {"underlying": "AAPL", "expiry": "2026-12-18", "price": None,
                                                         "currency": "USD", "calls": [], "puts": []}
    with app.app_context():
        with pytest.raises(ValueError, match="spento"):
            option_chains.expiries("AAPL")  # the tests: yfinance off
        app.config["YFINANCE"] = True
        try:
            from app.services import yf_source
            real = yf_source.available
            yf_source.available = lambda: False
            with pytest.raises(ValueError, match="non installato"):
                option_chains.expiries("AAPL")
            yf_source.available = real
            if real():
                assert hasattr(option_chains._library(), "Ticker")
        finally:
            app.config["YFINANCE"] = False


def test_the_chain_route(client, monkeypatch):
    from app.services import option_chains, settings_store
    assert client.get("/portfolio/opzioni/catena?u=AAPL").status_code == 403  # internet off
    settings_store.set_json("ui.settings", {"prices_online": True})
    monkeypatch.setattr(option_chains, "_library", lambda library=None: library or _Chains())
    assert client.get("/portfolio/opzioni/catena?u=AAPL").get_json() == {"underlying": "AAPL",
                                                                        "expiries": ["2026-12-18", "2027-01-15"]}
    chain = client.get("/portfolio/opzioni/catena?u=aapl&e=2026-12-18").get_json()
    assert chain["price"] == 214.5 and len(chain["calls"]) == 2
    assert "solo per le opzioni USA" in client.get("/portfolio/opzioni/catena?u=ENEL.MI").get_json()["error"]
    assert client.get("/portfolio/opzioni/catena?u=MSFT").status_code == 404  # no options listed
    monkeypatch.setattr(option_chains, "_library", lambda library=None: (_ for _ in ()).throw(OSError("down")))
    answer = client.get("/portfolio/opzioni/catena?u=AAPL")
    assert answer.status_code == 502 and "down" in answer.get_json()["error"]
    form = client.get("/portfolio/new").get_data(as_text=True)
    assert "Scegli dalla catena (USA)" in form and 'id="chain-table"' in form


# ── Taxes (F120.4): redditi diversi, with the multiplier; a written option realized when bought back ──

def test_capital_gains_of_options(app, db, store):
    from app.services import capital_gains
    with app.test_request_context():
        cash = Account(name="Broker", currency="EUR")
        db.session.add(cash)
        db.session.commit()
        # bought at 2,50 and sold at 4: (4 − 2,50) × 2 × 100 − commissions
        call = _option(db)
        portfolio_ops.record(call, portfolio_ops.Operation("buy", date(2026, 3, 2), cash, units=Decimal(2),
                                                           price=Decimal("2.50"), fee=Decimal(2)))
        portfolio_ops.record(call, portfolio_ops.Operation("sell", date(2026, 3, 9), cash, units=Decimal(2),
                                                           price=Decimal(4), fee=Decimal(2)))
        # written at 1,20 (3 contracts), bought back at 0,40 for one, the rest expires worthless
        put = _option(db, kind="put", strike="180")
        portfolio_ops.record(put, portfolio_ops.Operation("sell", date(2026, 4, 1), cash, units=Decimal(3),
                                                          price=Decimal("1.20"), fee=Decimal(3)))
        portfolio_ops.record(put, portfolio_ops.Operation("buy", date(2026, 4, 10), cash, units=Decimal(1),
                                                          price=Decimal("0.40"), fee=Decimal(1)))
        db.session.commit()
        options.settle(put, "worthless", date(2026, 4, 17))
        db.session.commit()
        # a call bought that expires worthless: its whole cost is a loss
        lost = _option(db, strike="400")
        portfolio_ops.record(lost, portfolio_ops.Operation("buy", date(2026, 5, 4), cash, units=Decimal(1),
                                                           price=Decimal("1.10")))
        db.session.commit()
        options.settle(lost, "worthless", date(2026, 5, 15))
        db.session.commit()
        summary = capital_gains.year_summary(2026)
    sales = summary["sales"]
    by = [(s.on, s.units, s.proceeds, s.cost, s.kind) for s in sales]
    assert by[0] == (date(2026, 3, 9), Decimal(2), Decimal("798.00"), Decimal("502.00"), "diversi")
    # the written put: 360 cashed in less 3 of commission = 357 for 3 contracts, 119 each
    assert by[1] == (date(2026, 4, 10), Decimal(1), Decimal("119.00"), Decimal("41.00"), "diversi")
    assert by[2] == (date(2026, 4, 17), Decimal(2), Decimal("238.00"), Decimal("0.00"), "diversi")
    assert by[3] == (date(2026, 5, 15), Decimal(1), Decimal("0"), Decimal("110.00"), "diversi")
    assert sales[3].result == Decimal("-110.00")
    assert sum(s.result for s in sales) == Decimal("296.00") + Decimal("78.00") + Decimal("238.00") - Decimal("110.00")
    assert not any(s.oversold for s in sales)


def test_a_written_option_opened_before_the_records(app, db, store):
    from app.services import capital_gains
    with app.test_request_context():
        cash = Account(name="Broker", currency="EUR")
        db.session.add(cash)
        db.session.commit()
        written = _option(db, kind="call", strike="250", quantity=-1, price="3")  # written before, at 3
        portfolio_ops.record(written, portfolio_ops.Operation("buy", date(2026, 6, 1), cash, units=Decimal(1),
                                                              price=Decimal(1)))
        db.session.commit()
        (sale,) = capital_gains.year_summary(2026)["sales"]
    assert (sale.proceeds, sale.cost, sale.result, sale.estimated) == (Decimal("300.00"), Decimal("100.00"),
                                                                      Decimal("200.00"), True)


# ── Options in a broker's statement (F120.4) ───────────────────────────────────

@pytest.mark.parametrize("text, terms", [
    ("AAPL  261218C00200000", ("AAPL", "call", "200", date(2026, 12, 18), "100")),
    ("AAPL 18DEC26 200 C", ("AAPL", "call", "200", date(2026, 12, 18), "100")),
    ("AAPL C200.00 18DEC26", ("AAPL", "call", "200.00", date(2026, 12, 18), "100")),
    ("CALL ENEL 6,5 DIC26", ("ENEL", "call", "6.5", date(2026, 12, 18), "100")),  # only the month: its third Friday
    ("MIBO 34000 P 19/12/2026", ("FTSEMIB.MI", "put", "34000", date(2026, 12, 19), "2.5")),
    ("Opz. Put FTSE MIB 34000 Dic 2026", ("FTSEMIB.MI", "put", "34000", date(2026, 12, 18), "2.5")),
    ("OESX DEC26 5000 C", ("^STOXX50E", "call", "5000", date(2026, 12, 18), "10")),
    ("Vanguard FTSE All-World", None), ("BTP 1AG31 0,6%", None), ("ENEL", None), ("Put C 2026", None),
    ("CALL ENEL 31/02/2026 6", None), (None, None), ("CALL ENEL DIC26", None),
])
def test_options_read_from_a_statement(text, terms):
    found = options.from_description(text)
    if terms is None:
        assert found is None
    else:
        assert (found["underlying"], found["option_kind"], str(found["strike"]), found["option_expiry"],
                str(found["multiplier"])) == terms


def test_third_friday():
    assert [options.third_friday(2026, m) for m in (1, 5, 12)] == [date(2026, 1, 16), date(2026, 5, 15), date(2026, 12, 18)]


def test_a_statement_with_options(client, db):
    import io
    import re

    from tests.form_helper import form_data
    csv = ("Data operazione;Segno;Titolo;ISIN;Ticker;Quantità;Prezzo;Controvalore;Commissioni\n"
           "02/11/2026;A;AAPL 18DEC26 200 C;;;2;2,50;500;2\n"
           "03/11/2026;V;MIBO 34000 P 19/12/2026;;;1;300;750;5\n"
           "10/11/2026;A;MIBO 34000 P 19/12/2026;;;1;100;250;5\n").encode()
    from app.services import broker_import
    with client.application.test_request_context():
        preview = broker_import.read("broker.csv", csv)
    assert [(r.units, r.price) for r in preview.rows] == [(Decimal(2), Decimal("2.50")), (Decimal(-1), Decimal(300)),
                                                         (Decimal(1), Decimal(100))]  # the value ÷ the multiplier
    html = client.post("/portfolio/import", data={"file": (io.BytesIO(csv), "broker.csv")},
                       content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    data = form_data(html, "broker-form", include=re.findall(r'name="include" value="(\d+)"', html))
    page = client.post("/portfolio/import/confirm", data=data, follow_redirects=True).get_data(as_text=True)
    assert "3 operazioni importate." in page
    call = Holding.query.filter_by(name="AAPL 18DEC26 200 C").one()
    assert (call.asset_class, call.option_kind, call.strike, call.ticker, call.multiplier, call.quantity) == (
        "Derivato", "call", Decimal(200), "AAPL261218C00200000", Decimal(100), Decimal(2))
    mibo = Holding.query.filter_by(name="MIBO 34000 P 19/12/2026").one()
    assert (mibo.underlying, mibo.multiplier, mibo.ticker, mibo.quantity) == ("FTSEMIB.MI", Decimal("2.5"), None, Decimal(0))
    amounts = sorted(t.amount for t in Transaction.query.filter(Transaction.units.isnot(None)))
    assert amounts == [Decimal("250.00"), Decimal("500.00"), Decimal("750.00")]  # the money: × the multiplier
