"""
Tests run against a real PostgreSQL database (the models use ARRAY columns).

    createdb myfinanceplace_test          # once
    TEST_DATABASE_URL=postgresql://sa:Pa55w0rd@localhost:5332/myfinanceplace_test pytest
"""
from datetime import date

import pytest

from app import create_app
from app.extensions import db as _db
from app.models.transaction import Transaction


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        _db.drop_all()
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return _db


def make_tx(**overrides) -> Transaction:
    values = dict(
        date=date(2026, 6, 1), description="Test", amount=10, currency="EUR",
        type="expense", category="Altro", tags=[], is_recurring=False,
    )
    values.update(overrides)
    return Transaction(**values)


@pytest.fixture()
def sample_data(db):
    """June 2026: 3000 income, 800 expenses; May 2026: 2800 income, 600 expenses."""
    db.session.add_all([
        make_tx(date=date(2026, 6, 1),  description="Stipendio", amount=3000, type="income", category="Stipendio"),
        make_tx(date=date(2026, 6, 3),  description="Affitto",   amount=600,  category="Casa"),
        make_tx(date=date(2026, 6, 10), description="Spesa",     amount=150,  category="Alimentari", counterparty="Esselunga"),
        make_tx(date=date(2026, 6, 12), description="Netflix",   amount=50,   category="Abbonamenti", tags=["deducibile"]),
        make_tx(date=date(2026, 6, 20), description="ETF",       amount=500,  type="transfer", category="Investimenti"),
        make_tx(date=date(2026, 5, 1),  description="Stipendio", amount=2800, type="income", category="Stipendio"),
        make_tx(date=date(2026, 5, 3),  description="Affitto",   amount=600,  category="Casa"),
        make_tx(date=date(2025, 12, 1), description="Bonus",     amount=1000, type="income", category="Bonus"),
    ])
    db.session.commit()
