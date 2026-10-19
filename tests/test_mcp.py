"""F22: read-only access for an AI assistant (MCP over stdin/stdout)."""
import io
import json
from datetime import date

import pytest

from app.extensions import db as _db
from app.models.account import Account
from app.models.client import Client, ClientGroup
from app.models.transaction import Transaction
from app.models.wealth import Debt, Goal, Holding
from app.services import mcp_server
from tests.conftest import make_tx


@pytest.fixture()
def book(db):
    bank = Account(name="Banca")
    db.session.add(bank)
    db.session.flush()
    today = date.today()
    db.session.add_all([
        make_tx(date=today, description="Spesa Esselunga", amount=80, category="Spesa", account_id=bank.id),
        make_tx(date=today, description="Stipendio", amount=2500, type="income", category="Stipendio", account_id=bank.id),
        Holding(name="VWCE", isin="IE00BK5BQT80", asset_class="ETF", quantity=10, avg_price=100, current_price=120),
        Debt(name="Mutuo", type="Mutuo", principal=100000, balance=80000),
        Goal(name="Vacanze", target_amount=2000, saved_amount=500),
    ])
    db.session.commit()


def _call(app, name, arguments=None):
    reply = mcp_server.handle(app, None, {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                                          "params": {"name": name, "arguments": arguments or {}}})
    result = reply["result"]
    return result["isError"], result["content"][0]["text"]


def test_protocol(app, db):
    init = mcp_server.handle(app, None, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                         "params": {"protocolVersion": "2025-03-26"}})
    assert init["result"]["protocolVersion"] == "2025-03-26" and init["result"]["capabilities"] == {"tools": {}}
    assert mcp_server.handle(app, None, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert mcp_server.handle(app, None, {"jsonrpc": "2.0", "id": 2, "method": "ping"})["result"] == {}
    tools = mcp_server.handle(app, None, {"jsonrpc": "2.0", "id": 3, "method": "tools/list"})["result"]["tools"]
    assert {t["name"] for t in tools} == set(mcp_server.TOOLS) and all(t["inputSchema"]["type"] == "object" for t in tools)
    assert mcp_server.handle(app, None, {"jsonrpc": "2.0", "id": 4, "method": "resources/list"})["error"]["code"] == -32601
    assert _call(app, "cancella_tutto") == (True, "Strumento sconosciuto: cancella_tutto")


def test_tools(app, book):
    error, body = _call(app, "riepilogo")
    assert not error and json.loads(body)["patrimonio"]["netto"] is not None
    assert json.loads(_call(app, "spese_per_categoria")[1])["per_categoria"] == {"Spesa": 80.0}
    moves = json.loads(_call(app, "movimenti", {"testo": "esselunga", "limite": 999})[1])
    assert moves["limite"] == 200 and [m["descrizione"] for m in moves["movimenti"]] == ["Spesa Esselunga"]
    assert json.loads(_call(app, "movimenti", {"categoria": "Stipendio"})[1])["movimenti"][0]["conto"] == "Banca"
    assert "net_worth" in json.loads(_call(app, "patrimonio", {"data": date.today().isoformat()})[1])
    assert json.loads(_call(app, "investimenti")[1])["titoli"][0]["valore"] == 1200
    assert json.loads(_call(app, "debiti")[1])["debiti"][0]["nome"] == "Mutuo"
    assert json.loads(_call(app, "obiettivi")[1])["obiettivi"][0]["percentuale"] == 25
    assert json.loads(_call(app, "archivi")[1])["archivi"][0]["principale"] is True
    error, body = _call(app, "consolidato_gruppo", {"gruppo": "nessuno"})
    assert error and "Gruppo non trovato" in body


def test_consolidated_group(app, book, monkeypatch):
    client = Client(name="Altro", slug="altro", database=None)
    _db.session.add(client)
    _db.session.flush()
    _db.session.add(ClientGroup(name="Famiglia", members=[client]))
    _db.session.commit()
    data = json.loads(_call(app, "consolidato_gruppo", {"gruppo": "famiglia"})[1])
    assert data["per_archivio"][0]["archivio"] == "Altro" and data["investimenti"][0]["isin"] == "IE00BK5BQT80"


def test_read_only(app, book, monkeypatch):
    def write(args):
        _db.session.add(make_tx(description="Intruso"))
        _db.session.flush()

    monkeypatch.setitem(mcp_server.TOOLS, "scrivi", ("", {}, write))
    error, body = _call(app, "scrivi")
    assert error and "read-only" in body
    assert Transaction.query.filter_by(description="Intruso").count() == 0


def test_serve_lines(app, book):
    stdin = io.StringIO("\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        "", "non json", "[1, 2]",
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "obiettivi"}}),
    ]) + "\n")
    stdout = io.StringIO()
    mcp_server.serve(app, None, stdin, stdout)
    replies = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert [r.get("id") for r in replies] == [1, None, None, 2]
    assert replies[0]["result"]["serverInfo"]["name"] == "myfinanceplace" and replies[0]["result"]["protocolVersion"]
    assert replies[1]["error"]["code"] == -32700 and replies[2]["error"]["code"] == -32600
    assert "Vacanze" in replies[3]["result"]["content"][0]["text"]


def test_cli_and_archive(app, book, monkeypatch):
    assert mcp_server.find_client(None) is None
    with pytest.raises(ValueError, match="Nessun archivio"):
        mcp_server.find_client("nessuno")
    runner = app.test_cli_runner()
    out = runner.invoke(args=["mcp", "serve"], input=json.dumps({"jsonrpc": "2.0", "id": 5, "method": "ping"}) + "\n")
    assert json.loads(out.output) == {"jsonrpc": "2.0", "id": 5, "result": {}}
    assert runner.invoke(args=["mcp", "serve", "--client", "nessuno"]).exit_code != 0


def test_desktop_flag(monkeypatch, tmp_path):
    from desktop import main

    args = main._arguments(["--mcp", "--client", "rossi"])
    assert args.mcp and args.client == "rossi"
    monkeypatch.setattr(main.paths, "postgres_bin", lambda: None)
    assert main.main(["--mcp", "--data-dir", str(tmp_path)]) == 2

    calls = []

    class FakeDatabase:
        def __init__(self, bin_dir, root):
            self.port = None

        def start(self):
            calls.append("start")
            raise main.DatabaseError("no")

        def stop(self):
            calls.append("stop")

    monkeypatch.setattr(main.paths, "postgres_bin", lambda: tmp_path)
    monkeypatch.setattr(main, "EmbeddedPostgres", FakeDatabase)
    assert main.main(["--mcp", "--data-dir", str(tmp_path)]) == 6 and calls == ["start", "stop"]
