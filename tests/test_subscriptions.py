"""F9: the Abbonamenti page — recurring series, their cost, next charge and price changes."""
from datetime import date

from app.models.transaction import Transaction
from app.services import subscriptions
from tests.conftest import make_tx

TODAY = date(2026, 6, 20)


def _netflix(db, amounts=(12.99, 12.99, 15.99), flagged=True):
    """Netflix on the 5th of March, April, May…; only the latest flagged as recurring (as the form does)."""
    txs = [make_tx(date=date(2026, 3 + k, 5), description="Netflix abbonamento", amount=a, category="Abbonamenti")
           for k, a in enumerate(amounts)]
    txs[-1].is_recurring, txs[-1].recurrence = flagged, "monthly" if flagged else None
    db.session.add_all(txs)
    db.session.commit()
    return txs[-1]


def test_a_flagged_series_with_cost_next_charge_and_price_change(app, db):
    _netflix(db)
    db.session.add(make_tx(date=date(2026, 1, 15), description="Assicurazione auto", amount=600, category="Assicurazioni",
                           is_recurring=True, recurrence="yearly"))
    db.session.commit()
    with app.test_request_context():
        data = subscriptions.overview("expense", TODAY)
    insurance, netflix = data["series"]  # the dearest a month first
    assert netflix.template.description == "Netflix abbonamento" and netflix.confirmed and netflix.count == 3
    assert netflix.amount == 15.99 and netflix.change == 3.0 and netflix.next_date == date(2026, 7, 5)
    assert insurance.monthly == 50.0 and insurance.yearly == 600.0 and insurance.next_date == date(2027, 1, 15)
    assert insurance.change is None and str(insurance.frequency_label) == "Annuale"
    assert round(data["monthly"], 2) == 65.99 and data["count"] == 2 and data["increases"] == 1
    assert data["upcoming"] == 15.99  # only Netflix falls in the next 30 days


def test_detected_series_are_offered_for_confirmation(app, db):
    _netflix(db, amounts=(9.99, 9.99, 9.99), flagged=False)
    db.session.add(make_tx(date=date(2026, 6, 1), description="Stipendio", amount=2000, type="income", category="Stipendio",
                           is_recurring=True, recurrence="monthly"))
    db.session.commit()
    with app.test_request_context():
        data = subscriptions.overview("expense", TODAY)
        income = subscriptions.overview("income", TODAY)
    [netflix] = data["series"]
    assert not netflix.confirmed and netflix.frequency == "monthly" and netflix.next_date == date(2026, 6, 5)
    assert data["to_confirm"] == 1 and data["upcoming"] == 0  # its next date is already past
    assert [s.template.description for s in income["series"]] == ["Stipendio"]


def test_stop_and_resume(client, db):
    tx = _netflix(db)
    response = client.post(f"/subscriptions/{tx.id}/stop")
    assert response.status_code == 302 and db.session.get(Transaction, tx.id).recurrence_end == tx.date
    html = client.get("/subscriptions/").get_data(as_text=True)
    assert "Terminati (1)" in html and "Riattiva" in html
    client.post(f"/subscriptions/{tx.id}/resume")
    assert db.session.get(Transaction, tx.id).recurrence_end is None


def test_confirm_from_the_page_comes_back_to_it(client, db):
    tx = _netflix(db, amounts=(9.99, 9.99, 9.99), flagged=False)
    response = client.post(f"/forecast/recurring/{tx.id}", data={"frequency": "monthly", "next": "/subscriptions/"})
    assert response.headers["Location"].endswith("/subscriptions/")
    assert db.session.get(Transaction, tx.id).is_recurring
    for outside in ("//evil.example", "/\\evil.example"):  # browsers read /\ as // : another site
        response = client.post(f"/forecast/recurring/{tx.id}", data={"frequency": "monthly", "next": outside})
        assert response.headers["Location"].endswith("/forecast/")


def test_pages(client, db):
    assert "Nessuna serie ricorrente" in client.get("/subscriptions/").get_data(as_text=True)
    _netflix(db)
    html = client.get("/subscriptions/").get_data(as_text=True)
    assert "Netflix abbonamento" in html and "Non più attivo" in html and "+€ 3,00" in html
    assert "Entrate ricorrenti" in client.get("/subscriptions/?kind=income").get_data(as_text=True)
    assert client.get("/subscriptions/?kind=boh").status_code == 200
