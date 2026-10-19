"""Which column is what in a mapped import: from the values, corrected when the user picks wrong, AI on a sample."""
import io
import json
from pathlib import Path

import pytest

from app.services import ai_extraction, column_guess, transfer

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "bank_statements"


def _mapped(guess):
    return {k: v for k, v in guess.mapping.items() if v}


@pytest.mark.parametrize("filename, expected", [
    ("fineco_2026-06_2026-07.xlsx", {"date": "Data_Operazione", "debit": "Uscite", "credit": "Entrate", "description": "Descrizione"}),
    ("banca_generica_2026-02.xls", {"date": "Data operazione", "debit": "Dare", "credit": "Avere", "description": "Descrizione"}),
    ("intesa_sanpaolo_2026-04_2026-09.xlsx", {"date": "Data", "amount": "Importo", "description": "Dettagli", "category": "Categoria"}),
    ("unicredit_2026-08_2026-09.csv", {"date": "Data Registrazione", "amount": "Importo (EUR)", "description": "Descrizione"}),
    ("n26_2026-08.csv", {"date": "Booking Date", "amount": "Amount (EUR)", "description": "Partner Name"}),
    ("revolut_2026-09.csv", {"date": "Started Date", "amount": "Amount", "description": "Description"}),
])
def test_columns_are_recognised_from_the_values(app, filename, expected):
    headers, rows, _line = transfer.read_table(filename, (SAMPLES / filename).read_bytes())
    guessed = column_guess.guess(headers, rows)
    assert _mapped(guessed) == expected and guessed.sure


def test_untitled_columns_and_type_words(app):
    headers = ["A", "B", "C", "D", "E"]
    rows = [{"A": f"0{d}/06/2026", "B": "PAGAMENTO POS " + shop, "C": amount, "D": kind, "E": "x"}
            for d, shop, amount, kind in [(1, "COOP", "12,50", "uscita"), (2, "BAR", "3,20", "uscita"),
                                          (3, "ACME", "1500", "entrata"), (4, "LIDL", "40", "uscita")]]
    guessed = column_guess.guess(headers, rows)
    assert _mapped(guessed) == {"date": "A", "amount": "C", "description": "B", "type": "D"}


def test_csv_without_header_and_with_decimal_commas(app):
    raw = "01/09/2026;Pagamento POS ESSELUNGA MILANO;-45,20\n02/09/2026;Stipendio ACME;1800,00\n".encode()
    headers, rows, first_line = transfer.read_table("movimenti.csv", raw)
    assert headers == ["Colonna 1", "Colonna 2", "Colonna 3"] and first_line == 1  # no row taken as the header
    assert [r["Colonna 3"] for r in rows] == ["-45,20", "1800,00"]  # ";" splits, not the decimal comma
    assert _mapped(column_guess.guess(headers, rows)) == {"date": "Colonna 1", "amount": "Colonna 3", "description": "Colonna 2"}


def test_csv_preamble_above_the_header_is_skipped(app):
    raw = "Banca Esempio\nConto 123\nData;Descrizione;Importo\n01/09/2026;Lidl;-9,90\n".encode()
    headers, rows, first_line = transfer.read_table("m.csv", raw)
    assert headers == ["Data", "Descrizione", "Importo"] and rows == [{"Data": "01/09/2026", "Descrizione": "Lidl", "Importo": "-9,90"}]
    assert first_line == 4


def test_nothing_recognisable_is_not_sure(app):
    guessed = column_guess.guess(["x", "y"], [{"x": "ciao", "y": "mondo"}])
    assert not guessed.sure and guessed.mapping["date"] is None


def test_a_right_mapping_is_kept(app):
    headers, rows, _line = transfer.read_table("u.csv", (SAMPLES / "unicredit_2026-08_2026-09.csv").read_bytes())
    fixed = column_guess.fix({"date": "Data valuta", "amount": "Importo (EUR)", "description": "Descrizione"}, headers, rows)
    assert fixed.mapping["date"] == "Data valuta" and fixed.notes == []  # a date column is a valid choice


def test_ai_backup_sees_only_a_sample(client, db, monkeypatch):
    app = client.application
    app.config.update(LLM_PROVIDER="ollama", LLM_MODEL="qwen3:1.7b")
    sent = []

    def ollama_json(model, system, prompt, schema, images=None):
        sent.append(json.loads(prompt))
        assert schema["properties"]["date"]["enum"][-1] == ""
        return json.dumps({"date": "Quando", "amount": "Quanto", "debit": "", "credit": "", "description": "Cosa",
                           "category": "", "type": "", "counterparty": "Inventata"})

    monkeypatch.setattr(ai_extraction, "ollama_json", ollama_json)
    lines = ["Quando;Quanto;Cosa;Note"] + [f"{d:02d}/06/2026;-{d},50;Spesa {d};n" for d in range(1, 31)]
    response = client.post("/export/import/columns/ai", data={"file": (io.BytesIO("\n".join(lines).encode()), "x.csv")},
                           content_type="multipart/form-data")
    data = response.get_json()
    assert response.status_code == 200 and data["guess"]["date"] == "Quando" and data["guess"]["amount"] == "Quanto"
    assert data["guess"]["counterparty"] is None  # not one of the file's columns
    assert len(sent[0]["righe"]) == column_guess.AI_SAMPLE_ROWS  # 10 of the 30 rows, nothing else


def test_ai_backup_errors(client, db, monkeypatch):
    csv = io.BytesIO(b"a;b\n1;2\n")
    assert "Nessun modello" in client.post("/export/import/columns/ai", data={"file": (csv, "x.csv")},
                                           content_type="multipart/form-data").get_json()["error"]
    client.application.config.update(LLM_PROVIDER="ollama", LLM_MODEL="qwen3:1.7b")
    monkeypatch.setattr(ai_extraction, "ollama_json", lambda *a, **k: "non json")
    response = client.post("/export/import/columns/ai", data={"file": (io.BytesIO(b"a;b\n1;2\n"), "x.csv")},
                           content_type="multipart/form-data")
    assert response.status_code == 400 and "leggibile" in response.get_json()["error"]
    assert client.post("/export/import/columns/ai", data={}).status_code == 400


def test_page_offers_the_ai_button_only_with_a_model(client, db):
    assert 'id="import-ask-ai"' not in client.get("/export/").get_data(as_text=True)
    client.application.config.update(LLM_PROVIDER="ollama", LLM_MODEL="qwen3:1.7b")
    assert 'id="import-ask-ai"' in client.get("/export/").get_data(as_text=True)


def test_a_few_broken_cells_do_not_hide_a_column(app):
    headers = ["C1", "C2", "C3"]
    rows = [{"C1": d, "C2": "Spesa " + d, "C3": a} for d, a in
            [("01/09/2026", "-45,20"), ("03/09/2026", "2.450,00"), ("05/09/2026", "-17,99"), ("xx", "1")]]
    guessed = column_guess.guess(headers, rows)
    assert _mapped(guessed) == {"date": "C1", "amount": "C3", "description": "C2"} and not guessed.sure
    fixed = column_guess.fix({"date": "C2", "amount": "C3", "description": "C2"}, headers, rows)
    assert fixed.mapping["date"] == "C1" and fixed.notes == ["Data: «C2» non contiene date, uso «C1»."]
