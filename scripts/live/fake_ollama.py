"""
Fake Ollama for the live run, on 127.0.0.1:11434: model list, download with progress, removal, reading of the
statement photo and classification by keywords. No model involved, same answers every time.
"""

import json
import sys
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "samples" / "bank_statements"))
import generate as g  # noqa: E402  (the sample generator: the photo shows these movements)

INSTALLED = {"qwen2.5vl:7b": 6.0e9, "qwen3:1.7b": 1.4e9, "llama3.2:1b": 1.3e9}
RULES = [
    (("esselunga", "conad", "lidl", "carrefour"), "Alimentari", "alta"),
    (("netflix", "spotify", "iliad"), "Abbonamenti", "alta"),
    (("stipendio",), "Stipendio", "alta"),
    (("uber", "trenitalia", "eni station", "q8", "ryanair", "telepass", "atm milano"), "Trasporto", "alta"),
    (
        ("starbucks", "bar centrale", "ristorante", "pizzeria", "deliveroo", "just eat", "cinema", "booking"),
        "Svago",
        "media",
    ),
    (("affitto", "enel", "a2a"), "Casa", "alta"),
    (("farmacia",), "Salute", "alta"),
    (("commissioni",), "Commissioni", "alta"),
    (("amazon", "decathlon", "feltrinelli"), "Altro", "media"),
]
NAMES = {
    "esselunga": "Esselunga",
    "conad": "Conad",
    "lidl": "Lidl",
    "carrefour": "Carrefour",
    "netflix": "Netflix",
    "spotify": "Spotify",
    "iliad": "Iliad",
    "stipendio": "ACME SPA",
    "uber": "Uber",
    "trenitalia": "Trenitalia",
    "eni station": "Eni",
    "q8": "Q8",
    "ryanair": "Ryanair",
    "telepass": "Telepass",
    "atm milano": "ATM Milano",
    "starbucks": "Starbucks",
    "bar centrale": "Bar Centrale",
    "ristorante": "Ristorante Da Luigi",
    "pizzeria": "Pizzeria Napoli",
    "deliveroo": "Deliveroo",
    "just eat": "Just Eat",
    "cinema": "Cinema Anteo",
    "booking": "Booking.com",
    "affitto": "Immobiliare Casa Bella",
    "enel": "Enel Energia",
    "a2a": "A2A",
    "farmacia": "Farmacia Comunale",
    "commissioni": "",
    "amazon": "Amazon",
    "decathlon": "Decathlon",
    "feltrinelli": "Feltrinelli",
}


intesa = g.movements(date(2026, 9, 1), date(2026, 9, 24), 88, salary=2180.0, rent=720.0)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _json(self, obj):
        out = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        if self.path == "/api/version":
            return self._json({"version": "0.9.0"})
        if self.path == "/api/tags":
            return self._json({"models": [{"name": n, "size": s} for n, s in INSTALLED.items()]})

    def do_DELETE(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        INSTALLED.pop(body["model"], None)
        self._json({})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/pull":
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            def chunk(obj):
                data = (json.dumps(obj) + "\n").encode()
                self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
                self.wfile.flush()

            chunk({"status": "pulling manifest"})
            for done in range(0, 101, 5):
                chunk({"status": "downloading", "total": 3_300_000_000, "completed": done * 33_000_000})
                time.sleep(0.4)
            chunk({"status": "success"})
            self.wfile.write(b"0\r\n\r\n")
            INSTALLED[body["model"]] = 3.3e9
            return
        if "items" in body["format"].get("properties", {}):  # classification request
            movements = json.loads(body["messages"][1]["content"].split("movimenti:\n", 1)[1])
            categories = body["format"]["properties"]["items"]["items"]["properties"]["category"]["enum"]
            items = []
            for m in movements:
                text = m["causale"].lower()
                hit = next(
                    ((k, cat, conf) for keys, cat, conf in RULES for k in keys if k in text and cat in categories), None
                )
                items.append(
                    {
                        "id": m["id"],
                        "category": hit[1] if hit else "Altro",
                        "counterparty": NAMES.get(hit[0], "") if hit else "",
                        "confidence": hit[2] if hit else "bassa",
                    }
                )
            return self._json(
                {"model": body["model"], "message": {"role": "assistant", "content": json.dumps({"items": items})}}
            )
        # /api/chat: the photo of the Intesa statement; the "model" skips row 6 on purpose
        rows = [
            {"date": m["date"].isoformat(), "description": m["full"], "details": m["short"], "amount": m["amount"]}
            for m in intesa
        ]
        rows.pop(6)
        reply = {
            "bank_name": "Intesa Sanpaolo",
            "has_balances": True,
            "opening_balance": 1500.0,
            "closing_balance": round(1500 + sum(m["amount"] for m in intesa), 2),
            "movements": rows,
        }
        self._json({"model": body["model"], "message": {"role": "assistant", "content": json.dumps(reply)}})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 11434), H).serve_forever()
