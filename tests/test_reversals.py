"""F108: reversals (storni) — an expense and an income of the same amount that cancel each other."""
import io
import re
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.transaction import Transaction
from app.services import reversals, totals
from tests.conftest import make_tx
from tests.form_helper import form_data


@pytest.fixture()
def conto(db):
    account = Account(name="Conto", kind="current")
    db.session.add(account)
    db.session.commit()
    return account


def _tx(db, account=None, **values):
    tx = make_tx(account_id=account.id if account else None, **values)
    db.session.add(tx)
    db.session.commit()
    return tx


def expenses() -> float:
    return totals.value_total(Transaction.type == "expense")


def test_a_linked_reversal_stays_out_of_the_totals(db, conto):
    pay = _tx(db, conto, description="PAGAMENTO POS NEGOZIO", amount=50, category="Shopping", date=date(2026, 11, 1))
    back = _tx(db, conto, description="STORNO PAGAMENTO POS NEGOZIO", amount=50, type="income", category="Rimborsi",
               date=date(2026, 11, 3))
    _tx(db, conto, description="Spesa", amount=30, date=date(2026, 11, 2))
    assert expenses() == 80
    reversals.link(pay, back)
    db.session.commit()
    assert pay.reversal_id == back.id and back.reversal_id == pay.id
    assert expenses() == 30 and totals.value_total(Transaction.type == "income") == 0
    assert pay.category == "Shopping"  # each keeps its own category
    assert reversals.linked_pairs() == [(pay, back)]
    assert reversals.unlink(back) == pay
    db.session.commit()
    assert pay.reversal_id is None and expenses() == 80
    assert reversals.unlink(pay) is None


def test_what_cannot_be_a_reversal(db, conto):
    pay = _tx(db, conto, amount=50)
    other_pay = _tx(db, conto, amount=50)
    smaller = _tx(db, conto, amount=40, type="income")
    dollars = _tx(db, conto, amount=50, type="income", currency="USD")
    back = _tx(db, conto, amount=50, type="income")
    giro = _tx(db, conto, amount=50, type="transfer")
    for first, second, words in ((pay, pay, "diversi"), (pay, other_pay, "direzioni opposte"),
                                 (pay, giro, "direzioni opposte"), (pay, smaller, "stesso importo"),
                                 (pay, dollars, "stesso importo")):
        with pytest.raises(ValueError, match=words):
            reversals.check(first, second)
    reversals.link(pay, back)
    with pytest.raises(ValueError, match="già collegato"):
        reversals.check(other_pay, back)


def test_candidates_pair_each_movement_once(db, conto):
    other_account = Account(name="Altro", kind="current")
    db.session.add(other_account)
    db.session.commit()
    day = date(2026, 11, 10)
    pay = _tx(db, conto, description="Amazon", amount=25, date=day)
    near = _tx(db, conto, description="Bonifico da Mario", amount=25, type="income", date=day + timedelta(days=2))
    far = _tx(db, conto, description="STORNO Amazon", amount=25, type="income", date=day + timedelta(days=30))
    _tx(db, other_account, description="Altro conto", amount=25, type="income", date=day)
    _tx(db, conto, description="Troppo lontano", amount=25, type="income", date=day + timedelta(days=200))
    pairs = reversals.candidates()
    assert len(pairs) == 1 and (pairs[0].first, pairs[0].second) == (pay, far)  # the causale wins over the closest
    assert pairs[0].signal and pairs[0].days == 30 and pairs[0].key == f"{pay.id}-{far.id}"
    reversals.dismiss(far.id, pay.id)
    reversals.dismiss(far.id, pay.id)  # twice: kept once
    pairs = reversals.candidates()
    assert [(p.first, p.second) for p in pairs] == [(pay, near)] and not pairs[0].signal
    assert reversals.dismissed() == {f"{pay.id}-{far.id}"}
    assert reversals.candidates(ids=[near.id])[0].second == near
    assert reversals.auto_link([pay.id]) == 0  # no causale says so: only proposed


def test_auto_link_only_what_the_causale_names(db, conto):
    pay = _tx(db, conto, description="PAGAMENTO POS BAR", amount=Decimal("3.50"))
    back = _tx(db, conto, description="Annullamento operazione POS BAR", amount=Decimal("3.50"), type="income")
    assert reversals.says_reversal("Storno addebito") and not reversals.says_reversal("Stipendio", None)
    assert reversals.auto_link([back.id]) == 1
    assert pay.reversal_id == back.id


def test_partners_offered_on_a_transaction(db, conto):
    pay = _tx(db, conto, amount=12)
    same = _tx(db, conto, amount=12, type="income", date=date(2026, 6, 5))
    elsewhere = _tx(db, None, amount=12, type="income", date=date(2026, 6, 2))
    _tx(db, conto, amount=13, type="income")
    assert reversals.partners_for(pay) == [same, elsewhere]  # same account first
    reversals.link(pay, same)
    assert reversals.partners_for(pay) == []


def test_pages(client, db, conto):
    pay = _tx(db, conto, description="Pagamento palestra", amount=40, date=date.today())
    back = _tx(db, conto, description="Storno palestra", amount=40, type="income", date=date.today())
    html = client.get("/transactions/reversals").get_data(as_text=True)
    assert "Pagamento palestra" in html and "storno nella causale" in html and "Nessuno storno collegato" in html
    assert "/transactions/reversals" in client.get("/transactions/").get_data(as_text=True)
    page = client.get(f"/transactions/{pay.id}/edit").get_data(as_text=True)
    assert "Collega come storno" in page and "Storno palestra" in page
    response = client.post("/transactions/reversals/link", data={"first": pay.id, "second": back.id},
                           follow_redirects=True)
    assert "Storno collegato" in response.get_data(as_text=True)
    assert "stornato" in client.get("/transactions/").get_data(as_text=True)
    page = client.get(f"/transactions/{pay.id}/edit").get_data(as_text=True)
    assert "Si annulla con" in page and "Scollega lo storno" in page
    response = client.post("/transactions/reversals/link", data={"first": pay.id, "second": back.id},
                           follow_redirects=True)
    assert "già collegato" in response.get_data(as_text=True)
    client.post(f"/transactions/{pay.id}/reversal/unlink")
    db.session.refresh(pay)
    assert pay.reversal_id is None
    client.post("/transactions/reversals/dismiss", data={"first": pay.id, "second": back.id})
    assert "Nessun possibile storno" in client.get("/transactions/reversals").get_data(as_text=True)
    lonely = _tx(db, conto, description="Senza coppia", amount=999)
    assert "Nessun movimento dello stesso importo" in client.get(f"/transactions/{lonely.id}/edit").get_data(as_text=True)
    assert client.post("/transactions/reversals/link", data={"first": 0, "second": 1}).status_code == 404


def test_a_statement_with_a_reversal_links_it_on_import(client, db, conto):
    csv = ("Data;Descrizione;Importo\n"
           "01/11/2026;PAGAMENTO POS NEGOZIO SPORT;-50,00\n"
           "03/11/2026;STORNO PAGAMENTO POS NEGOZIO SPORT;50,00\n"
           "04/11/2026;PAGAMENTO POS LIBRERIA;-20,00\n"
           "06/11/2026;ACCREDITO DA LIBRERIA;20,00\n")
    html = client.post("/export/bank", data={"file": (io.BytesIO(csv.encode()), "movimenti.csv"), "bank": "auto"},
                       content_type="multipart/form-data").get_data(as_text=True)
    rows = sorted(set(re.findall(r'name="include" value="(\d+)"', html)), key=int)
    response = client.post("/export/bank/confirm", data=form_data(html, "preview-form", include=rows, account_id=conto.id),
                           follow_redirects=True)
    page = response.get_data(as_text=True)
    assert "1 storno riconosciuto e collegato" in page and "1 possibile storno da controllare" in page
    linked = Transaction.query.filter(Transaction.reversal_id.isnot(None)).all()
    assert {t.description for t in linked} == {"PAGAMENTO POS NEGOZIO SPORT", "STORNO PAGAMENTO POS NEGOZIO SPORT"}


def test_a_backup_keeps_the_reversals(client, db, conto, tmp_path, app):
    app.instance_path = str(tmp_path)
    pay = _tx(db, conto, description="Pagamento", amount=70)
    back = _tx(db, conto, description="Storno pagamento", amount=70, type="income")
    reversals.link(pay, back)
    db.session.commit()
    archive = client.get("/export/backup").data
    response = client.post("/export/restore", data={"file": (io.BytesIO(archive), "backup.zip"), "confirm": "1"},
                           content_type="multipart/form-data", follow_redirects=True)
    assert response.status_code == 200
    restored = Transaction.query.filter(Transaction.reversal_id.isnot(None)).order_by(Transaction.id).all()
    assert [(t.description, t.reversal_id) for t in restored] == [("Pagamento", back.id), ("Storno pagamento", pay.id)]
