"""
Phase 1 (14 Nov): the export of the transactions with or without the investments, the template to fill in for the
broker import, a new instrument from an import placed in the model's part of its asset class.
"""
import csv
import io
import sys
from datetime import date
from pathlib import Path

import openpyxl

from app.models.portfolio_model import SlotHolding
from app.models.transaction import Transaction
from app.models.wealth import Holding
from app.services import broker_import, investments_archive, portfolio_models, transfer
from tests.conftest import make_tx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "samples" / "dati_fittizi"))
import genera_investimenti as demo  # noqa: E402

TODAY = date(2026, 11, 11)


def test_the_export_with_or_without_the_investments(app, client, db, tmp_path):
    app.instance_path = str(tmp_path)
    with app.test_request_context():
        demo.fill(TODAY)
        db.session.add(make_tx(date=date(2026, 10, 3), description="Pizzeria", amount=30, category="Ristoranti"))
        db.session.commit()
        every = transfer.query_transactions()
        theirs = transfer.query_transactions(scope="investments")
        ours = transfer.query_transactions(scope="no_investments")
        assert len(theirs) + len(ours) == len(every) and theirs and ours
        assert {t.id for t in theirs} == investments_archive.transaction_ids()
        assert all(t.holding_id is None and t.securities_account_id is None for t in ours)
        assert any(t.description == "Pizzeria" for t in ours) and not any(t.description == "Pizzeria" for t in theirs)
    rows = list(csv.reader(io.StringIO(client.get("/export/csv?scope=no_investments").get_data(as_text=True).lstrip("﻿")),
                           delimiter=";"))
    assert len(rows) - 1 == len(ours)
    response = client.get("/export/csv?scope=investments&period=all")
    assert "_investimenti_" in response.headers["Content-Disposition"]
    data = client.get("/export/json?scope=investments").get_json()
    assert len(data["transactions"]) == len(theirs)
    assert len(client.get("/export/json?scope=nonsense").get_json()["transactions"]) == len(every)
    page = client.get("/export/").get_data(as_text=True)
    assert 'name="scope"' in page and "Transazioni conti e contante" in page and "Transazioni investimenti" in page


def test_the_template_is_read_by_the_import(app, client, db):
    with app.test_request_context():
        for kind, name in (("csv", "modello.csv"), ("xlsx", "modello.xlsx")):
            preview = broker_import.read(name, broker_import.template(kind))
            rows = {r.name: r for r in preview.rows}
            assert len(rows) == 3 and not preview.unread, kind
            assert rows["Enel S.p.A."].units < 0 and rows["Vanguard FTSE All-World UCITS ETF Acc"].units == 10
            bond = rows["BTP 4,40% Mg33"]
            assert bond.units == 5000 and str(bond.price) == "1.012"  # % of the nominal → euro per euro
    response = client.get("/portfolio/import/template.xlsx")
    sheet = openpyxl.load_workbook(io.BytesIO(response.data)).active
    assert sheet["A1"].value == "Data operazione" and sheet.max_row == 4
    assert client.get("/portfolio/import/template.csv").mimetype == "text/csv"
    assert client.get("/portfolio/import/template.pdf").status_code == 404
    assert "Modello da compilare" in client.get("/portfolio/import").get_data(as_text=True)


def test_a_new_instrument_joins_the_part_of_its_class(app, client, db, tmp_path):
    app.instance_path = str(tmp_path)
    with app.test_request_context():
        demo.fill(TODAY)
        small = Holding(name="iShares MSCI World Small Cap UCITS ETF", isin="IE00BF4RFH31", asset_class="ETF",
                        allocation_class="Azionario", quantity=0, avg_price=0, opening_quantity=0, opening_price=0)
        art = Holding(name="Quadro d'autore", asset_class="ETF", allocation_class="Altro", quantity=0, avg_price=0,
                      opening_quantity=0, opening_price=0)
        db.session.add_all([small, art])
        db.session.flush()
        joined = portfolio_models.place_new(small)
        assert joined == ["Allocazione per classi: Azioni"]
        assert portfolio_models.place_new(art) == []  # no part holds anything of its class: placed by hand
        assert portfolio_models.place_new(small) == []  # already in: nothing more
        db.session.commit()
    assert SlotHolding.query.filter_by(holding_id=small.id).count() == 1
    # through the import: the file's new instrument is placed, and the page says where
    raw = ("Data operazione;Segno;Titolo;ISIN;Quantità;Prezzo;Commissioni\n"
           "05/11/2026;A;iShares Core MSCI Europe UCITS ETF;IE00B4K48X80;10;80,00;2,95\n").encode()
    page = client.post("/portfolio/import", data={"file": (io.BytesIO(raw), "ops.csv")},
                       content_type="multipart/form-data").get_data(as_text=True)
    payload = page.split('name="payload" value="')[1].split('"')[0]
    page = client.post("/portfolio/import/confirm", data={"payload": payload, "include": "0", "holding-0": ""},
                       follow_redirects=True).get_data(as_text=True)
    assert "messo nel portafoglio modello: Allocazione per classi: Azioni" in page
    europe = Holding.query.filter_by(isin="IE00B4K48X80").one()
    assert Transaction.query.filter_by(holding_id=europe.id).count() == 1
