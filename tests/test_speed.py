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
