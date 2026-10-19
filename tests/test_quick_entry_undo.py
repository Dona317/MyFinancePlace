"""F13: quick entry from the transactions list, and undo/redo of the last added or deleted transactions."""
import json
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.models.transaction import Transaction, TransactionSplit
from app.services import categories, settings_store, undo
from tests.conftest import make_tx


def test_quick_entry_guesses_category_and_counterparty(client, db):
    categories.ensure_defaults()
    response = client.post("/transactions/quick", data={"date": "2026-10-05", "description": "PAGAMENTO POS ESSELUNGA MILANO",
                                                         "amount": "-45,20"})
    assert response.status_code == 302
    tx = Transaction.query.one()
    assert (tx.type, tx.amount, tx.category, tx.counterparty) == ("expense", Decimal("45.20"), "Alimentari", "Esselunga")
    client.post("/transactions/quick", data={"date": "2026-10-06", "description": "Lezione privata", "amount": "50",
                                             "category": "Freelance"})
    assert Transaction.query.filter_by(description="Lezione privata").one().category == "Freelance"
    html = client.post("/transactions/quick", data={"date": "2026-10-06", "description": "X", "amount": "0"},
                       follow_redirects=True).get_data(as_text=True)
    assert "diverso da zero" in html and Transaction.query.count() == 2
    assert 'id="quick-add"' in html and 'id="undo-button"' in html


def test_undo_and_redo_an_added_transaction(client, db):
    client.post("/transactions/quick", data={"date": "2026-10-05", "description": "Caffè", "amount": "-1,20"})
    assert "Aggiunta «Caffè»" in client.get("/transactions/").get_data(as_text=True)
    client.post("/transactions/undo")
    assert Transaction.query.count() == 0
    html = client.get("/transactions/").get_data(as_text=True)
    assert 'id="redo-button"' in html and 'id="undo-button"' not in html
    client.post("/transactions/redo")
    assert Transaction.query.one().description == "Caffè"
    client.post("/transactions/undo")  # the redo can be undone in turn
    assert Transaction.query.count() == 0


def test_undo_a_deletion_puts_back_the_rows_and_their_parts(client, db):
    tx = make_tx(description="Spesa grande", amount=100, category="Alimentari", tags=["Esselunga"])
    tx.splits = [TransactionSplit(category="Alimentari", amount=Decimal(70)), TransactionSplit(category="Casa", amount=Decimal(30))]
    other = make_tx(description="Benzina", amount=60)
    db.session.add_all([tx, other])
    db.session.commit()
    tx_id = tx.id
    client.post(f"/transactions/{tx_id}/delete")
    assert Transaction.query.count() == 1
    assert "Annullato: rimessa" in client.post("/transactions/undo", follow_redirects=True).get_data(as_text=True)
    back = db.session.get(Transaction, tx_id)
    assert back.description == "Spesa grande" and back.tags == ["Esselunga"] and back.amount_base == Decimal("100.00")
    assert sorted((s.category, s.amount) for s in back.splits) == [("Alimentari", Decimal("70.00")), ("Casa", Decimal("30.00"))]
    client.post("/transactions/delete-selected", data={"ids": [str(tx_id), str(other.id)]})
    assert Transaction.query.count() == 0
    assert "Eliminate 2 transazioni" in client.get("/transactions/").get_data(as_text=True)
    client.post("/transactions/undo")
    assert Transaction.query.count() == 2 and TransactionSplit.query.count() == 2


def test_nothing_to_undo_and_old_steps_expire(client, db):
    assert "Niente da annullare" in client.post("/transactions/undo", follow_redirects=True).get_data(as_text=True)
    assert "Niente da ripetere" in client.post("/transactions/redo", follow_redirects=True).get_data(as_text=True)
    tx = make_tx()
    db.session.add(tx)
    db.session.commit()
    with client.application.test_request_context():
        undo.remember_created([tx])
        step = json.loads(settings_store.get(undo.UNDO_KEY))
        step["at"] = (datetime.now() - timedelta(hours=2)).isoformat()
        settings_store.set(undo.UNDO_KEY, json.dumps(step))
        assert undo.available() == {"undo": None, "redo": None}
        settings_store.set(undo.UNDO_KEY, "{broken")
        assert undo.undo() is None
        settings_store.set(undo.UNDO_KEY, json.dumps({"kind": "created", "ids": [], "at": "yesterday"}))
        assert undo.available()["undo"] is None


def test_a_restored_row_whose_id_was_taken_gets_a_new_one(client, db):
    tx = make_tx(description="Vecchia", date=date(2026, 1, 1))
    db.session.add(tx)
    db.session.commit()
    old_id = tx.id
    client.post(f"/transactions/{old_id}/delete")
    db.session.execute(Transaction.__table__.insert().values(id=old_id, date=date(2026, 2, 2), description="Nuova",
                                                             amount=5, type="expense", tags=[]))
    db.session.commit()
    client.post("/transactions/undo")
    assert sorted(t.description for t in Transaction.query) == ["Nuova", "Vecchia"]
