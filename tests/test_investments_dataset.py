"""
The fictitious investments (samples/dati_fittizi/genera_investimenti.py): ten ETFs of different asset classes,
shares, bonds and funds on two securities accounts, with a model portfolio out of balance and the statements of
both accounts. Built into the test database, it must add up — positions, liquidity never below zero, the model —
and its statements must import only this month's trades.
"""
import io
import json
import sys
import zipfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.account import Account
from app.models.securities import Portfolio, SecuritiesAccount
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import accounts, backup, broker_import, portfolio_models, securities

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "samples" / "dati_fittizi"))
import genera_investimenti as demo  # noqa: E402

TODAY = date(2026, 11, 11)


@pytest.fixture()
def data(app, db, tmp_path):
    app.instance_path = str(tmp_path)
    with app.test_request_context():
        result = demo.fill(TODAY)
    return result


def test_ten_etfs_of_different_classes_shares_bonds_and_funds(app, data):
    etfs = Holding.query.filter_by(asset_class="ETF").all()
    assert len(etfs) == 10 and len({h.index_name for h in etfs}) == 10
    assert {h.allocation_class for h in etfs} >= {"Azionario", "Obbligazionario", "Monetario e liquidità",
                                                   "Oro e metalli preziosi", "Commodities", "Immobiliare",
                                                   "Criptovalute", "Misto"}
    kinds = {h.asset_class for h in Holding.query}
    assert kinds == {"ETF", "Azione", "Obbligazione", "Fondo comune", "Fondo assicurativo", "Fondo Pensione"}
    assert all(h.maturity_date and h.bond_type for h in Holding.query.filter_by(asset_class="Obbligazione"))
    assert Holding.query.filter_by(isin="IT0005638820").one().quantity == 0  # the BOT, repaid at maturity


def test_two_securities_accounts_and_two_portfolios(app, data):
    with app.test_request_context():
        assert [d.name for d in securities.accounts()] == ["Conto titoli Directa", "Dossier Fineco",
                                                           "Polizza e previdenza (Intesa)"]
        assert securities.default_portfolio().name == "Crescita"
        assert Portfolio.query.count() == 2
        # every position adds up to its holding, and nothing is left without a dossier
        for holding in Holding.query:
            parts = securities.positions([holding])
            assert sum((p.quantity for p in parts), Decimal(0)) == holding.quantity, holding.name
        assert not securities.ensure_assigned()
    # the same share in both dossiers and both portfolios
    enel = Holding.query.filter_by(isin="IT0003128367").one()
    places = {(p.securities_account_id, p.portfolio_id) for p in securities.positions([enel])}
    assert len(places) == 2


def test_liquidity_never_below_zero(app, data):
    cutoff = data["cutoff"]
    for account in Account.query:
        day = date(2024, 1, 1)
        while day < cutoff:
            assert accounts.balance(account, day) >= 0, (account.name, day)
            day += timedelta(days=7)


def test_the_model_is_out_of_balance_and_the_pac_waits(app, data):
    with app.test_request_context():
        template = portfolio_models.active()
        plan = portfolio_models.rebalance(template, "full")
        assert [line.label for line in plan.out_of_band] == ["Azioni"]
        assert any(line.move > 0 for line in plan.lines) and any(line.move < 0 for line in plan.lines)
        assert portfolio_models.active(Portfolio.query.filter_by(name="Reddito").one().id).name == "Reddito 75/25"
    pac = data["holdings"]["vwce"]
    assert Transaction.query.filter(Transaction.holding_id == pac.id, Transaction.units > 0).count() > 30


def test_the_statements_import_only_this_month(app, data):
    """The history is recognized as already imported; this month's trades are new (two instruments not yet owned)."""
    with app.test_request_context():
        for dossier, new in (("fineco", 3), ("directa", 3)):
            for name in (f"storico_{dossier}.csv", f"mese_corrente_{dossier}.csv"):
                preview = broker_import.read(name, data["files"][name].encode("utf-8"))
                fresh = [r for r in preview.rows if not r.duplicate]
                assert len(fresh) == new and all(r.on >= data["cutoff"] for r in fresh), name
            assert any(r.holding_id is None for r in fresh)  # a new instrument, created by the import
        directa = broker_import.read("storico_directa.csv", data["files"]["storico_directa.csv"].encode("utf-8"))
        assert directa.unread  # dividends, coupons and taxes: not trades


def test_the_backup_restores(app, data):
    with app.test_request_context():
        raw = backup.create_archive()
        before = (Transaction.query.count(), SecuritiesAccount.query.count(),
                  {a.name: accounts.balance(a) for a in Account.query})
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            backup.restore(json.loads(archive.read("backup.json")), {})
        assert (Transaction.query.count(), SecuritiesAccount.query.count(),
                {a.name: accounts.balance(a) for a in Account.query}) == before
