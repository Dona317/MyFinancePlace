"""
Generate the fictitious data of this folder: a full backup (.zip) to restore from the app and a CSV of
transactions to import. Everything is invented (people, amounts, policy numbers).

    DATABASE_URL=postgresql://.../an_EMPTY_scratch_database python samples/dati_fittizi/genera.py

It needs an empty scratch database (it creates the tables and fills them); your real database is never touched.
The files are already in the folder: you only need this script to regenerate them.
"""
import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.account import Account  # noqa: E402
from app.models.budget import Budget  # noqa: E402
from app.models.transaction import Transaction  # noqa: E402
from app.models.wealth import Debt, Goal, Holding, InsurancePolicy  # noqa: E402
from app.services import backup, settings_store, transfer, wealth  # noqa: E402

HERE = Path(__file__).resolve().parent
MONTHS = 18
rng = random.Random(2026)


def month_starts(today: date) -> list[date]:
    first = today.replace(day=1)
    starts = []
    for back in range(MONTHS - 1, -1, -1):
        year, month = divmod(first.year * 12 + first.month - 1 - back, 12)
        starts.append(date(year, month + 1, 1))
    return starts


def money(low: float, high: float) -> Decimal:
    return Decimal(str(round(rng.uniform(low, high), 2)))


def fill(today: date) -> None:
    conto = Account(name="Conto corrente Fineco", kind="current", opening_balance=Decimal("4200"), iban_tail="4821")
    carta = Account(name="Carta di credito Visa", kind="card", opening_balance=0, iban_tail="0937")
    deposito = Account(name="Conto deposito Illimity", kind="savings", opening_balance=Decimal("8000"))
    contanti = Account(name="Contanti", kind="cash", opening_balance=Decimal("150"))
    db.session.add_all([conto, carta, deposito, contanti])

    mutuo = Debt(name="Mutuo casa — Intesa", type="Mutuo", principal=Decimal("180000"), annual_rate=Decimal("3.1"),
                 term_months=300, start_date=date(2022, 4, 1))
    auto = Debt(name="Prestito auto — Agos", type="Prestito Auto", principal=Decimal("14000"), annual_rate=Decimal("6.9"),
                term_months=60, start_date=date(2024, 9, 1))
    db.session.add_all([mutuo, auto])

    holdings = [
        Holding(name="Vanguard FTSE All-World", ticker="VWCE", asset_class="ETF", quantity=Decimal("120"),
                avg_price=Decimal("98.40"), current_price=Decimal("131.20"), price_date=today, purchase_date=date(2023, 3, 10)),
        Holding(name="iShares Core € Govt Bond", ticker="IEGA", asset_class="ETF", quantity=Decimal("60"),
                avg_price=Decimal("118.00"), current_price=Decimal("121.50"), price_date=today, purchase_date=date(2024, 1, 15)),
        Holding(name="BTP Italia 2030", ticker="IT0005497000", asset_class="Obbligazione", quantity=Decimal("50"),
                avg_price=Decimal("99.50"), current_price=Decimal("101.10"), price_date=today, purchase_date=date(2023, 6, 1)),
        Holding(name="Bitcoin", ticker="BTC", asset_class="Criptovaluta", quantity=Decimal("0.12"),
                avg_price=Decimal("41000"), current_price=Decimal("58500"), price_date=today, purchase_date=date(2024, 2, 5)),
        Holding(name="Appartamento Via Roma 12", asset_class="Immobile", quantity=1, avg_price=Decimal("235000"),
                current_price=Decimal("248000"), price_date=today, purchase_date=date(2022, 4, 1)),
        Holding(name="Fondo pensione Cometa", asset_class="Fondo Pensione", quantity=1,
                avg_price=Decimal("9400"), current_price=Decimal("10150"), price_date=today, purchase_date=date(2019, 1, 1)),
    ]
    db.session.add_all(holdings)

    db.session.add_all([
        InsurancePolicy(type="Auto", company="Genialloyd", policy_number="GA-2026-118842", premium=Decimal("540"),
                        frequency="annual", coverage_limit=Decimal("6070000"), start_date=today - timedelta(days=345),
                        expiry_date=today + timedelta(days=20)),
        InsurancePolicy(type="Casa", company="UnipolSai", policy_number="US-77120-B", premium=Decimal("24.50"),
                        frequency="monthly", coverage_limit=Decimal("250000"), start_date=date(2022, 4, 1),
                        expiry_date=date(2032, 4, 1)),
        InsurancePolicy(type="Vita", company="Generali", policy_number="GEN-TCM-5521", premium=Decimal("180"),
                        frequency="biannual", coverage_limit=Decimal("200000"), start_date=date(2022, 4, 1)),
    ])
    db.session.add_all([
        Goal(name="Fondo d'emergenza", target_amount=Decimal("12000"), saved_amount=Decimal("7800"),
             target_date=today + timedelta(days=270), notes="Sul conto deposito"),
        Goal(name="Vacanza in Giappone", target_amount=Decimal("5000"), saved_amount=Decimal("1900"),
             target_date=today + timedelta(days=200)),
        Goal(name="Cambio auto", target_amount=Decimal("15000"), saved_amount=Decimal("2500")),
    ])
    db.session.add_all([
        Budget(category="Alimentari", amount=Decimal("420")), Budget(category="Ristoranti", amount=Decimal("150")),
        Budget(category="Svago", amount=Decimal("120")), Budget(category="Trasporti", amount=Decimal("180")),
        Budget(category="Abbonamenti", amount=Decimal("45")), Budget(category="Shopping", amount=Decimal("150")),
    ])
    db.session.flush()

    txs = []

    def add(day, description, amount, kind, category, counterparty=None, account=conto, **extra):
        if day > today:
            return
        txs.append(Transaction(date=day, description=description, amount=Decimal(amount), currency="EUR", type=kind,
                               category=category, counterparty=counterparty or description, tags=extra.pop("tags", []),
                               account_id=account.id, **extra))

    for start in month_starts(today):
        m = start.month
        add(start.replace(day=27), "Stipendio ACME S.p.A.", "2450.00" if m != 12 else "4900.00", "income", "Stipendio",
            "ACME S.p.A.", is_recurring=True, recurrence="monthly")
        if m in (3, 9):
            add(start.replace(day=15), "Fattura consulenza", money(600, 1200), "income", "Lavoro autonomo", "Studio Rossi",
                tags=["lavoro"])
        add(start.replace(day=1), "Rata mutuo", "858.40", "expense", "Casa", "Intesa Sanpaolo", debt_id=mutuo.id,
            is_recurring=True, recurrence="monthly")
        add(start.replace(day=5), "Rata prestito auto", "276.60", "expense", "Prestiti", "Agos", debt_id=auto.id,
            is_recurring=True, recurrence="monthly")
        add(start.replace(day=8), "Enel Energia — bolletta luce e gas", money(70, 190) if m in (11, 12, 1, 2) else money(45, 85),
            "expense", "Bollette", "Enel Energia", is_recurring=True, recurrence="monthly")
        add(start.replace(day=12), "TIM fibra", "29.90", "expense", "Bollette", "TIM", is_recurring=True, recurrence="monthly")
        add(start.replace(day=3), "Netflix", "13.99", "expense", "Abbonamenti", "Netflix", account=carta,
            is_recurring=True, recurrence="monthly")
        add(start.replace(day=18), "Spotify", "10.99", "expense", "Abbonamenti", "Spotify", account=carta,
            is_recurring=True, recurrence="monthly")
        add(start.replace(day=20), "Palestra FitActive", "34.90", "expense", "Salute", "FitActive",
            is_recurring=True, recurrence="monthly")
        add(start.replace(day=2), "Giroconto conto deposito", "300.00", "transfer", "Risparmio", "Illimity",
            counter_account_id=deposito.id)
        add(start.replace(day=10), "Versamento fondo pensione", "100.00", "expense", "Investimenti", "Cometa",
            holding_id=holdings[5].id)
        for week in range(4):
            day = start + timedelta(days=week * 7 + rng.randint(0, 5))
            if day.month != m:
                continue
            add(day, rng.choice(["Esselunga", "Coop", "Conad", "Lidl"]), money(35, 110), "expense", "Alimentari")
            if rng.random() < 0.6:
                add(day + timedelta(days=1), rng.choice(["Ristorante Da Mario", "Pizzeria Napoli", "Sushi Ko", "Bar Centrale"]),
                    money(12, 70), "expense", "Ristoranti", account=carta)
            if rng.random() < 0.5:
                add(day + timedelta(days=2), rng.choice(["Eni carburante", "Q8", "IP Station"]), money(40, 75),
                    "expense", "Trasporti")
        if rng.random() < 0.7:
            add(start.replace(day=rng.randint(6, 26)), rng.choice(["Amazon", "Zalando", "Decathlon", "IKEA"]),
                money(20, 160), "expense", "Shopping", account=carta)
        if rng.random() < 0.5:
            add(start.replace(day=rng.randint(6, 26)), rng.choice(["Cinema UCI", "Teatro", "Concerto", "Libreria Feltrinelli"]),
                money(10, 60), "expense", "Svago", account=carta)
        if rng.random() < 0.35:
            add(start.replace(day=rng.randint(6, 26)), rng.choice(["Farmacia", "Visita dentista", "Ottico"]),
                money(15, 180), "expense", "Salute", tags=["detraibile"])
        add(start.replace(day=rng.randint(3, 25)), "Prelievo bancomat", "100.00", "transfer", "Contanti", "Bancomat",
            counter_account_id=contanti.id)
        if m == 8:
            add(start.replace(day=9), "Volo e hotel vacanze", money(900, 1400), "expense", "Viaggi", "Booking.com", account=carta)
        if m == 12:
            add(start.replace(day=15), "Regali di Natale", money(250, 450), "expense", "Shopping", "Vari", account=carta)
        if m == 4:
            add(start.replace(day=11), "Dividendo VWCE", money(35, 60), "income", "Dividendi", "Vanguard", account=deposito)
        if m in (1, 7):
            add(start.replace(day=25), "Premio polizza vita", "180.00", "expense", "Assicurazioni", "Generali")
        add(start.replace(day=1), "Premio assicurazione casa", "24.50", "expense", "Assicurazioni", "UnipolSai",
            is_recurring=True, recurrence="monthly")

    # the card is paid off from the current account at the start of the following month
    for start in month_starts(today)[1:]:
        prev_end = start
        prev_start = (start - timedelta(days=1)).replace(day=1)
        spent = sum(t.amount for t in txs if t.account_id == carta.id and prev_start <= t.date < prev_end)
        add(start.replace(day=15), "Addebito estratto carta Visa", f"{spent:.2f}", "transfer", "Carta di credito", "Visa",
            counter_account_id=carta.id)

    db.session.add_all(txs)
    settings_store.set(wealth.OPENING_CASH_SETTING, "0")
    db.session.commit()

    firsts = month_starts(today)
    for on in (firsts[-12] - timedelta(days=1), firsts[-6] - timedelta(days=1)):
        wealth.take_snapshot(f"Fine {on:%m/%Y}", on)
    wealth.take_snapshot("Oggi")
    db.session.commit()
    print(f"{len(txs)} transactions from {firsts[0]} to {today}")


def main() -> None:
    app = create_app()
    with app.app_context():
        if db.inspect(db.engine).get_table_names():
            sys.exit("The database is not empty: use an empty scratch database (see the top of this file).")
        db.create_all()
        fill(date.today())
        (HERE / "backup_completo_demo.zip").write_bytes(backup.create_archive())
        rows = transfer.query_transactions()
        (HERE / "transazioni_demo.csv").write_text("﻿" + transfer.to_csv(rows), encoding="utf-8")
    print("written:", *(p.name for p in sorted(HERE.glob("*demo*"))))


if __name__ == "__main__":
    main()
