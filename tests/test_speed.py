"""What keeps the pages quick: the API's list in a fixed number of queries, the studio counted once per request, the
answers compressed for a browser on another machine."""
import gzip

from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.models.transaction import TransactionSplit
from app.services import studio
from tests.conftest import make_tx


class Statements:
    """The SQL statements sent while the block runs."""

    def __enter__(self):
        self.sent = []
        event.listen(Engine, "before_cursor_execute", self._note)
        return self.sent

    def __exit__(self, *exc):
        event.remove(Engine, "before_cursor_execute", self._note)

    def _note(self, conn, cursor, statement, parameters, context, executemany):
        self.sent.append(statement)


def test_the_api_list_reads_the_splits_together(client, db):
    for index in range(12):
        tx = make_tx(description=f"Spesa {index}", amount=100)
        tx.splits = [TransactionSplit(category="Spesa", amount=70), TransactionSplit(category="Casa", amount=30)]
        db.session.add(tx)
    db.session.commit()
    db.session.remove()
    with Statements() as sent:
        answer = client.get("/transactions/api").get_json()
    assert answer["total"] == 12 and all(len(tx["splits"]) == 2 for tx in answer["transactions"])
    assert len([s for s in sent if "transaction_splits" in s]) == 1  # not one query per transaction


def test_the_studio_is_counted_once_per_request(app, db):
    with app.test_request_context():
        with Statements() as sent:
            assert studio.is_studio() is False and studio.is_studio() is False
        assert len([s for s in sent if "FROM clients" in s]) == 1


def test_a_page_is_compressed_only_for_a_browser_elsewhere(client, db):
    elsewhere = {"REMOTE_ADDR": "192.168.1.20"}
    plain = client.get("/settings/", headers={"Accept-Encoding": "gzip"})  # the desktop app: same machine
    assert "Content-Encoding" not in plain.headers
    packed = client.get("/settings/", headers={"Accept-Encoding": "gzip, br"}, environ_base=elsewhere)
    assert packed.headers["Content-Encoding"] == "gzip" and "Accept-Encoding" in packed.headers["Vary"]
    assert gzip.decompress(packed.get_data()) == plain.get_data() and len(packed.get_data()) < len(plain.get_data()) / 3
    assert "Content-Encoding" not in client.get("/settings/", environ_base=elsewhere).headers  # not asked for
    style = client.get("/static/css/main.css", headers={"Accept-Encoding": "gzip"}, environ_base=elsewhere)
    assert style.headers["Content-Encoding"] == "gzip" and b".topbar" in gzip.decompress(style.get_data())
    small = client.get("/health", headers={"Accept-Encoding": "gzip"}, environ_base=elsewhere)
    assert "Content-Encoding" not in small.headers  # a few bytes: left as they are


# ── What a request read is kept only until it writes (services.request_cache.data) ──

def _etf_with_prices(db):
    from datetime import date
    from decimal import Decimal

    from app.models.account import Account
    from app.models.wealth import Holding, HoldingPrice

    broker = Account(name="Directa", kind="other")
    etf = Holding(name="All-World", asset_class="ETF", quantity=10, avg_price=100, purchase_date=date(2024, 1, 2),
                  opening_quantity=10, opening_price=100, opening_date=date(2024, 1, 2), current_price=Decimal(130),
                  price_date=date(2025, 12, 31))
    db.session.add_all([broker, etf])
    db.session.commit()
    for month in range(24):
        on = date(2024 + month // 12, month % 12 + 1, 28)
        db.session.add(HoldingPrice(holding_id=etf.id, on=on, price=Decimal(100 + month)))
    db.session.commit()
    return broker, etf


def test_a_series_of_two_years_costs_a_handful_of_queries(app, db):
    from datetime import date

    from app.services import performance

    _broker, etf = _etf_with_prices(db)
    with app.test_request_context():
        with Statements() as sent:
            series = performance.value_series([etf], date(2025, 12, 31))
            dates, returns = performance.monthly_returns([etf], date(2025, 12, 31))
        assert len(series["labels"]) >= 24 and len(returns) >= 23
        assert series["value"][1] == 1000.0 and series["value"][2] == 1010.0  # 10 units at 100, then at 101
        assert len(sent) <= 8, sent  # not a handful per month-end: the prices and the trades are read once


def test_what_was_read_is_forgotten_at_a_write_and_at_a_rollback(app, db):
    from datetime import date
    from decimal import Decimal

    from app.services import holding_moves, portfolio_ops
    from app.services.net_worth_growth import units_after
    from app.services.portfolio_ops import Operation

    broker, etf = _etf_with_prices(db)
    with app.test_request_context():
        assert units_after(date(2025, 1, 1)) == {} and holding_moves.fees() == {}
        portfolio_ops.record(etf, Operation("buy", date(2025, 3, 10), broker, units=Decimal(5), price=Decimal(100),
                                            fee=Decimal(2)))
        db.session.commit()
        assert units_after(date(2025, 1, 1)) == {etf.id: 5.0}  # read again after the write
        (trade,) = holding_moves.trades()
        assert trade.signed == Decimal(500) and holding_moves.fees() == {trade.id: Decimal(2)}
        db.session.add(make_tx(type="transfer", amount=300, holding_id=etf.id, units=Decimal(-3), date=date(2025, 6, 1)))
        db.session.flush()
        assert units_after(date(2025, 1, 1)) == {etf.id: 2.0} and holding_moves.trades()[-1].signed == Decimal(-300)
        db.session.rollback()
        assert units_after(date(2025, 1, 1)) == {etf.id: 5.0}  # the sale that was undone is not remembered


def test_the_reminders_are_kept_between_pages_until_something_is_written(app, client, db):
    from datetime import date, timedelta
    from decimal import Decimal

    from app.models.wealth import InsurancePolicy

    def page():
        with Statements() as sent:
            html = client.get("/notifications/peek").get_data(as_text=True)
        return html, [s for s in sent if "insurance_policies" in s]

    html, asked = page()
    assert "Unipol" not in html and asked
    html, asked = page()
    assert not asked  # the second page did not work the reminders out again
    db.session.add(InsurancePolicy(type="Auto", company="Unipol", premium=Decimal(300),
                                   expiry_date=date.today() + timedelta(days=10)))
    db.session.commit()
    html, asked = page()
    assert "Unipol" in html and asked  # a write: worked out again, the new reminder is there at the next page
    app.config["NOTIFICATIONS_KEEP_SECONDS"] = 0
    assert page()[1] and page()[1]  # switched off: asked at every page
