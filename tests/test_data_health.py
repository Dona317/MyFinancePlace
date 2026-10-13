"""F20a: the data health checks, the page that lists them and the reminders for the serious ones."""
from datetime import date
from decimal import Decimal

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import data_health, notifications
from tests.conftest import make_tx

TODAY = date(2026, 10, 13)


def _by_key(checks):
    return {check.key: check for check in checks}


def test_clean_archive(app, db):
    with app.test_request_context():
        checks = data_health.run(TODAY)
    assert all(check.count == 0 for check in checks)
    assert [c.key for c in checks][:2] == ["oversold", "rates"]  # nothing found: by seriousness
    with app.test_request_context():
        assert data_health.severe(TODAY) == []


def test_every_check_finds_its_problem(app, db):
    current = Account(name="Corrente", kind="current", reconciled_on=date(2026, 9, 30))
    old = Account(name="Vecchio", kind="savings")
    db.session.add_all([current, old,
                        Holding(name="Sbagliato", asset_class="ETF", isin="IE00B4L5Y983", quantity=-2, avg_price=10,
                                price_date=TODAY),
                        Holding(name="Vecchio prezzo", asset_class="Azione", ticker="ENEL.MI", quantity=5, avg_price=6,
                                price_date=date(2026, 9, 1)),
                        Holding(name="Senza codici", asset_class="Fondo", quantity=1, avg_price=100),
                        Holding(name="Manuale", asset_class="Fondo", quantity=1, avg_price=100, price_source="manual"),
                        Holding(name="Casa", asset_class="Immobile", quantity=1, avg_price=1)])
    db.session.flush()
    db.session.add_all([
        make_tx(description="Giroconto a metà", type="transfer", category="Giroconto", account_id=current.id),
        make_tx(description="Cena a Londra", currency="GBP", amount=Decimal("40"), category="Ristoranti"),
        make_tx(description="Boh", category="Altro", date=date(2026, 9, 1)),
        make_tx(description="PAGAMENTO POS ESSELUNGA", amount=Decimal("50"), date=date(2026, 9, 2), category="Spesa"),
        make_tx(description="PAGAMENTO POS ESSELUNGA", amount=Decimal("50"), date=date(2026, 9, 3), category="Spesa"),
    ])
    db.session.commit()
    with app.test_request_context():
        checks = _by_key(data_health.run(TODAY))
        severe = data_health.severe(TODAY)
    assert {k: c.count for k, c in checks.items()} == {
        "oversold": 1, "rates": 1, "stale": 2, "transfers": 1, "duplicates": 1, "uncategorized": 1,
        "unpriceable": 1, "reconcile": 1}
    assert checks["stale"].items[1].label == "Vecchio prezzo — 01/09/2026"
    assert checks["stale"].items[0].label.endswith("mai")  # «Senza codici» was never priced
    assert [c.key for c in severe] == ["oversold", "rates"]
    assert checks["reconcile"].items[0].label == "Vecchio — mai"
    with app.test_request_context():
        keys = [n.key for n in notifications.collect(TODAY)]
    assert "health-oversold-1" in keys and "health-rates-1" in keys


def test_page(client, db):
    page = client.get("/data-health/").get_data(as_text=True)
    assert "Nessun problema che cambi i numeri." in page and "Salute dei dati" in page
    db.session.add(Holding(name="Sbagliato", asset_class="ETF", quantity=-2, avg_price=10))
    db.session.add_all([make_tx(description=f"Giroconto {i}", type="transfer", category="Giroconto") for i in range(22)])
    db.session.commit()
    page = client.get("/data-health/").get_data(as_text=True)
    assert "controlli hanno trovato qualcosa da sistemare." in page and "e altri 2" in page
    assert Transaction.query.count() == 22
