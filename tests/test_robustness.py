"""Improper use of the forms and uploads: wrong files, characters the database refuses, requests from other sites.
The app must answer with a message, never an error 500, and save nothing broken."""
import io

from app.models.transaction import Transaction
from app.models.wealth import Goal
from app.services import statement_readers, transfer


def test_unreadable_csv_is_a_message_not_a_crash(client):
    for name, raw in {"binary.csv": bytes(range(256)) * 400,
                      "huge.csv": b"Data;Descrizione;Importo\n01/01/2026;" + b"A" * 300_000 + b";-5\n"}.items():
        r = client.post("/export/import/columns", data={"file": (io.BytesIO(raw), name)}, content_type="multipart/form-data")
        assert r.status_code == 400 and "CSV leggibile" in r.get_json()["error"]


def test_statement_reader_with_a_giant_cell():
    text = "riga di titolo\n" + "a;b;c\n" * 3 + "x;" + "A" * 300_000 + ";y\n"
    document = statement_readers.text_document("csv", text)
    assert document.text_lines  # read as plain lines, no exception


def test_csv_cells_still_reads_good_files():
    assert transfer.csv_cells("a;b;c\n1;2;3\n") == [["a", "b", "c"], ["1", "2", "3"]]


def test_nul_characters_in_a_form_are_refused(client, db):
    r = client.post("/lifestyle/goals/new", data={"name": "Casa\x00", "target_amount": "100"})
    assert r.status_code == 400 and "caratteri non validi" in r.get_data(as_text=True)
    assert Goal.query.count() == 0
    assert client.get("/transactions/?q=a\x00b").status_code == 400
    assert client.post("/transactions/", data={"next": "\x00"}).status_code == 405  # no such form: not a crash


def test_nul_characters_from_a_file_are_dropped_on_save(app, db):
    db.session.add(Transaction(date=__import__("datetime").date(2026, 1, 1), description="Bar\x00 Centrale",
                               amount=-2, type="expense"))
    db.session.commit()
    assert Transaction.query.one().description == "Bar Centrale"


def test_requests_from_another_site_are_refused(client, db):
    data = {"name": "Vacanze", "target_amount": "500"}
    for headers in ({"Origin": "https://evil.example"}, {"Origin": "null"},
                    {"Referer": "https://evil.example/page"}, {"Sec-Fetch-Site": "cross-site"}):
        r = client.post("/lifestyle/goals/new", data=data, headers=headers)
        assert r.status_code == 403 and "altro sito" in r.get_data(as_text=True)
    r = client.post("/transactions/api", json={"amount": 1}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and "altro sito" in r.get_json()["message"]
    assert Goal.query.count() == 0
    # the app's own pages (same origin), and tools that send no origin at all, still work
    client.post("/lifestyle/goals/new", data=data, headers={"Origin": "http://localhost", "Sec-Fetch-Site": "same-origin"})
    client.post("/lifestyle/goals/new", data=data)
    assert Goal.query.count() == 2
    assert client.get("/dashboard", headers={"Origin": "https://evil.example"}).status_code == 200
