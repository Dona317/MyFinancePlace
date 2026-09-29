"""Full backup (.zip) and restore, and re-importing the older JSON export of the transactions."""
import io
import json
import zipfile
from datetime import date
from decimal import Decimal

import pytest

from app.models import AppSetting, Debt, Document, DuplicateDismissal, Goal, Holding, InsurancePolicy, Snapshot, Transaction
from app.services import backup, settings_store, wealth
from tests.conftest import make_tx


@pytest.fixture()
def instance(app, tmp_path):
    app.instance_path = str(tmp_path)
    return tmp_path


@pytest.fixture()
def everything(db, sample_data, instance):
    """One row in every table, and a file in the document archive."""
    first, second = Transaction.query.order_by(Transaction.id).limit(2).all()
    stored = "b" * 32 + ".pdf"
    (instance / "documents").mkdir(exist_ok=True)
    (instance / "documents" / stored).write_bytes(b"%PDF contratto")
    db.session.add_all([
        DuplicateDismissal(first_id=first.id, second_id=second.id),
        Holding(name="VWCE", asset_class="ETF", quantity=Decimal("3.12345678"), avg_price=Decimal("101.5")),
        Debt(name="Mutuo", type="Mutuo", principal=Decimal("100000"), annual_rate=Decimal("2.75"), term_months=240,
             start_date=date(2024, 3, 1)),
        InsurancePolicy(type="Casa", company="Allianz", premium=Decimal("300"), frequency="annual"),
        Goal(name="Vacanza", target_amount=Decimal("3000"), saved_amount=Decimal("250")),
        Document(filename="contratto.pdf", stored_name=stored, mimetype="application/pdf", size=14,
                 transaction_id=first.id),
    ])
    db.session.commit()
    settings_store.set("forecast.window", "6")
    wealth.take_snapshot("Prima")


def upload(client, content: bytes, name="backup.zip", confirm=True):
    data = {"file": (io.BytesIO(content), name)}
    if confirm:
        data["confirm"] = "1"
    return client.post("/export/restore", data=data, content_type="multipart/form-data", follow_redirects=True)


def test_backup_contains_every_table_and_the_files(client, everything):
    response = client.get("/export/backup")
    assert response.mimetype == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        data = json.loads(archive.read("backup.json"))
        assert archive.read("documents/" + "b" * 32 + ".pdf") == b"%PDF contratto"
    assert data["format"] == "myfinanceplace-backup"
    assert backup.counts(data) == {
        "app_settings": 1, "accounts": 0, "categories": 0, "category_rules": 0, "transactions": 8, "duplicate_dismissals": 1, "holdings": 1, "debts": 1,
        "insurance_policies": 1, "goals": 1, "documents": 1, "snapshots": 1,
    }


def test_restore_brings_everything_back(client, db, everything, instance):
    archive = client.get("/export/backup").data
    net_worth = wealth.balance_sheet()["net_worth"]

    # change things after the backup: they must disappear
    db.session.add(make_tx(description="Dopo il backup"))
    Goal.query.delete()
    db.session.commit()
    (instance / "documents" / "orfano.pdf").write_bytes(b"x")

    html = upload(client, archive).get_data(as_text=True)
    assert "Backup ripristinato: 8 transazioni" in html

    db.session.expire_all()
    assert Transaction.query.count() == 8 and not Transaction.query.filter_by(description="Dopo il backup").count()
    assert Goal.query.one().saved_amount == 250
    assert Holding.query.one().quantity == Decimal("3.12345678")
    assert Snapshot.query.one().detail["holdings"][0]["name"] == "VWCE"
    assert DuplicateDismissal.query.count() == 1
    assert db.session.get(AppSetting, "forecast.window").value == "6"
    assert Document.query.one().transaction_id == Transaction.query.order_by(Transaction.id).first().id
    assert (instance / "documents" / ("b" * 32 + ".pdf")).read_bytes() == b"%PDF contratto"
    assert not (instance / "documents" / "orfano.pdf").exists()
    assert wealth.balance_sheet()["net_worth"] == net_worth

    # new rows continue after the restored ids
    db.session.add(make_tx(description="Nuova"))
    db.session.commit()
    assert Transaction.query.filter_by(description="Nuova").one().id > 8


def test_restore_keeps_a_copy_of_the_replaced_data(client, db, everything):
    archive = client.get("/export/backup").data
    db.session.add(make_tx(description="Solo prima del ripristino"))
    db.session.commit()
    upload(client, archive)

    copies = backup.list_safety_copies()
    assert len(copies) == 1
    saved = client.get(f"/export/backup/automatic/{copies[0]['name']}")
    with zipfile.ZipFile(io.BytesIO(saved.data)) as zipped:
        data = json.loads(zipped.read("backup.json"))
    assert any(t["description"] == "Solo prima del ripristino" for t in data["tables"]["transactions"])
    assert "Backup automatici (1)" in client.get("/export/").get_data(as_text=True)
    assert client.get("/export/backup/automatic/..%2F..%2Fsecret.zip").status_code == 404


def test_restore_needs_confirmation(client, db, everything):
    archive = client.get("/export/backup").data
    db.session.add(make_tx(description="Resta"))
    db.session.commit()
    html = upload(client, archive, confirm=False).get_data(as_text=True)
    assert "conferma che i dati attuali verranno sostituiti" in html
    assert Transaction.query.filter_by(description="Resta").count() == 1


@pytest.mark.parametrize("content, message", [
    (b"not a backup", "non è un backup"),
    (b'{"hello": 1}', "non è un backup di MyFinancePlace"),
    (b'{"format": "myfinanceplace-backup", "version": 99, "tables": {}}', "versione più recente"),
])
def test_invalid_files_change_nothing(client, db, sample_data, instance, content, message):
    html = upload(client, content, name="x.json").get_data(as_text=True)
    assert message in html
    assert Transaction.query.count() == 8


def test_broken_backup_is_all_or_nothing(client, db, sample_data, instance):
    data = backup.export_data()
    data["tables"]["transactions"][0]["amount"] = "tanti"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("backup.json", json.dumps(data))
    html = upload(client, buffer.getvalue()).get_data(as_text=True)
    assert "valore non valido" in html
    assert Transaction.query.count() == 8


def test_old_json_export_adds_only_new_transactions(client, db, sample_data, instance):
    exported = client.get("/export/json").data
    payload = json.loads(exported)
    payload["transactions"].append({"date": "2026-07-01", "description": "Nuova spesa", "amount": 42.5,
                                    "type": "expense", "tags": ["x"], "is_recurring": False})
    html = upload(client, json.dumps(payload).encode(), name="old.json", confirm=False).get_data(as_text=True)
    assert "1 transazioni aggiunte, 8 già presenti ignorate" in html
    assert Transaction.query.count() == 9
    assert Transaction.query.filter_by(description="Nuova spesa").one().amount == Decimal("42.50")
