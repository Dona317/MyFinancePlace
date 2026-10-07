"""
The complete fictitious dataset (samples/dati_fittizi/genera_completo.py): three years on four linked accounts.
Built into the test database, it must add up — balances, transfers, investments — and fill every page; its
statements of the last weeks must import through the usual preview.
"""
import io
import json
import sys
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.account import Account
from app.models.transaction import Transaction, TransactionSplit
from app.models.wealth import Holding
from app.services import accounts, analytics, backup, bank_import, categories, subscriptions, wealth
from tests.conftest import make_tx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "samples" / "dati_fittizi"))
import genera_completo as demo  # noqa: E402

TODAY = date(2026, 10, 7)


@pytest.fixture()
def demo_data(app, db):
    with app.test_request_context():
        categories.ensure_defaults()
        result = demo.fill(TODAY)
    return result


def _balances() -> dict:
    return {a.name: accounts.balance(a) for a in Account.query}


def test_three_years_on_four_linked_accounts(app, demo_data):
    first, last = (Transaction.query.order_by(Transaction.date.asc()).first().date,
                   Transaction.query.order_by(Transaction.date.desc()).first().date)
    assert first == date(2023, 10, 1) and last.month == 8 and demo_data["cutoff"] == date(2026, 9, 1)
    assert Account.query.count() == 4 and TransactionSplit.query.count() > 0
    transfers = Transaction.query.filter_by(type="transfer")
    assert transfers.filter(Transaction.counter_account_id.isnot(None)).count() > 100  # the links between accounts
    with app.test_request_context():
        balances = _balances()
        # the card owes exactly August's spending: July's was paid on 15 August
        august = sum(mv.euro() for mv in demo_data["moves"]
                     if mv.account == "carta" and mv.type == "expense" and mv.date.month == 8 and mv.date.year == 2026)
        assert balances["Carta di credito Visa"] == -float(august)
        expected = {name: float(demo.balance(demo_data["moves"], key, demo_data["cutoff"]))
                    for key, (name, *_) in demo.ACCOUNTS.items()}
        assert balances == pytest.approx(expected)
        # the cash in the balance sheet is the money on the accounts: ETF purchases left it for the portfolio
        assert wealth.cash_balance() == pytest.approx(sum(balances.values()))


def test_cash_leaves_for_an_investment_and_comes_back_from_a_sale(app, db):
    account = Account(name="Broker", kind="other", opening_balance=Decimal(1000))
    etf = Holding(name="ETF", asset_class="ETF", quantity=1, avg_price=Decimal(300))
    db.session.add_all([account, etf])
    db.session.flush()
    db.session.add_all([
        make_tx(type="transfer", amount=300, category="Investimenti", account_id=account.id, holding_id=etf.id),
        make_tx(type="transfer", amount=50, category="Investimenti", counter_account_id=account.id, holding_id=etf.id),
        make_tx(type="transfer", amount=999, category="Giroconto"),  # between accounts not recorded: no change
    ])
    db.session.commit()
    with app.test_request_context():
        assert wealth.cash_balance() == 750.0 == accounts.balance(account)


def test_every_page_has_data(client, demo_data):
    for url in ("/dashboard", "/reports/summary?year=2024", "/reports/", "/lifestyle/?year=2025", "/forecast/",
                "/subscriptions/", "/subscriptions/?kind=income", "/accounts/", "/accounting/balance-sheet",
                "/accounting/cash-flow?year=2025", "/accounting/income-statement?year=2025", "/lifestyle/budget",
                "/lifestyle/goals", "/snapshots/", "/portfolio/", "/debt/", "/transactions/?category=Casa"):
        response = client.get(url)
        assert response.status_code == 200, url
    with client.application.test_request_context():
        run = analytics.autonomy(TODAY)
        assert run["basis"] == 12 and run["months_all"] > 3 and run["months_essential"] > run["months_all"]
        rates = analytics.savings_rates_by_year(TODAY)
        assert [y["year"] for y in rates["years"]] == [2026, 2025, 2024, 2023]
        subs = subscriptions.overview("expense", TODAY)
        assert [s.template.description for s in subs["ended"]] == ["Disney Plus"]
        netflix = next(s for s in subs["series"] if s.template.description == "Netflix abbonamento")
        assert netflix.amount == 15.99 and netflix.confirmed
        assert analytics.nature_split(date(2025, 1, 1), date(2026, 1, 1))["amounts"]["fixed"] > 0


def test_the_statements_import_through_the_preview(app, demo_data, tmp_path):
    written = demo.write_statements(demo_data["moves"], demo_data["cutoff"], tmp_path)
    assert all(count > 0 for count in written.values())
    with app.test_request_context():
        for name, count in written.items():
            preview = bank_import.analyze_statement(name, (tmp_path / name).read_bytes())
            assert len(preview.rows) == count and not preview.unread, name
            assert not any(r.duplicate for r in preview.rows)  # all after the backup's last day
            if name.endswith(".xml"):
                assert preview.balance_check.ok
            if name.endswith(".qif"):
                assert any(r.type == "transfer" for r in preview.rows)


def test_the_backup_restores(app, demo_data):
    with app.test_request_context():
        raw = backup.create_archive()
        before = (Transaction.query.count(), _balances())
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            data = json.loads(archive.read("backup.json"))
        backup.restore(data, {})
        assert (Transaction.query.count(), _balances()) == before
