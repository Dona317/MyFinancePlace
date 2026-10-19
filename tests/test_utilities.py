"""F23: utility bills — consumption, cost per unit, seasons, another offer, bills from movements and from the AI."""
import json
from datetime import date
from decimal import Decimal

import pytest

from app.models.utility import UtilityReading
from app.models.wealth import Document
from app.services import ai_extraction, document_store, settings_store, utilities
from tests.conftest import make_tx


def _bill(db, start, end, amount, use=None, utility="power", **values):
    reading = utilities.save(None, utility=utility, start=start, end=end, amount=Decimal(amount),
                             consumption=Decimal(use) if use is not None else None, **values)
    db.session.commit()
    return reading


def test_costs_by_month_and_unit(db):
    jan = _bill(db, date(2026, 1, 1), date(2026, 2, 28), "177", "590", supplier="  Enel   Energia ")
    assert jan.supplier == "Enel Energia" and utilities.days(jan) == 59
    assert utilities.unit_cost(jan) == Decimal("0.3000") and utilities.monthly_cost(jan) == Decimal("91.32")
    data = utilities.by_month("power")
    assert data[(2026, 1)]["use"].quantize(Decimal("0.1")) == Decimal("310.0")
    assert sum(v["cost"] for v in data.values()).quantize(Decimal("0.01")) == 177
    _bill(db, date(2026, 3, 1), date(2026, 4, 30), "120", "480")
    flat = _bill(db, date(2026, 1, 1), date(2026, 1, 31), "29.90", utility="internet")
    assert utilities.unit_cost(flat) is None
    s = utilities.summary("power", today=date(2026, 6, 15))
    assert s.count == 2 and s.year_cost == Decimal("297.00") and s.year_use == Decimal("1070.0")
    assert s.monthly == Decimal("74.25") and s.unit_cost == Decimal("0.2776") and s.last.period_end == date(2026, 4, 30)
    empty = utilities.summary("gas", today=date(2026, 6, 15))
    assert empty.year_cost == 0 and empty.unit_cost is None and empty.last is None and empty.monthly == 0
    chart = utilities.chart("power")
    assert chart["labels"] == ["02/26", "04/26"] and chart["unit"] == [0.3, 0.25]


def test_seasons_and_offer(db):
    _bill(db, date(2025, 1, 1), date(2025, 2, 28), "200", "600", utility="gas")
    _bill(db, date(2026, 1, 1), date(2026, 2, 28), "180", "450", utility="gas")
    rows = utilities.seasons("gas", today=date(2026, 6, 1))
    winter = rows[0]
    assert winter["before"]["use"] == Decimal("600.0") and winter["now"]["use"] == Decimal("450.0")
    assert winter["change"] == -25.0 and rows[2]["before"] is None and rows[2]["change"] is None
    offer = utilities.with_offer("gas", Decimal("0.30"), Decimal(10), today=date(2026, 6, 1))
    assert offer == {"months": 2, "actual": Decimal("180.00"), "other": Decimal("155.00"), "difference": Decimal("-25.00")}
    assert utilities.with_offer("water", Decimal(1), None, today=date(2026, 6, 1)) is None
    with pytest.raises(ValueError, match="prezzo"):
        utilities.with_offer("gas", None, None)


def test_validation(db):
    for values, message in ((dict(utility="phone"), "utenza"), (dict(start=None), "periodo"),
                            (dict(end=date(2025, 12, 1)), "prima"), (dict(amount=Decimal(0)), "positivo"),
                            (dict(consumption=Decimal(-1)), "negativo")):
        base = dict(utility="power", start=date(2026, 1, 1), end=date(2026, 1, 31), amount=Decimal(50))
        with pytest.raises(ValueError, match=message):
            utilities.save(None, **(base | values))


def test_candidates_from_movements(db):
    today = date.today()
    luce = make_tx(date=today, description="ENEL ENERGIA addebito", amount=95, category="Luce")
    gas = make_tx(date=today, description="A2A gas", amount=60, category="Gas")
    other = make_tx(date=today, description="Spesa", amount=30, category="Spesa")
    db.session.add_all([luce, gas, other])
    db.session.commit()
    _bill(db, date(today.year - 1, 1, 1), date(today.year - 1, 2, 27), "100", "300", utility="gas")
    found = {tx.id: (key, start) for tx, key, start in utilities.candidates()}
    assert set(found) == {luce.id, gas.id}
    assert found[gas.id] == ("gas", date(today.year - 1, 2, 28)) and found[luce.id][0] == "power"
    utilities.save(None, utility="power", start=found[luce.id][1], end=today, amount=Decimal(95), transaction=luce)
    db.session.commit()
    assert [tx.id for tx, _, _ in utilities.candidates()] == [gas.id]


def _document(db, raw: bytes, name: str) -> Document:
    stored, mimetype = document_store.save(name, raw)
    doc = Document(filename=name, stored_name=stored, mimetype=mimetype, size=len(raw))
    db.session.add(doc)
    db.session.commit()
    return doc


ANSWER = {"utility": "power", "supplier": "Enel", "period_start": "2026-07-01", "period_end": "2026-08-31",
          "consumption": 412.5, "amount": 131.2}


def test_read_bill_with_ai(app, db, monkeypatch):
    pdf = b"%PDF-1.4\n%fake\n"
    doc = _document(db, pdf, "bolletta.pdf")
    with pytest.raises(ValueError, match="non è attiva"):
        utilities.read_bill(doc)
    settings_store.set(ai_extraction.PROVIDER_SETTING, "anthropic")
    sent = {}
    monkeypatch.setattr(ai_extraction, "split_pdf", lambda raw, pages: [raw])
    monkeypatch.setattr(ai_extraction, "anthropic_json",
                        lambda model, system, content, schema, max_tokens: sent.update(content=content) or json.dumps(ANSWER))
    found = utilities.read_bill(doc)
    assert found["utility"] == "power" and found["start"] == date(2026, 7, 1) and found["consumption"] == Decimal("412.5")
    assert sent["content"][0]["type"] == "document"
    monkeypatch.setattr(ai_extraction, "anthropic_json", lambda *a, **k: json.dumps(ANSWER | {"period_end": "agosto"}))
    with pytest.raises(ValueError, match="non ha letto"):
        utilities.read_bill(doc)
    settings_store.set(ai_extraction.PROVIDER_SETTING, "ollama")
    monkeypatch.setattr(ai_extraction, "_pdf_page_images", lambda raw: [b"page1", b"page2", b"page3"])
    monkeypatch.setattr(ai_extraction, "ollama_json", lambda model, system, prompt, schema, images:
                        sent.update(images=images) or json.dumps(ANSWER | {"utility": "boh", "consumption": None}))
    found = utilities.read_bill(doc)
    assert found["utility"] == "" and found["consumption"] is None and sent["images"] == [b"page1", b"page2"]
    text = _document(db, b"just text", "nota.txt")
    with pytest.raises(ValueError, match="PDF o in foto"):
        utilities.read_bill(text)


def test_pages(client, db, monkeypatch):
    page = client.get("/utilities/").get_data(as_text=True)
    assert "Bollette" in page and "Nessuna bolletta" in page and "è spenta" in page
    client.post("/utilities/new", data={"utility": "gas", "supplier": "A2A", "start": "2026-01-01", "end": "2026-02-28",
                                        "amount": "180", "consumption": "450"})
    reading = UtilityReading.query.one()
    page = client.get("/utilities/?utility=gas").get_data(as_text=True)
    assert "A2A" in page and "utilityChart" in page and "Consumo per stagione" in page
    assert client.get("/utilities/").status_code == 200  # the utility with the most bills
    assert "positivo" in client.post("/utilities/new", data={"utility": "gas", "start": "2026-01-01", "end": "2026-01-31",
                                                             "amount": "0"}, follow_redirects=True).get_data(as_text=True)
    assert 'value="A2A"' in client.get(f"/utilities/?utility=gas&edit={reading.id}").get_data(as_text=True)
    client.post(f"/utilities/{reading.id}/edit", data={"utility": "gas", "supplier": "Hera", "start": "2026-01-01",
                                                       "end": "2026-02-28", "amount": "190", "consumption": "460"})
    db.session.refresh(reading)
    assert reading.supplier == "Hera" and reading.amount == 190
    offer = client.get("/utilities/?utility=gas&unit_price=0,30&fixed=10").get_data(as_text=True)
    assert "avresti pagato" in offer and "in meno" in offer
    assert "prezzo per unità" in client.get("/utilities/?utility=gas&unit_price=x", follow_redirects=True).get_data(as_text=True)
    tx = make_tx(date=date.today(), description="ENEL addebito", amount=95, category="Luce")
    db.session.add(tx)
    db.session.commit()
    assert "ENEL addebito" in client.get("/utilities/").get_data(as_text=True)
    client.post("/utilities/new", data={"transaction_id": tx.id, "utility": "power", "amount": "95", "supplier": "ENEL",
                                        "start": "2026-08-01", "end": date.today().isoformat(), "consumption": "300"})
    assert UtilityReading.query.filter_by(transaction_id=tx.id).one().consumption == 300
    doc = _document(db, b"%PDF-1.4\n", "bolletta.pdf")
    settings_store.set(ai_extraction.PROVIDER_SETTING, "anthropic")
    db.session.commit()
    monkeypatch.setattr(utilities, "read_bill", lambda d: {"utility": "power", "supplier": "Enel", "start": date(2026, 7, 1),
                                                           "end": date(2026, 8, 31), "consumption": Decimal("412.5"),
                                                           "amount": Decimal("131.2")})
    page = client.post("/utilities/read", data={"document_id": doc.id}, follow_redirects=True).get_data(as_text=True)
    assert "controllali" in page and 'value="2026-08-31"' in page and f'name="document_id" value="{doc.id}"' in page
    monkeypatch.setattr(utilities, "read_bill", lambda d: (_ for _ in ()).throw(ValueError("non ha letto")))
    assert "non ha letto" in client.post("/utilities/read", data={"document_id": doc.id},
                                         follow_redirects=True).get_data(as_text=True)
    client.post(f"/utilities/{reading.id}/delete")
    assert UtilityReading.query.count() == 1
