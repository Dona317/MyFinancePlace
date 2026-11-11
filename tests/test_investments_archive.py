"""
The investments on their own (services.investments_archive): exported from the fictitious set, restored over
changed investments or into an archive without them, they come back the same — positions, liquidity, models, PACs —
and the rest of the archive is not touched.
"""
import io
import json
import sys
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.models import (
    Account,
    Goal,
    Holding,
    InvestmentPlan,
    PlannedOrder,
    Portfolio,
    PortfolioTemplate,
    SecuritiesAccount,
    Transaction,
)
from app.services import accounts, investments_archive, securities
from app.services.investments_archive import ArchiveError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "samples" / "dati_fittizi"))
import genera_investimenti as demo  # noqa: E402

TODAY = date(2026, 11, 11)


def _picture() -> dict:
    """What must survive a round trip, by names (ids change)."""
    return {
        "balances": {a.name: round(accounts.balance(a), 2) for a in Account.query},
        "holdings": sorted((h.name, str(h.quantity), str(h.avg_price), str(h.current_price)) for h in Holding.query),
        "positions": sorted((p.name, str(p.quantity), p.securities_account_id is not None) for p in securities.positions()),
        "transactions": Transaction.query.count(),
        "dossiers": sorted(d.name for d in SecuritiesAccount.query),
        "folios": sorted((p.name, p.is_default) for p in Portfolio.query),
        "models": sorted((t.name, t.active, len(t.slots), sum(len(s.links) for s in t.slots)) for t in PortfolioTemplate.query),
        "plans": sorted((p.name, p.portfolio.name if p.portfolio else None,
                         p.securities_account.name if p.securities_account else None) for p in InvestmentPlan.query),
    }


@pytest.fixture()
def data(app, db, tmp_path):
    app.instance_path = str(tmp_path)
    with app.test_request_context():
        demo.fill(TODAY)
        db.session.add(Goal(name="Vacanza", target_amount=Decimal(2000), saved_amount=Decimal(100)))
        db.session.add(Holding(name="Casa", asset_class="Immobile", quantity=1, avg_price=200000))
        db.session.commit()


def test_round_trip_over_changed_investments(app, db, data):
    with app.test_request_context():
        before = _picture()
        raw = investments_archive.create_archive()
        exported = investments_archive.read_upload(raw)
        assert exported["tables"]["accounts"] and {"Casa"}.isdisjoint(h["name"] for h in exported["tables"]["holdings"])
        assert investments_archive.counts(exported)["holdings"] == 25
        # the investments change: a holding deleted, a portfolio renamed, a theoretical order added
        Holding.query.filter_by(isin="IE00BK5BQT80").one().name = "cambiato"
        Portfolio.query.filter_by(name="Reddito").one().name = "Altro"
        db.session.add(PlannedOrder(batch="x", holding_id=Holding.query.first().id, side="buy", units=1, price=1))
        db.session.delete(Holding.query.filter_by(isin="IT0003128367").one())
        db.session.commit()
        added = investments_archive.restore(investments_archive.read_upload(raw))
        assert added["holdings"] == 25 and added["planned_orders"] == 0
        assert _picture() == before
        assert Goal.query.count() == 1 and Holding.query.filter_by(name="Casa").count() == 1  # not the section's


def test_into_an_archive_without_the_investments(app, db, data):
    """Restored where the investments and their accounts are gone: the accounts come back by name, with the same
    liquidity, and the commissions stay tied to their trades."""
    with app.test_request_context():
        before = _picture()
        raw = investments_archive.create_archive()
        investments_archive._clear()
        for name in ("Liquidità Fineco", "Liquidità Directa"):
            db.session.delete(Account.query.filter_by(name=name).one())
        db.session.commit()
        assert Holding.query.count() == 1 and Transaction.query.filter(Transaction.units.isnot(None)).count() == 0
        investments_archive.restore(investments_archive.read_upload(raw))
        after = _picture()
    assert after == before
    fees = Transaction.query.filter(Transaction.fee_for_id.isnot(None)).all()
    assert fees and all(f.fee_for is not None and f.fee_for.holding_id for f in fees)


def test_bad_files(app, db, data):
    with app.test_request_context():
        for raw in (b"nonsense", b"PK\x03\x04broken", json.dumps({"format": "other"}).encode()):
            with pytest.raises(ArchiveError, match="non è un export"):
                investments_archive.read_upload(raw)
        good = investments_archive.export_data()
        assert investments_archive.read_upload(json.dumps(good).encode())["format"] == investments_archive.FORMAT
        broken = json.loads(json.dumps(good))
        broken["tables"]["template_slots"][0]["template_id"] = 999999
        count = Transaction.query.count()
        with pytest.raises(ArchiveError, match="collegamento rotto"):
            investments_archive.restore(broken)
        assert Transaction.query.count() == count  # all or nothing
        bad = json.loads(json.dumps(good))
        bad["tables"]["holdings"][0]["quantity"] = "molte"
        with pytest.raises(ArchiveError, match="valore non valido"):
            investments_archive.restore(bad)


def test_pages(client, app, db, data):
    response = client.get("/portfolio/archive")
    assert response.mimetype == "application/zip" and "investimenti_" in response.headers["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert investments_archive.DATA_FILE in archive.namelist()
    assert "Esporta gli investimenti" in client.get("/portfolio/import").get_data(as_text=True)
    page = client.post("/portfolio/archive/restore", data={"file": (io.BytesIO(response.data), "inv.zip")},
                       content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "conferma che gli investimenti attuali" in page
    page = client.post("/portfolio/archive/restore", data={}, follow_redirects=True).get_data(as_text=True)
    assert "Scegli il file degli investimenti" in page
    page = client.post("/portfolio/archive/restore", data={"file": (io.BytesIO(b"x"), "x.zip"), "confirm": "1"},
                       content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "non è un export" in page
    page = client.post("/portfolio/archive/restore", data={"file": (io.BytesIO(response.data), "inv.zip"), "confirm": "1"},
                       content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "Investimenti ripristinati: 25 titoli" in page
