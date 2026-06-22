"""
Run with:  python seed.py
Wipes all existing data and inserts fresh test records.
"""
from datetime import date
from app import create_app
from app.extensions import db
from app.models.transaction import Transaction

app = create_app()

TRANSACTIONS = [
    Transaction(
        date=date(2026, 6, 1),
        description="Stipendio giugno",
        amount=2800.00,
        currency="EUR",
        type="income",
        category="Stipendio",
        counterparty="Datore di lavoro",
        tags=["stipendio"],
        is_recurring=True,
        recurrence="monthly",
        notes=None,
    ),
    Transaction(
        date=date(2026, 6, 3),
        description="Spesa al supermercato",
        amount=87.50,
        currency="EUR",
        type="expense",
        category="Alimentari",
        counterparty="Esselunga",
        tags=["cibo", "casa"],
        is_recurring=False,
        notes=None,
    ),
    Transaction(
        date=date(2026, 6, 5),
        description="Abbonamento Netflix",
        amount=17.99,
        currency="EUR",
        type="expense",
        category="Abbonamenti",
        counterparty="Netflix",
        tags=["svago", "deducibile"],
        is_recurring=True,
        recurrence="monthly",
        notes=None,
    ),
    Transaction(
        date=date(2026, 6, 10),
        description="Benzina",
        amount=65.00,
        currency="EUR",
        type="expense",
        category="Trasporto",
        counterparty="ENI",
        tags=["auto"],
        is_recurring=False,
        notes="Pieno completo",
    ),
    Transaction(
        date=date(2026, 6, 15),
        description="Freelance progetto web",
        amount=500.00,
        currency="EUR",
        type="income",
        category="Freelance",
        counterparty="Cliente ABC",
        tags=["freelance", "deducibile"],
        is_recurring=False,
        notes="Fattura #2026-012",
    ),
]


def seed():
    with app.app_context():
        print("Tables cleaning...")
        Transaction.query.delete()
        db.session.commit()

        print("Test data seeding...")
        db.session.add_all(TRANSACTIONS)
        db.session.commit()

        print(f"Done — {len(TRANSACTIONS)} transactions inserted.")


if __name__ == "__main__":
    seed()
