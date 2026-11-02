"""
Read-only access for an AI assistant on this computer (F22): a small MCP server (Model Context Protocol, JSON-RPC 2.0
over stdin/stdout, one message per line) that Claude Desktop or another MCP client starts with `flask mcp serve` (or
`MyFinancePlace --mcp` from the desktop app), so the assistant can read balances, spending, investments, debts, goals
and the consolidated view of a group to answer questions.

Nothing can be changed: there is no tool that writes, and every call runs in a READ ONLY database transaction that
is rolled back at the end. The data never leaves the computer except through the client the user connected.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import event, or_
from sqlalchemy.engine import Engine

from app.extensions import db
from app.models.client import Client, ClientGroup
from app.models.transaction import Transaction
from app.models.wealth import Debt, Goal
from app.services import assistant, consolidation, studio, wealth
from app.services.parsing import to_date
from app.services.spending_rhythm import by_category

PROTOCOL = "2025-06-18"
MAX_MOVEMENTS = 200
INSTRUCTIONS = ("Dati finanziari personali di una famiglia italiana (importi in euro, sola lettura). "
                "Usa «riepilogo» per una visione d'insieme, poi gli altri strumenti per i dettagli.")


def _period(args: dict, days: int = 30) -> tuple[date, date]:
    end = to_date(args.get("a")) or date.today()
    start = to_date(args.get("da")) or end - timedelta(days=days)
    return start, end


def _summary(args: dict) -> dict:
    return assistant.facts()


def _spending(args: dict) -> dict:
    start, end = _period(args)
    rows = sorted(by_category(start, end).items(), key=lambda kv: -kv[1])
    return {"da": start, "a": end, "per_categoria": dict(rows), "totale": sum((v for _, v in rows), Decimal(0))}


def _movements(args: dict) -> dict:
    start, end = _period(args, days=90)
    query = Transaction.query.filter(Transaction.date >= start, Transaction.date <= end)
    if args.get("categoria"):
        query = query.filter(Transaction.category == args["categoria"])
    if args.get("testo"):
        like = f"%{args['testo']}%"
        query = query.filter(or_(Transaction.description.ilike(like), Transaction.counterparty.ilike(like)))
    limit = max(1, min(int(args.get("limite") or 50), MAX_MOVEMENTS))
    rows = query.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(limit).all()
    return {"movimenti": [{"data": tx.date, "descrizione": tx.description, "tipo": tx.type, "categoria": tx.category,
                           "importo": tx.amount_base if tx.amount_base is not None else tx.amount,
                           "conto": tx.account.name if tx.account else None} for tx in rows],
            "mostrati": len(rows), "limite": limit}


def _balance_sheet(args: dict) -> dict:
    sheet = wealth.balance_sheet(to_date(args.get("data")))
    return {k: v for k, v in sheet.items() if k != "debts"} | {"debiti": sheet["debts"]}


def _investments(args: dict) -> dict:
    return {"titoli": [{"nome": h.name, "isin": h.isin, "ticker": h.ticker, "classe": h.asset_class,
                        "quote": h.units, "prezzo": h.price, "valore": round(h.value, 2), "costo": round(h.cost, 2),
                        "guadagno_pct": round(h.gain_pct, 1), "intestatario": h.owner} for h in wealth.holdings_on()]}


def _debts(args: dict) -> dict:
    return {"debiti": [{"nome": d.name, "tipo": d.type, "tasso": d.annual_rate,
                        **{k: v for k, v in wealth.debt_summary(d).items() if isinstance(v, (int, float, str))}}
                       for d in Debt.query.order_by(Debt.name)]}


def _goals(args: dict) -> dict:
    return {"obiettivi": [{"nome": g.name, "obiettivo": g.target_amount, "risparmiato": g.saved_amount,
                           "entro": g.target_date, "percentuale": round(g.progress, 1)} for g in Goal.query.order_by(Goal.name)]}


def _archives(args: dict) -> dict:
    clients = Client.query.order_by(Client.database.isnot(None), Client.name).all()  # read only: no primary made here
    rows = [{"nome": c.name, "slug": c.slug, "principale": c.is_primary} for c in clients]
    if not any(row["principale"] for row in rows):
        rows.insert(0, {"nome": "Archivio principale", "slug": None, "principale": True})
    return {"archivi": rows,
            "gruppi": [{"nome": g.name, "archivi": [c.name for c in g.members]} for g in ClientGroup.query.order_by(ClientGroup.name)]}


def _group(args: dict) -> dict:
    group = ClientGroup.query.filter(db.func.lower(ClientGroup.name) == str(args.get("gruppo") or "").lower()).first()
    if group is None:
        raise ValueError("Gruppo non trovato: usa «archivi» per l'elenco.")
    data = consolidation.consolidate(group)
    keys = ("currency", "net_worth", "cash", "investments", "other_assets", "liabilities", "income_12", "expenses_12",
            "passive_12", "internal_total", "spending", "debts", "goals")
    return {k: data[k] for k in keys} | {
        "per_archivio": [{"archivio": m.client.name, "sommato": m.included, "patrimonio_netto": m.net_worth,
                          "entrate_12": m.income_12, "uscite_12": m.expenses_12} for m in data["members"]],
        "investimenti": [{k: h[k] for k in ("name", "isin", "units", "value", "gain_pct", "members")} for h in data["holdings"]]}


PERIOD = {"da": {"type": "string", "description": "data iniziale AAAA-MM-GG"},
          "a": {"type": "string", "description": "data finale AAAA-MM-GG (predefinita: oggi)"}}
TOOLS = {
    "riepilogo": ("Riassunto dell'archivio: patrimonio, conti, entrate e uscite degli ultimi 12 mesi, spese per "
                  "categoria, investimenti, debiti, obiettivi, eventi, rendite, problemi nei dati.", {}, _summary),
    "spese_per_categoria": ("Spese per categoria in un periodo (predefinito: ultimi 30 giorni).", PERIOD, _spending),
    "movimenti": ("Singoli movimenti di un periodo (predefinito: ultimi 90 giorni), filtrabili per categoria o testo.",
                  PERIOD | {"categoria": {"type": "string"}, "testo": {"type": "string"},
                            "limite": {"type": "integer", "description": f"al massimo {MAX_MOVEMENTS}"}}, _movements),
    "patrimonio": ("Stato patrimoniale a una data (predefinita: oggi).",
                   {"data": {"type": "string", "description": "AAAA-MM-GG"}}, _balance_sheet),
    "investimenti": ("Titoli e beni posseduti con valore, costo e guadagno.", {}, _investments),
    "debiti": ("Mutui e prestiti con il residuo.", {}, _debts),
    "obiettivi": ("Obiettivi di risparmio e a che punto sono.", {}, _goals),
    "archivi": ("Gli archivi (persone o famiglie) e i gruppi.", {}, _archives),
    "consolidato_gruppo": ("Il consolidato di un gruppo di archivi (famiglia).",
                           {"gruppo": {"type": "string", "description": "nome del gruppo"}}, _group),
}


def tool_list() -> list[dict]:
    return [{"name": name, "description": description,
             "inputSchema": {"type": "object", "properties": properties, "additionalProperties": False}}
            for name, (description, properties, _) in TOOLS.items()]


def _json(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _read_only(connection) -> None:
    connection.exec_driver_sql("SET TRANSACTION READ ONLY")


def call(app, client: Client | None, name: str, arguments: dict | None) -> dict:
    """One tool, read only, in the chosen archive; the answer as MCP content."""
    if name not in TOOLS:
        return {"content": [{"type": "text", "text": f"Strumento sconosciuto: {name}"}], "isError": True}
    with app.test_request_context():
        db.session.rollback()  # every transaction of the call starts read only, in any archive it reads
        event.listen(Engine, "begin", _read_only)
        try:
            studio.activate(client)
            result = TOOLS[name][2](arguments or {})
            body, error = json.dumps(result, ensure_ascii=False, default=_json), False
        except Exception as exc:  # noqa: BLE001 - the assistant gets the message, the server goes on
            body, error = f"Errore: {exc}", True
        finally:
            db.session.rollback()
            event.remove(Engine, "begin", _read_only)
    return {"content": [{"type": "text", "text": body}], "isError": error}


def handle(app, client: Client | None, message: dict) -> dict | None:
    """The answer to one JSON-RPC message (None for a notification)."""
    method, ident = message.get("method"), message.get("id")
    if ident is None:
        return None  # notifications/initialized and the like
    if method == "initialize":
        version = (message.get("params") or {}).get("protocolVersion") or PROTOCOL
        result = {"protocolVersion": version, "capabilities": {"tools": {}},
                  "serverInfo": {"name": "myfinanceplace", "version": "1.0"}, "instructions": INSTRUCTIONS}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": tool_list()}
    elif method == "tools/call":
        params = message.get("params") or {}
        result = call(app, client, params.get("name", ""), params.get("arguments"))
    else:
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": f"Metodo sconosciuto: {method}"}}
    return {"jsonrpc": "2.0", "id": ident, "result": result}


def serve(app, client: Client | None = None, stdin=None, stdout=None) -> None:
    """Answer the messages on stdin until it closes."""
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON non valido"}}
        else:
            reply = handle(app, client, message) if isinstance(message, dict) else \
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Richiesta non valida"}}
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            stdout.flush()


def find_client(slug: str | None) -> Client | None:
    if not slug:
        return None
    client = Client.query.filter_by(slug=slug).first()
    if client is None:
        raise ValueError(f"Nessun archivio «{slug}»: vedi `flask clients list`.")
    return client
