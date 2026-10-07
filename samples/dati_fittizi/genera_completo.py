"""
The complete fictitious dataset: three years of one household on FOUR linked accounts, to try every page of the app.

    DATABASE_URL=postgresql://.../an_EMPTY_scratch_database python samples/dati_fittizi/genera_completo.py

Accounts and how they are linked (every link is a «giroconto», a transfer between own accounts):
- Conto corrente Fineco: salary, mortgage, bills, groceries; pays the credit card every month, puts money aside on
  the savings account and on the broker account
- Carta di credito Visa: restaurants, shopping, subscriptions, holidays (one in US dollars); paid off on the 15th
- Conto deposito Illimity: monthly saving, quarterly interest, a withdrawal back to the current account each summer
- Conto titoli Directa: monthly PAC (ETF bought on the 12th), quarterly dividends

The data has: salary raises, a yearly bonus and the «tredicesima»; seasonal bills; yearly costs (car insurance, car
tax, TARI); subscriptions with price increases and one cancelled; a few split purchases; a payment in USD; budgets,
goals, debts, holdings, policies and snapshots every six months.

Written next to this file:
- backup_completo_3anni.zip — everything up to the end of the month before last (Esporta → Backup completo → Ripristina)
- transazioni_3anni.csv — the same transactions (Esporta → Importa CSV con mappatura)
- estratti_da_importare/ — last month and the current one of each account, each in a different import format, to
  import after the restore: CSV (current account), OFX (card), CAMT.053 (savings, with balances), QIF (broker)
"""
from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.account import Account  # noqa: E402
from app.models.budget import Budget  # noqa: E402
from app.models.currency import ExchangeRate  # noqa: E402
from app.models.transaction import Transaction, TransactionSplit  # noqa: E402
from app.models.wealth import Debt, Goal, Holding, InsurancePolicy  # noqa: E402
from app.services import backup, settings_store, transfer, wealth  # noqa: E402

HERE = Path(__file__).resolve().parent
STATEMENTS = HERE / "estratti_da_importare"
YEARS = 3
SEED = 3036
USD_RATE = Decimal("0.92")  # 1 USD in EUR, the same every month: a fixed rate keeps the data reproducible

ACCOUNTS = {  # key: (name, kind, opening balance, last IBAN digits)
    "conto": ("Conto corrente Fineco", "current", Decimal("3500"), "4821"),
    "carta": ("Carta di credito Visa", "card", Decimal("0"), "0937"),
    "deposito": ("Conto deposito Illimity", "savings", Decimal("5000"), "7710"),
    "titoli": ("Conto titoli Directa", "other", Decimal("0"), "2203"),
}


@dataclass
class Move:
    """One movement before it becomes a Transaction: amounts are positive, `type` gives the direction."""
    date: date
    description: str
    amount: Decimal
    type: str                     # income | expense | transfer
    category: str
    account: str                  # key of ACCOUNTS: where the money leaves (or arrives, for income)
    to: str | None = None         # transfer: where it arrives
    counterparty: str | None = None
    currency: str = "EUR"
    recurrence: str | None = None
    recurrence_end: date | None = None
    splits: list = field(default_factory=list)
    holding: str | None = None
    debt: str | None = None
    tags: list = field(default_factory=list)

    def euro(self) -> Decimal:
        return (self.amount * USD_RATE).quantize(Decimal("0.01")) if self.currency == "USD" else self.amount

    def effect(self, account: str) -> Decimal:
        """What this movement does to the balance of `account` (in euro)."""
        if self.type == "income":
            return self.euro() if self.account == account else Decimal(0)
        change = Decimal(0)
        if self.account == account:
            change -= self.euro()
        if self.type == "transfer" and self.to == account:
            change += self.euro()
        return change


def months(first: date, last: date):
    day = first.replace(day=1)
    while day <= last:
        yield day
        day = date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def movements(today: date) -> list[Move]:
    """Every movement from the same month YEARS ago to `today`, deterministic for a given `today`."""
    rng = random.Random(SEED)
    first = date(today.year - YEARS, today.month, 1)
    moves: list[Move] = []

    def money(low, high) -> Decimal:
        return Decimal(str(round(rng.uniform(low, high), 2)))

    def add(day: date, description, amount, kind, category, account="conto", **extra):
        if first <= day <= today:
            moves.append(Move(day, description, Decimal(str(amount)), kind, category, account, **extra))

    for start in months(first, today):
        y, m = start.year, start.month
        salary = 2300 if y < today.year - 1 else 2450 if y == today.year - 1 else 2600  # a raise every January
        add(start.replace(day=27), "Stipendio ACME S.p.A.", salary * (2 if m == 12 else 1), "income", "Stipendio",
            counterparty="ACME S.p.A.", recurrence="monthly")
        if m == 3:
            add(start.replace(day=27), "Premio di produzione ACME", money(800, 1500), "income", "Bonus e premi",
                counterparty="ACME S.p.A.")
        if m in (2, 6, 10) and rng.random() < 0.8:
            add(start.replace(day=rng.randint(8, 22)), "Fattura consulenza Studio Bianchi", money(400, 1200), "income",
                "Freelance", counterparty="Studio Bianchi", tags=["lavoro"])

        # fixed costs on the current account
        add(start.replace(day=1), "Rata mutuo Intesa Sanpaolo", "858.40", "expense", "Mutuo", counterparty="Intesa Sanpaolo",
            recurrence="monthly", debt="mutuo")
        if start >= date(2024, 9, 1):
            add(start.replace(day=5), "Rata prestito auto Agos", "276.60", "expense", "Prestiti", counterparty="Agos",
                recurrence="monthly", debt="auto")
        winter = m in (11, 12, 1, 2, 3)
        add(start.replace(day=8), "Enel Energia bolletta luce e gas", money(110, 210) if winter else money(45, 85),
            "expense", "Bollette", counterparty="Enel Energia", recurrence="monthly")
        tim = "32.90" if start >= date(2025, 6, 1) else "29.90"  # a price increase
        add(start.replace(day=12), "TIM fibra casa", tim, "expense", "Internet e telefono", counterparty="TIM",
            recurrence="monthly")
        add(start.replace(day=18), "Iliad ricarica mobile", "9.99", "expense", "Internet e telefono", counterparty="Iliad",
            recurrence="monthly")
        add(start.replace(day=20), "Palestra FitActive", "34.90", "expense", "Palestra", counterparty="FitActive",
            recurrence="monthly")
        add(start.replace(day=3), "Premio assicurazione casa UnipolSai", "24.50", "expense", "Assicurazioni",
            counterparty="UnipolSai", recurrence="monthly")

        # subscriptions on the card
        netflix = "15.99" if start >= date(2026, 2, 1) else "13.99" if start >= date(2024, 10, 1) else "12.99"
        add(start.replace(day=4), "Netflix abbonamento", netflix, "expense", "Streaming", "carta", counterparty="Netflix",
            recurrence="monthly")
        add(start.replace(day=6), "Spotify Premium", "10.99", "expense", "Streaming", "carta", counterparty="Spotify",
            recurrence="monthly")
        if start <= date(2025, 4, 1):  # cancelled: its last payment ends the series
            add(start.replace(day=9), "Disney Plus", "8.99", "expense", "Streaming", "carta", counterparty="Disney+",
                recurrence="monthly", recurrence_end=date(2025, 4, 9) if start == date(2025, 4, 1) else None)
        if m == 10:
            add(start.replace(day=14), "Amazon Prime rinnovo annuale", "49.90", "expense", "Abbonamenti", "carta",
                counterparty="Amazon", recurrence="yearly")

        # yearly and seasonal costs
        if m == 2:
            add(start.replace(day=10), "Genialloyd polizza auto", money(520, 560), "expense", "Assicurazioni",
                counterparty="Genialloyd", recurrence="yearly")
        if m == 1:
            add(start.replace(day=28), "Bollo auto ACI", "286.00", "expense", "Tasse e imposte", counterparty="ACI")
        if m in (5, 11):
            add(start.replace(day=16), "TARI rata comune", money(140, 160), "expense", "Tasse e imposte",
                counterparty="Comune di Milano")
        if m == 8:
            add(start.replace(day=3), "Volo e hotel vacanze Puglia", money(900, 1500), "expense", "Viaggi", "carta",
                counterparty="Booking.com")
        if m == 4 and y >= today.year - 1:
            add(start.replace(day=22), "Hotel New York Manhattan", money(600, 800), "expense", "Viaggi", "carta",
                counterparty="Hilton", currency="USD", tags=["viaggio"])
        if m == 12:
            add(start.replace(day=12), "Regali di Natale", money(250, 450), "expense", "Regali e donazioni", "carta",
                counterparty="Vari")

        # everyday spending
        for week in range(4):
            day = start + timedelta(days=week * 7 + rng.randint(0, 5))
            if day.month != m:
                continue
            shop = rng.choice(["Esselunga", "Coop", "Conad", "Lidl"])
            amount = money(35, 120)
            extra = {}
            if week == 0 and rng.random() < 0.35:  # the big monthly shop with household goods: split
                home = (amount * Decimal("0.3")).quantize(Decimal("0.01"))
                extra["splits"] = [("Alimentari", amount - home), ("Casa", home)]
            add(day, f"{shop} spesa", amount, "expense", "Alimentari", counterparty=shop, **extra)
            if rng.random() < 0.6:
                place = rng.choice(["Ristorante Da Mario", "Pizzeria Napoli", "Sushi Ko", "Trattoria Milanese"])
                add(day + timedelta(days=1), place, money(18, 80), "expense", "Ristoranti", "carta", counterparty=place)
            if rng.random() < 0.6:
                add(day + timedelta(days=2), "Bar Centrale colazione", money(2, 9), "expense", "Bar e caffè", "carta",
                    counterparty="Bar Centrale")
            if rng.random() < 0.5:
                fuel = rng.choice(["Eni", "Q8", "IP"])
                add(day + timedelta(days=3), f"{fuel} carburante", money(40, 75), "expense", "Carburante",
                    counterparty=fuel)
        if rng.random() < 0.7:
            shop = rng.choice(["Amazon", "Zalando", "Decathlon", "IKEA"])
            add(start.replace(day=rng.randint(6, 26)), f"{shop} acquisto", money(20, 180), "expense", "Shopping", "carta",
                counterparty=shop)
        if rng.random() < 0.5:
            fun = rng.choice(["Cinema UCI", "Teatro alla Scala", "Concerto Forum", "Libreria Feltrinelli"])
            add(start.replace(day=rng.randint(6, 26)), fun, money(10, 70), "expense", "Svago", "carta", counterparty=fun)
        if rng.random() < 0.35:
            care = rng.choice(["Farmacia Comunale", "Visita dentista", "Ottico Salmoiraghi"])
            add(start.replace(day=rng.randint(6, 26)), care, money(15, 180), "expense", "Salute", counterparty=care,
                tags=["detraibile"])

        # the links between the accounts
        add(start.replace(day=2), "Giroconto verso conto deposito", "300.00", "transfer", "Giroconto", to="deposito",
            counterparty="Illimity")
        add(start.replace(day=10), "Giroconto verso conto titoli", "250.00", "transfer", "Giroconto", to="titoli",
            counterparty="Directa")
        add(start.replace(day=12), "Acquisto ETF VWCE (PAC)", "240.00", "transfer", "Investimenti", "titoli",
            counterparty="Vanguard", holding="vwce")
        add(start.replace(day=12), "Commissione ordine Directa", "1.50", "expense", "Commissioni", "titoli",
            counterparty="Directa")
        if m in (3, 6, 9, 12):
            add(start.replace(day=30 if m != 2 else 28), "Interessi maturati conto deposito", money(25, 45), "income",
                "Interessi", "deposito", counterparty="Illimity")
            add(start.replace(day=15), "Dividendo VWCE", money(30, 70), "income", "Dividendi e cedole", "titoli",
                counterparty="Vanguard")
        if m == 7:
            add(start.replace(day=20), "Giroconto da conto deposito per vacanze", "1200.00", "transfer", "Giroconto",
                "deposito", to="conto", counterparty="Illimity")

    # the card is paid off from the current account on the 15th of the following month
    for start in list(months(first, today))[1:]:
        previous = (start - timedelta(days=1)).replace(day=1)
        spent = sum((mv.euro() for mv in moves if mv.account == "carta" and mv.type == "expense"
                     and previous <= mv.date < start), Decimal(0))
        if spent:
            add(start.replace(day=15), "Addebito estratto conto carta Visa", spent, "transfer", "Giroconto", to="carta",
                counterparty="Visa")
    moves.sort(key=lambda mv: (mv.date, mv.description))
    return moves


def balance(moves: list[Move], account: str, before: date) -> Decimal:
    return ACCOUNTS[account][2] + sum((mv.effect(account) for mv in moves if mv.date < before), Decimal(0))


# ── The database: everything up to the end of the month before last ────────────

def fill(today: date) -> dict:
    """Write the movements before last month, and the rest of the household, into the (empty) database: last month
    and the current one are left to the statements, as if the bank files were still to be imported."""
    moves = movements(today)
    cutoff = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    accounts = {key: Account(name=name, kind=kind, opening_balance=opening, iban_tail=tail)
                for key, (name, kind, opening, tail) in ACCOUNTS.items()}
    debts = {
        "mutuo": Debt(name="Mutuo casa — Intesa", type="Mutuo", principal=Decimal("180000"), annual_rate=Decimal("3.1"),
                      term_months=300, start_date=date(2022, 4, 1)),
        "auto": Debt(name="Prestito auto — Agos", type="Prestito Auto", principal=Decimal("14000"),
                     annual_rate=Decimal("6.9"), term_months=60, start_date=date(2024, 9, 1)),
    }
    bought = sum((mv.amount for mv in moves if mv.holding == "vwce" and mv.date < cutoff), Decimal(0))
    holdings = {
        "vwce": Holding(name="Vanguard FTSE All-World", ticker="VWCE", asset_class="ETF",
                        quantity=(bought / Decimal("112")).quantize(Decimal("0.0001")), avg_price=Decimal("112"),
                        current_price=Decimal("131.20"), price_date=today, purchase_date=date(today.year - YEARS, today.month, 12)),
        "btp": Holding(name="BTP Italia 2030", ticker="IT0005497000", asset_class="Obbligazione", quantity=Decimal("50"),
                       avg_price=Decimal("99.50"), current_price=Decimal("101.10"), price_date=today, purchase_date=date(2023, 6, 1)),
        "casa": Holding(name="Appartamento Via Roma 12", asset_class="Immobile", quantity=1, avg_price=Decimal("235000"),
                        current_price=Decimal("248000"), price_date=today, purchase_date=date(2022, 4, 1)),
        "pensione": Holding(name="Fondo pensione Cometa", asset_class="Fondo Pensione", quantity=1, avg_price=Decimal("9400"),
                            current_price=Decimal("10150"), price_date=today, purchase_date=date(2019, 1, 1)),
    }
    db.session.add_all([*accounts.values(), *debts.values(), *holdings.values()])
    db.session.add_all([
        InsurancePolicy(type="Auto", company="Genialloyd", policy_number="GA-2026-118842", premium=Decimal("540"),
                        frequency="annual", coverage_limit=Decimal("6070000"), start_date=date(today.year, 2, 10),
                        expiry_date=date(today.year + 1, 2, 10)),
        InsurancePolicy(type="Casa", company="UnipolSai", policy_number="US-77120-B", premium=Decimal("24.50"),
                        frequency="monthly", coverage_limit=Decimal("250000"), start_date=date(2022, 4, 1),
                        expiry_date=date(2032, 4, 1)),
        Goal(name="Fondo d'emergenza", target_amount=Decimal("15000"), saved_amount=Decimal("9000"),
             target_date=today + timedelta(days=365), notes="Sul conto deposito"),
        Goal(name="Viaggio in Giappone", target_amount=Decimal("5000"), saved_amount=Decimal("1800"),
             target_date=today + timedelta(days=240)),
        Budget(category="Alimentari", amount=Decimal("450")), Budget(category="Ristoranti", amount=Decimal("160")),
        Budget(category="Svago", amount=Decimal("100")), Budget(category="Shopping", amount=Decimal("150")),
        Budget(category="Streaming", amount=Decimal("35")),
        Budget(category="Viaggi", month=date(today.year, 8, 1), amount=Decimal("1500")),  # one month only
    ])
    db.session.add_all(ExchangeRate(currency="USD", on=start, rate=USD_RATE)
                       for start in months(date(today.year - YEARS, today.month, 1), today))
    db.session.flush()

    rows = []
    for mv in (mv for mv in moves if mv.date < cutoff):
        counterparty = mv.counterparty or mv.description
        tx = Transaction(date=mv.date, description=mv.description, amount=mv.amount, currency=mv.currency, type=mv.type,
                         category=mv.category, counterparty=counterparty, tags=[counterparty, *mv.tags],
                         is_recurring=mv.recurrence is not None, recurrence=mv.recurrence, recurrence_end=mv.recurrence_end,
                         account_id=accounts[mv.account].id,
                         counter_account_id=accounts[mv.to].id if mv.to else None,
                         holding_id=holdings[mv.holding].id if mv.holding else None,
                         debt_id=debts[mv.debt].id if mv.debt else None)
        tx.splits = [TransactionSplit(category=c, amount=a) for c, a in mv.splits]
        rows.append(tx)
    db.session.add_all(rows)
    settings_store.set(wealth.OPENING_CASH_SETTING, "0")
    db.session.commit()
    for back in (24, 18, 12, 6, 0):  # the balance sheet at the end of a month, every six months
        year, month = divmod(cutoff.year * 12 + cutoff.month - 1 - back, 12)
        on = date(year, month + 1, 1) - timedelta(days=1)
        wealth.take_snapshot(f"Fine {on:%m/%Y}", on)
    db.session.commit()
    return {"moves": moves, "saved": len(rows), "cutoff": cutoff}


# ── Last month and the current one, as each bank would export them ─────────────

def _it(amount: Decimal) -> str:
    return f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _of(moves: list[Move], account: str, since: date) -> list[tuple[Move, Decimal]]:
    """(movement, signed amount on `account`) from `since` on."""
    return [(mv, mv.effect(account)) for mv in moves if mv.date >= since and mv.effect(account)]


def write_statements(moves: list[Move], since: date, folder: Path) -> dict[str, int]:
    folder.mkdir(exist_ok=True)
    written = {}

    rows = _of(moves, "conto", since)
    lines = ["Data operazione;Descrizione;Importo"] + [f"{mv.date:%d/%m/%Y};{mv.description};{_it(a)}" for mv, a in rows]
    (folder / "conto_corrente_fineco.csv").write_text("﻿" + "\n".join(lines) + "\n", encoding="utf-8")
    written["conto_corrente_fineco.csv"] = len(rows)

    rows = _of(moves, "carta", since)
    body = "".join(f"<STMTTRN><TRNTYPE>{'CREDIT' if a > 0 else 'DEBIT'}</TRNTYPE><DTPOSTED>{mv.date:%Y%m%d}</DTPOSTED>"
                   f"<TRNAMT>{a:.2f}</TRNAMT><FITID>V{i:05d}</FITID><NAME>{_xml(mv.description)}</NAME></STMTTRN>\n"
                   for i, (mv, a) in enumerate(rows, 1))
    (folder / "carta_visa.ofx").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<?OFX OFXHEADER="200" VERSION="220"?>\n'
        "<OFX><CREDITCARDMSGSRSV1><CCSTMTTRNRS><CCSTMTRS><CURDEF>EUR</CURDEF><BANKTRANLIST>\n"
        f"{body}</BANKTRANLIST></CCSTMTRS></CCSTMTTRNRS></CREDITCARDMSGSRSV1></OFX>\n", encoding="utf-8")
    written["carta_visa.ofx"] = len(rows)

    rows = _of(moves, "deposito", since)
    opening = balance(moves, "deposito", since)
    closing = opening + sum((a for _, a in rows), Decimal(0))

    def bal(code, amount):
        return (f"<Bal><Tp><CdOrPrtry><Cd>{code}</Cd></CdOrPrtry></Tp><Amt Ccy=\"EUR\">{abs(amount):.2f}</Amt>"
                f"<CdtDbtInd>{'CRDT' if amount >= 0 else 'DBIT'}</CdtDbtInd></Bal>\n")
    entries = "".join(
        f"<Ntry><Amt Ccy=\"EUR\">{abs(a):.2f}</Amt><CdtDbtInd>{'CRDT' if a > 0 else 'DBIT'}</CdtDbtInd><Sts>BOOK</Sts>"
        f"<BookgDt><Dt>{mv.date:%Y-%m-%d}</Dt></BookgDt><NtryDtls><TxDtls><RmtInf><Ustrd>{_xml(mv.description)}</Ustrd>"
        f"</RmtInf></TxDtls></NtryDtls></Ntry>\n" for mv, a in rows)
    (folder / "conto_deposito_illimity_camt053.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">'
        "<BkToCstmrStmt><Stmt><Id>ILLIMITY</Id>\n" + bal("OPBD", opening) + bal("CLBD", closing) + entries
        + "</Stmt></BkToCstmrStmt></Document>\n", encoding="utf-8")
    written["conto_deposito_illimity_camt053.xml"] = len(rows)

    rows = _of(moves, "titoli", since)
    out = ["!Type:Bank"]
    for mv, a in rows:
        category = "[Conto corrente Fineco]" if mv.type == "transfer" and mv.to == "titoli" else mv.category
        out += [f"D{mv.date:%d/%m/%Y}", f"T{a:.2f}", f"P{mv.description}", f"L{category}", "^"]
    (folder / "conto_titoli_directa.qif").write_text("\n".join(out) + "\n", encoding="utf-8")
    written["conto_titoli_directa.qif"] = len(rows)
    return written


def main() -> None:
    app = create_app()
    today = date.today()
    with app.app_context():
        if db.inspect(db.engine).get_table_names():
            sys.exit("The database is not empty: use an empty scratch database (see the top of this file).")
        db.create_all()
        result = fill(today)
        (HERE / "backup_completo_3anni.zip").write_bytes(backup.create_archive())
        (HERE / "transazioni_3anni.csv").write_text("﻿" + transfer.to_csv(transfer.query_transactions()), encoding="utf-8")
        written = write_statements(result["moves"], result["cutoff"], STATEMENTS)
    print(f"{result['saved']} transactions up to {result['cutoff'] - timedelta(days=1)}; statements from {result['cutoff']}:",
          ", ".join(f"{name} ({count})" for name, count in written.items()))


if __name__ == "__main__":
    main()
