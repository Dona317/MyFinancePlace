"""The merchant read from the bank causale (MVP point 4), checked on every sample statement."""
from pathlib import Path

import pytest

from app.models.transaction import Transaction
from app.services import bank_import, merchant
from tests.conftest import make_tx

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "bank_statements"
SKIP = ("SCANSIONE", "FOTO")  # read by OCR/AI, tested elsewhere


@pytest.mark.parametrize("causale, expected", [
    ("Pagamento carta - PAGAMENTO POS ESSELUNGA MILANO", "Esselunga"),
    ("PAGAMENTO CARTA PAGAMENTO POS FARMACIA COMUNALE 3", "Farmacia Comunale"),
    ("Pagamento Visa Debit presso ESSELUNGA MILANO", "Esselunga"),
    ("Pagamento tramite POS TRENITALIAWEB", "Trenitaliaweb"),
    ("PAGAMENTO POS ENI STATION 1043", "Eni Station"),
    ("PAGAMENTO POS Q8 VIA EMILIA", "Q8"),
    ("PAGAMENTO POS AMAZON EU SARL", "Amazon"),
    ("PAGAMENTO POS LIDL ITALIA", "Lidl"),
    ("PAGAMENTO POS RISTORANTE DA LUIGI", "Ristorante da Luigi"),
    ("PAGAMENTO POS PIZZERIA NAPOLI", "Pizzeria Napoli"),
    ("PAGAMENTO POS ATM MILANO", "ATM"),
    ("NETFLIX.COM AMSTERDAM", "Netflix"),
    ("SPOTIFY AB STOCKHOLM", "Spotify"),
    ("Addebito SDD - ENEL ENERGIA SPA bolletta luce 07/2026", "Enel Energia"),
    ("A2A ENERGIA gas", "A2A Energia"),
    ("ILIAD ITALIA SPA ricarica", "Iliad"),
    ("Bonifico a IMMOBILIARE CASA BELLA SRL per AFFITTO 07/2026", "Immobiliare Casa Bella"),
    ("BONIFICO SEPA Bonifico a IMMOBILIARE CASA BELLA SRL per AFFITTO 06/2026", "Immobiliare Casa Bella"),
    ("Bonifico SEPA - Bonifico da STUDIO BIANCHI per FATTURA consulenza", "Studio Bianchi"),
    ("Bonifico da ACME SPA per STIPENDIO 07/2026", "Acme"),
    ("Payment from Mario Rossi", "Mario Rossi"),
    ("Starbucks", "Starbucks"),
    ("H&M MILANO", "H&M"),
    # nobody to name
    ("COMMISSIONI BONIFICO", None),
    ("Commissione Revolut: Cash withdrawal at BANCOMAT ROMA", None),
    ("Giroconto verso conto deposito", None),
    ("Prelievo bancomat", None),
    ("Imposta di bollo", None),
    ("", None),
    ("12/07/2026 1043", None),
])
def test_merchant_from_the_causale(causale, expected):
    assert merchant.extract(causale) == expected


def test_details_are_used_when_the_description_names_nobody():
    assert merchant.extract("Pagamento carta", "PAGAMENTO POS DECATHLON") == "Decathlon"


@pytest.mark.parametrize("path", sorted(p for p in SAMPLES.iterdir()
                                        if p.suffix not in (".py", ".md") and p.is_file() and not p.name.startswith(SKIP)),
                         ids=lambda p: p.name)
def test_every_sample_statement_gets_its_merchants(app, db, path):
    with app.test_request_context():
        preview = bank_import.analyze_statement(path.name, path.read_bytes())
    spending = [r for r in preview.rows if r.type != "transfer"]
    named = [r for r in spending if r.counterparty]
    assert spending and len(named) >= 0.85 * len(spending)
    for row in spending:
        if not row.counterparty:  # only rows that name nobody may stay without one
            assert merchant.NOBODY.search(f"{row.description} {row.details or ''}"), row.description
    bank_words = {"Pagamento", "Pos", "Carta", "Bonifico", "Sepa", "Addebito", "Sdd", "Milano", "Italia"}
    assert not {r.counterparty for r in named} & bank_words


def test_fill_counterparties_of_saved_transactions(client, db):
    old = make_tx(description="Spesa", bank_description="PAGAMENTO POS ESSELUNGA MILANO", tags=["casa"])
    plain = make_tx(description="Abbonamento NETFLIX.COM", tags=[])
    named = make_tx(description="PAGAMENTO POS LIDL", counterparty="Lidl Via Roma", tags=["Lidl Via Roma"])
    fee = make_tx(description="COMMISSIONI BONIFICO", tags=[])
    giro = make_tx(description="Giroconto", type="transfer", tags=[])
    db.session.add_all([old, plain, named, fee, giro])
    db.session.commit()
    assert "Compila controparti (3)" in client.get("/transactions/").get_data(as_text=True)
    page = client.post("/transactions/fill-counterparties", follow_redirects=True).get_data(as_text=True)
    assert "2 transazioni hanno ora la controparte" in page
    assert (db.session.get(Transaction, old.id).counterparty, db.session.get(Transaction, old.id).tags) == ("Esselunga", ["Esselunga", "casa"])
    assert db.session.get(Transaction, plain.id).counterparty == "Abbonamento Netflix"
    assert db.session.get(Transaction, named.id).counterparty == "Lidl Via Roma"  # kept as the user wrote it
    assert db.session.get(Transaction, fee.id).counterparty is None
    again = client.post("/transactions/fill-counterparties", follow_redirects=True).get_data(as_text=True)
    assert "Nessuna controparte da aggiungere" in again
