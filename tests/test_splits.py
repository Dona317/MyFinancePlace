"""F1: split transactions — one amount across several categories, counted by category everywhere."""
import io
import json
import zipfile
from datetime import date
from decimal import Decimal

import pytest

from app.models.currency import ExchangeRate
from app.models.transaction import Transaction, TransactionSplit
from app.services import analytics, backup, budgets, categories, category_rules, forecast, history_classifier, reports, wealth
from tests.conftest import make_tx

JUNE = date(2026, 6, 10)


def _split(db, parts=(("Alimentari", 70), ("Casa", 30)), amount=100, **values):
    tx = make_tx(date=JUNE, description="Esselunga spesa grande", amount=amount, category=parts[0][0], **values)
    tx.splits = [TransactionSplit(category=c, amount=Decimal(a)) for c, a in parts]
    db.session.add(tx)
    db.session.commit()
    return tx


def _form(**changes):
    data = {"date": "2026-06-10", "description": "Supermercato", "amount": "-100", "currency": "EUR",
            "split_category": ["Alimentari", "Casa"], "split_amount": ["70", "30"]}
    data.update(changes)
    return data


def test_form_saves_the_parts_and_the_largest_category(client, db):
    response = client.post("/transactions/new", data=_form())
    assert response.status_code == 302
    tx = Transaction.query.one()
    assert [(s.category, s.amount) for s in tx.splits] == [("Alimentari", Decimal("70.00")), ("Casa", Decimal("30.00"))]
    assert tx.category == "Alimentari" and tx.type == "expense"
    assert tx.parts() == [("Alimentari", 70.0), ("Casa", 30.0)]


@pytest.mark.parametrize("changes, message", [
    ({"split_amount": ["70", "20"]}, "le parti fanno 90,00 ma l&#39;importo è 100,00"),
    ({"split_category": ["Alimentari", ""]}, "riga 2: scegli una categoria"),
    ({"split_amount": ["130", "-30"]}, "riga 2: l&#39;importo deve essere positivo"),
    ({"split_amount": ["70", "tanti"]}, "riga 2: «tanti» non è un importo"),
    ({"transfer": "on"}, "un trasferimento tra conti non si suddivide"),
])
def test_form_refuses_parts_that_do_not_add_up(client, db, changes, message):
    response = client.post("/transactions/new", data=_form(**changes))
    html = response.get_data(as_text=True)
    assert response.status_code == 200 and message in html and Transaction.query.count() == 0
    assert 'value="70"' in html or 'value="130"' in html  # nothing typed is lost


def test_one_part_left_is_an_ordinary_transaction(client, db):
    tx = _split(db)
    client.post(f"/transactions/{tx.id}/edit", data=_form(category="Casa", split_category=["Casa"], split_amount=["100"]))
    db.session.refresh(tx)
    assert tx.splits == [] and tx.category == "Casa"
    assert TransactionSplit.query.count() == 0


def test_edit_page_shows_the_parts_and_the_list_shows_both_categories(client, db):
    tx = _split(db)
    html = client.get(f"/transactions/{tx.id}/edit").get_data(as_text=True)
    assert 'id="split-box"' in html and 'value="70,00"' in html and 'value="30,00"' in html
    listing = client.get("/transactions/").get_data(as_text=True)
    assert "Alimentari + Casa" in listing and "suddivisa" in listing
    assert "Esselunga spesa grande" in client.get("/transactions/?category=Casa").get_data(as_text=True)


def test_every_total_by_category_counts_each_part(app, db):
    _split(db)
    db.session.add(make_tx(date=JUNE, category="Casa", amount=5))
    db.session.commit()
    start, end = date(2026, 6, 1), date(2026, 7, 1)
    with app.test_request_context():
        assert {i["category"]: i["amount"] for i in analytics.category_breakdown(start, end)} == {"Alimentari": 70.0, "Casa": 35.0}
        trend = {d["label"]: d["data"][5] for d in analytics.monthly_category_trend(2026, 5, "expense", 12)["datasets"]}
        assert trend == {"Alimentari": 70.0, "Casa": 35.0}
        table = analytics.summary_table(2026, 6)
        assert {r["name"]: r["total"] for r in table["expense"]["rows"]} == {"Alimentari": 70.0, "Casa": 35.0}
        assert budgets.spent_by_category(JUNE) == {"Alimentari": 70.0, "Casa": 35.0}
        assert analytics.totals(start, end)["expenses"] == 105.0  # the transaction itself is counted once
        rows = reports.transactions(reports.base_query(start, end), "expense", "Casa")
        assert sorted(reports.value(tx) for tx in rows) == [5.0, 30.0]
        assert reports.summary(rows)["total"] == 35.0
        assert categories.usage()["Casa"] == 2 and "Alimentari" in categories.used_names()


def test_split_income_and_dividends(app, db):
    _split(db, parts=(("Dividendi", 40), ("Stipendio", 60)), type="income")
    with app.test_request_context():
        assert wealth.dividends(date(2026, 1, 1), date(2027, 1, 1)) == 40.0


def test_forecast_spreads_the_parts(app, db):
    _split(db)
    tx = Transaction.query.one()
    series = forecast._variable_series([tx], 0, 30000, set())
    assert {key: sum(values) for key, values in series.items()} == {("expense", "Alimentari"): 70.0, ("expense", "Casa"): 30.0}


def test_foreign_currency_parts_keep_their_share(app, db):
    db.session.add(ExchangeRate(currency="USD", on=date(2026, 6, 1), rate=Decimal("0.8")))  # 100 USD = 80 EUR
    db.session.commit()
    tx = _split(db, currency="USD")
    assert tx.amount_base == Decimal("80.00")
    with app.test_request_context():
        breakdown = {i["category"]: i["amount"] for i in analytics.category_breakdown(date(2026, 6, 1), date(2026, 7, 1))}
    assert breakdown == {"Alimentari": 56.0, "Casa": 24.0} and tx.parts() == [("Alimentari", 56.0), ("Casa", 24.0)]


def test_renaming_or_deleting_a_category_reaches_the_parts(db):
    categories.ensure_defaults()
    _split(db)
    categories.rename("Casa", "Abitazione")
    assert {s.category for s in TransactionSplit.query} == {"Alimentari", "Abitazione"}
    categories.delete("Abitazione", "Altro")
    assert {s.category for s in TransactionSplit.query} == {"Alimentari", "Altro"}


def test_rules_ai_and_history_leave_a_split_alone(client, db):
    tx = _split(db, parts=(("Altro", 70), ("Casa", 30)))
    category_rules.learn("Esselunga", "Alimentari")
    tx.counterparty = "Esselunga"
    db.session.commit()
    category_rules.apply()
    assert Transaction.query.one().category == "Altro"  # still the split made by hand
    client.post("/transactions/classify/apply", data={"apply": [str(tx.id)], f"category-{tx.id}": "Svago"})
    assert Transaction.query.one().category == "Altro"
    with client.application.test_request_context():
        assert not history_classifier.index().size  # the history does not learn from it


def test_deleting_the_transaction_deletes_its_parts(db):
    tx = _split(db)
    db.session.delete(tx)
    db.session.commit()
    assert TransactionSplit.query.count() == 0


def test_api_reads_and_writes_the_parts(client, db):
    body = {"description": "Spesa", "amount": 100, "date": "2026-06-10", "type": "expense",
            "splits": [{"category": "Alimentari", "amount": 70}, {"category": "Casa", "amount": 30}]}
    created = client.post("/transactions/api", json=body)
    assert created.status_code == 201 and created.json["splits"] == body["splits"] and created.json["category"] == "Alimentari"
    tx_id = created.json["id"]
    bad = client.put(f"/transactions/api/{tx_id}", json=body | {"splits": [{"category": "Casa", "amount": 1}, {"category": "X", "amount": 1}]})
    assert bad.status_code == 422 and "le parti fanno" in bad.get_data(as_text=True)
    kept = client.put(f"/transactions/api/{tx_id}", json={k: v for k, v in body.items() if k != "splits"} | {"description": "Spesa!"})
    assert len(kept.json["splits"]) == 2  # left out: unchanged
    cleared = client.put(f"/transactions/api/{tx_id}", json=body | {"splits": []})
    assert cleared.json["splits"] == []


def test_export_and_backup_keep_the_parts(client, db):
    _split(db)
    csv = client.get("/export/csv?period=all").get_data(as_text=True)
    assert "Alimentari 70,00; Casa 30,00" in csv
    exported = client.get("/export/json").json["transactions"][0]
    assert exported["splits"] == [{"category": "Alimentari", "amount": 70.0}, {"category": "Casa", "amount": 30.0}]
    raw = client.get("/export/backup").data
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        data = json.loads(archive.read("backup.json"))
    assert len(data["tables"]["transaction_splits"]) == 2
    TransactionSplit.query.delete()
    db.session.commit()
    backup.restore(data, {})
    assert [(s.category, s.amount) for s in TransactionSplit.query.order_by(TransactionSplit.id)] == [
        ("Alimentari", Decimal("70.00")), ("Casa", Decimal("30.00"))]
