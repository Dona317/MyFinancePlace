"""
Portfolio updates read by the AI model: the operations a document lists, and the current state (the positions) from
which the operations are derived; both go to the broker import's review page.
"""
import io
import json
from datetime import date
from decimal import Decimal

import pytest
from PIL import Image

from app.models.account import Account
from app.models.securities import SecuritiesAccount
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import ai_extraction, portfolio_reading
from app.services.ai_extraction import AIExtractionError


@pytest.fixture()
def model(app, monkeypatch):
    """Ollama faked at ollama_json: `answer` is what it replies (a dict, or a list of dicts for the parts)."""
    app.config.update(LLM_PROVIDER="ollama", LLM_MODEL="", OLLAMA_URL="http://ollama.test:11434")
    state = {"answer": {}, "calls": []}

    def reply(model_name, system, prompt, schema, images=None):
        state["calls"].append({"prompt": prompt, "schema": schema, "images": images})
        answer = state["answer"]
        return json.dumps(answer.pop(0) if isinstance(answer, list) else answer)

    monkeypatch.setattr(ai_extraction, "ollama_json", reply)
    return state


@pytest.fixture()
def book(db):
    settle = Account(name="Directa", kind="other", opening_balance=Decimal(10000))
    db.session.add(settle)
    db.session.flush()
    dossier = SecuritiesAccount(name="Titoli Directa", settlement_account_id=settle.id, active=True)
    etf = Holding(name="Vanguard FTSE All-World", isin="IE00BK5BQT80", ticker="VWCE", asset_class="ETF", quantity=10,
                  avg_price=100, current_price=Decimal(110), opening_quantity=10, opening_price=100,
                  opening_date=date(2025, 1, 2))
    enel = Holding(name="Enel", isin="IT0003128367", ticker="ENEL.MI", asset_class="Azioni", quantity=100, avg_price=6,
                   current_price=Decimal(7), opening_quantity=100, opening_price=6, opening_date=date(2025, 1, 2))
    db.session.add_all([dossier, etf, enel])
    db.session.commit()
    return settle, dossier, etf, enel


def _txt(text="Estratto conto titoli"):
    return (io.BytesIO(text.encode()), "estratto.txt")


def _png():
    out = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(out, "PNG")
    return out.getvalue()


def test_operations_are_read_and_validated(model, book):
    model["answer"] = {"operations": [
        {"date": "2026-10-01", "side": "buy", "name": "Vanguard FTSE All-World", "isin": "ie00bk5bqt80", "ticker": "",
         "quantity": 5, "price": 120, "amount_eur": 0, "fee": 1.5},
        {"date": "2026-10-02", "side": "sell", "name": "Apple", "isin": "", "ticker": "aapl", "quantity": 2,
         "price": 250, "amount_eur": 460, "fee": 0},  # priced in dollars: the euro value wins
        {"date": "", "side": "buy", "name": "Senza data", "isin": "", "ticker": "", "quantity": 1, "price": 1,
         "amount_eur": 0, "fee": 0},
        "not an operation"]}
    reading = portfolio_reading.operations("ordini.txt", b"conferma d'ordine")
    rows = reading.preview.rows
    assert [(r.name, r.units, r.price, r.fee) for r in rows] == [
        ("Vanguard FTSE All-World", Decimal(5), Decimal(120), Decimal("1.5")), ("Apple", Decimal(-2), Decimal(230), 0)]
    assert rows[0].holding_id == book[2].id and rows[0].isin == "IE00BK5BQT80" and rows[1].holding_id is None
    assert reading.preview.layout == "ai" and len(reading.notes) == 1 and "Senza data" in reading.notes[0]
    assert "<documento>" in model["calls"][0]["prompt"] and "operations" in model["calls"][0]["schema"]["properties"]


def test_nothing_to_read(model, book):
    model["answer"] = {"operations": []}
    with pytest.raises(AIExtractionError):
        portfolio_reading.operations("ordini.txt", b"niente")
    with pytest.raises(AIExtractionError):
        portfolio_reading.operations("vuoto.txt", b"   ")


def test_an_unreadable_reply_is_an_error(app, model, monkeypatch, book):
    monkeypatch.setattr(ai_extraction, "ollama_json", lambda *a, **k: "not json")
    with pytest.raises(AIExtractionError):
        portfolio_reading.operations("ordini.txt", b"conferma")


def test_no_model_configured(app, db):
    app.config.update(LLM_PROVIDER="")
    with pytest.raises(AIExtractionError):
        portfolio_reading.ask("a.txt", b"x", "p", {})


def test_the_state_gives_the_differences(model, book):
    _settle, dossier, etf, enel = book
    model["answer"] = {"date": "2026-10-31", "positions": [
        {"name": "Vanguard FTSE All-World", "isin": "IE00BK5BQT80", "ticker": "", "quantity": 8, "price": 0,
         "value_eur": 1000},
        {"name": "Vanguard FTSE All-World", "isin": "IE00BK5BQT80", "ticker": "", "quantity": 4, "price": 0,
         "value_eur": 500},  # a second lot on the next page: 12 in all
        {"name": "BTP 2030", "isin": "IT0005000001", "ticker": "", "quantity": 5000, "price": 98, "value_eur": 0},
        {"name": "Senza quantità", "isin": "", "ticker": "", "quantity": -1, "price": 1, "value_eur": 0},
            {"name": "Enel", "isin": "IT0003128367", "ticker": "", "quantity": 100, "price": 7, "value_eur": 700},
            {"name": "Ignota", "isin": "", "ticker": "", "quantity": 3, "price": 0, "value_eur": 0}]}
    reading = portfolio_reading.state("estratto.txt", b"posizioni", complete=True)
    rows = {r.name: r for r in reading.preview.rows}
    assert reading.on == date(2026, 10, 31) and reading.unchanged == 1  # Enel: 100 held, 100 shown
    assert rows["Vanguard FTSE All-World"].units == 2 and rows["Vanguard FTSE All-World"].price == Decimal(125)
    assert rows["Vanguard FTSE All-World"].holding_id == etf.id
    assert rows["BTP 2030"].units == 5000 and rows["BTP 2030"].price == Decimal("0.98")  # % of the nominal
    assert "Ignota" not in rows and any("Ignota" in n for n in reading.notes) and any("Senza" in n for n in reading.notes)
    assert all(r.on == date(2026, 10, 31) for r in reading.preview.rows)
    assert reading.preview.layout == "state" and enel.id not in {r.holding_id for r in reading.preview.rows}


def test_the_complete_state_sells_what_is_no_longer_there(model, book):
    _settle, _dossier, etf, enel = book
    model["answer"] = {"date": "", "positions": [
        {"name": "Enel", "isin": "IT0003128367", "ticker": "", "quantity": 100, "price": 7, "value_eur": 0}]}
    reading = portfolio_reading.state("estratto.txt", b"posizioni", on=date(2026, 11, 2), complete=True)
    assert [(r.holding_id, r.units, r.price) for r in reading.preview.rows] == [(etf.id, Decimal(-10), Decimal(110))]
    model["answer"] = {"date": "", "positions": [
        {"name": "Enel", "isin": "IT0003128367", "ticker": "", "quantity": 100, "price": 7, "value_eur": 0}]}
    same = portfolio_reading.state("estratto.txt", b"posizioni", on=date(2026, 11, 2))
    assert same.preview.rows == [] and same.unchanged == 1


def test_the_state_of_one_securities_account(model, book, client):
    settle, dossier, etf, _enel = book
    from app.services import securities
    securities.ensure_assigned()
    model["answer"] = {"date": "2026-11-03", "positions": [
        {"name": "Vanguard FTSE All-World", "isin": "IE00BK5BQT80", "ticker": "", "quantity": 15, "price": 112,
         "value_eur": 0}]}
    page = client.post("/portfolio/import/ai", data={"file": _txt(), "mode": "state", "dossier_id": str(dossier.id)},
                       content_type="multipart/form-data")
    assert page.status_code == 200 and "dallo stato attuale" in page.text and "Titoli Directa" in page.text
    assert f'name="dossier_id" value="{dossier.id}"' in page.text and "broker-columns" not in page.text
    payload = page.text.split('name="payload" value="', 1)[1].split('"', 1)[0]
    done = client.post("/portfolio/import/confirm", data={"payload": payload, "include": "0", "account_id": str(settle.id),
                                                          "dossier_id": str(dossier.id), "holding-0": str(etf.id)},
                       follow_redirects=True)
    assert "1 operazioni importate" in done.text
    trade = Transaction.query.filter(Transaction.holding_id == etf.id, Transaction.units.isnot(None)).one()
    assert trade.securities_account_id == dossier.id and trade.unit_price == Decimal(112)


def test_the_pages(model, book, client):
    page = client.get("/portfolio/import")
    assert "Leggi con AI" in page.text and "Stato attuale" in page.text
    model["answer"] = {"operations": [
        {"date": "2026-10-01", "side": "buy", "name": "Enel", "isin": "IT0003128367", "ticker": "", "quantity": 10,
         "price": 7, "amount_eur": 0, "fee": 0}]}
    preview = client.post("/portfolio/import/ai", data={"file": _txt(), "mode": "operations"},
                          content_type="multipart/form-data")
    assert preview.status_code == 200 and "letto con AI" in preview.text and "save-preset" not in preview.text
    model["answer"] = {"date": "", "positions": [
        {"name": "Enel", "isin": "IT0003128367", "ticker": "", "quantity": 100, "price": 7, "value_eur": 0},
        {"name": "Vanguard FTSE All-World", "isin": "IE00BK5BQT80", "ticker": "", "quantity": 10, "price": 0,
         "value_eur": 0}]}
    same = client.post("/portfolio/import/ai", data={"file": _txt(), "mode": "state"},
                       content_type="multipart/form-data", follow_redirects=True)
    assert "nessuna operazione da aggiungere" in same.text
    model["answer"] = {"operations": []}
    failed = client.post("/portfolio/import/ai", data={"file": _txt(), "mode": "operations"},
                         content_type="multipart/form-data", follow_redirects=True)
    assert "Lettura AI non riuscita" in failed.text
    missing = client.post("/portfolio/import/ai", data={}, follow_redirects=True)
    assert "Scegli il documento" in missing.text


def test_the_page_without_a_model(app, client, db):
    app.config.update(LLM_PROVIDER="")
    assert "non è configurata" in client.get("/portfolio/import").text


def test_images_go_to_the_local_model_as_pages(model, book):
    model["answer"] = {"operations": [
        {"date": "2026-10-01", "side": "buy", "name": "Enel", "isin": "", "ticker": "", "quantity": 10, "price": 7,
         "amount_eur": 0, "fee": 0}]}
    portfolio_reading.operations("foto.png", _png())
    assert model["calls"][0]["images"] and "<documento>" not in model["calls"][0]["prompt"]


def test_claude_gets_the_image(app, monkeypatch, book):
    app.config.update(LLM_PROVIDER="anthropic", LLM_MODEL="claude-haiku-4-5")
    sent = []

    def reply(model_name, system, content, schema, **kwargs):
        sent.append(content)
        return json.dumps({"date": "", "positions": []})

    monkeypatch.setattr(ai_extraction, "anthropic_json", reply)
    reading = portfolio_reading.state("foto.png", _png())
    assert sent[0][0]["type"] == "image" and reading.preview.rows == []
    portfolio_reading.state("estratto.txt", b"posizioni")
    assert sent[1][0]["type"] == "text"
