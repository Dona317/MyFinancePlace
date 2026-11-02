"""F22: odd jobs and occasional work — withholding, INPS threshold, collecting, the tax return."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.gig import Gig
from app.models.transaction import Transaction
from app.services import cash, gigs, notifications
from tests.conftest import make_tx


def _gig(db, **values):
    base = dict(client="Studio Bianchi", description="Sito web", owner=None, on=date(2026, 3, 10), hours=Decimal(10),
                gross=Decimal(1000), withholding_agent=True, expenses=None, method="transfer", notes=None)
    gig = gigs.save(Gig(), **(base | values))
    db.session.commit()
    return gig


def test_withholding_threshold_and_year(db):
    a = _gig(db)
    b = _gig(db, client="Sig.ra Rossi", description="Ripetizioni", gross=Decimal(3200), withholding_agent=False,
             method="cash", expenses=Decimal(150))
    _gig(db, on=date(2025, 5, 1), gross=Decimal(50))
    assert gigs.withholding(a) == 200 and gigs.net(a) == 800 and gigs.net(b) == 3200
    year = gigs.year(2026)
    assert year.gross == 4200 and year.withheld == 200 and year.net == 4000 and year.to_collect == 4000
    assert year.expenses == 150 and year.taxable == 4050
    assert year.near_threshold and year.over_threshold == 0 and year.threshold_pct == 84.0
    assert year.by_client == [("Sig.ra Rossi", 3200, 1), ("Studio Bianchi", 1000, 1)]
    _gig(db, gross=Decimal(2000))
    year = gigs.year(2026)
    assert year.over_threshold == 1200 and year.threshold_pct == 100.0
    assert 2025 in gigs.years() and date.today().year in gigs.years()
    assert gigs.clients() == ["Sig.ra Rossi", "Studio Bianchi"]


def test_validation(db):
    for bad, message in ((dict(client=" "), "per chi"), (dict(on=None), "data"), (dict(gross=Decimal(0)), "positivo"),
                         (dict(hours=Decimal(-1)), "negative")):
        with pytest.raises(ValueError, match=message):
            _gig(db, **bad)
    assert _gig(db, method="strano").method == "other"


def test_collect_link_unpay_and_late(app, db):
    gig = _gig(db, method="cash", withholding_agent=False, on=date.today() - timedelta(days=40))
    assert gigs.late() == [gig]
    with app.test_request_context():
        assert f"gig-{gig.id}" in [n.key for n in notifications.collect()]
    wallet = cash.wallet(create=True)
    tx = gigs.collect(gig, wallet, date.today())
    db.session.commit()
    assert tx.amount == 1000 and tx.account_id == wallet.id and tx.category == gigs.CATEGORY and gigs.paid(gig)
    assert gigs.late() == []
    with pytest.raises(ValueError, match="già incassato"):
        gigs.collect(gig, wallet)
    gigs.unpay(gig)
    db.session.commit()
    assert Transaction.query.count() == 0 and not gigs.paid(gig)
    bank_income = make_tx(date=gig.date + timedelta(days=3), description="Bonifico Bianchi", amount=1000, type="income",
                          import_ref="abc")
    db.session.add(bank_income)
    db.session.commit()
    assert gigs.candidates(gig) == [bank_income]
    gigs.link(gig, bank_income)
    gigs.unpay(gig)  # a movement from the bank stays
    db.session.commit()
    assert Transaction.query.count() == 1
    with pytest.raises(ValueError, match="entrata"):
        gigs.link(gig, make_tx(type="expense"))


def test_pages(client, db):
    page = client.get("/gigs/").get_data(as_text=True)
    assert "Nessun lavoro" in page and "Soglia INPS" in page
    client.post("/gigs/new", data={"client": "Studio Bianchi", "description": "Sito web", "date": "2026-03-10",
                                   "gross": "1000", "hours": "10", "withholding": "on", "method": "transfer"})
    gig = Gig.query.one()
    assert gig.withholding_rate == 20 and gig.hours == 10
    page = client.get("/gigs/?year=2026").get_data(as_text=True)
    assert "Sito web" in page and "da incassare" in page and "Per committente" in page
    assert "per chi" in client.post("/gigs/new", data={"client": "", "description": "x", "date": "2026-01-01",
                                                       "gross": "1"}, follow_redirects=True).get_data(as_text=True)
    client.post(f"/gigs/{gig.id}/edit", data={"client": "Studio Bianchi", "description": "Sito web e logo",
                                              "date": "2026-03-10", "gross": "1200", "method": "cash", "expenses": "50"})
    db.session.refresh(gig)
    assert gig.gross == 1200 and gig.withholding_rate == 0 and gig.expenses == 50 and gig.method == "cash"
    client.post(f"/gigs/{gig.id}/collect", data={"on": "2026-03-20"})  # cash: to the wallet, made on the spot
    db.session.refresh(gig)
    assert gig.paid_on == date(2026, 3, 20) and gig.transaction.account.kind == "cash"
    client.post(f"/gigs/{gig.id}/unpay")
    bank = Account(name="Banca")
    db.session.add(bank)
    db.session.commit()
    client.post(f"/gigs/{gig.id}/collect", data={"account_id": bank.id})
    db.session.refresh(gig)
    assert gig.transaction.account_id == bank.id
    other = make_tx(date=date(2026, 3, 12), description="Bonifico", amount=1200, type="income")
    db.session.add(other)
    db.session.commit()
    client.post(f"/gigs/{gig.id}/unpay")
    client.post(f"/gigs/{gig.id}/collect", data={"transaction_id": other.id})
    db.session.refresh(gig)
    assert gig.transaction_id == other.id
    tax = client.get("/tax/gigs?year=2026").get_data(as_text=True)
    assert "redditi diversi" in tax and "Studio Bianchi" in tax
    client.post(f"/gigs/{gig.id}/delete")
    assert Gig.query.count() == 0
