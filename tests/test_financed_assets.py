"""F20d: a debt linked to the asset it financed (mortgage → house): value, what is owed, the equity."""
from datetime import date

from app.models.wealth import Debt, Holding
from app.services import wealth


def _house(db):
    house = Holding(name="Casa", asset_class="Immobile", quantity=1, avg_price=250000, current_price=300000)
    car = Holding(name="Auto", asset_class="Altro", quantity=1, avg_price=20000, current_price=8000)
    db.session.add_all([house, car])
    db.session.flush()
    mortgage = Debt(name="Mutuo", type="Mutuo", principal=200000, balance=180000, holding_id=house.id)
    loan = Debt(name="Prestito auto", type="Prestito Auto", principal=15000, balance=10000, holding_id=car.id)
    other = Debt(name="Carta", type="Carta di Credito", principal=500, balance=500)
    db.session.add_all([mortgage, loan, other])
    db.session.commit()
    return house, car, mortgage, loan


def test_equity(app, db):
    house, car, mortgage, loan = _house(db)
    with app.test_request_context():
        rows = {r["holding"].name: r for r in wealth.financed_assets(date(2026, 10, 13))}
    assert set(rows) == {"Casa", "Auto"}
    assert (rows["Casa"]["owed"], rows["Casa"]["equity"], rows["Casa"]["owned_pct"]) == (180000, 120000, 40.0)
    assert (rows["Auto"]["equity"], rows["Auto"]["debts"]) == (-2000, [loan])  # owes more than it is worth


def test_pages(client, db):
    house, car, mortgage, loan = _house(db)
    assert "€ 120.000,00" in client.get(f"/debt/{mortgage.id}").get_data(as_text=True)
    assert "Finanziato con un debito" in client.get(f"/portfolio/{house.id}").get_data(as_text=True)
    assert "Beni acquistati con un debito" in client.get("/accounting/balance-sheet").get_data(as_text=True)
    page = client.get(f"/debt/{mortgage.id}/edit").get_data(as_text=True)
    assert f'<option value="{house.id}" selected>Casa</option>' in page
    form = {"name": "Mutuo", "type": "Mutuo", "principal": "200000", "annual_rate": "3", "term_months": "300",
            "balance": "180000", "holding_id": ""}
    client.post(f"/debt/{mortgage.id}/edit", data=form)
    assert db.session.get(Debt, mortgage.id).holding_id is None
    client.post(f"/debt/{mortgage.id}/edit", data={**form, "holding_id": str(car.id)})
    assert db.session.get(Debt, mortgage.id).holding_id == car.id
    db.session.delete(car)
    db.session.commit()
    assert db.session.get(Debt, mortgage.id).holding_id is None  # the asset sold: the debt stays
