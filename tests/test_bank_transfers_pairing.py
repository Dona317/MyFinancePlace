"""
Money moved between two of the user's accounts is in both banks' statements, maybe a few days apart and maybe called
just "bonifico". Importing the second statement must join it to the side saved from the first one (one transfer with
both accounts), never skip it or count it twice.
"""
import io
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.account import Account
from app.models.transaction import Transaction
from app.services import accounts
from tests.form_helper import form_data

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "samples" / "dati_fittizi"))
import genera_due_banche as two  # noqa: E402

HEADER = "Data Registrazione;Data valuta;Descrizione;Causale;Importo (EUR)\n"


def _csv(*lines: str) -> bytes:
    return ("﻿" + HEADER + "\n".join(lines) + "\n").encode()


@pytest.fixture()
def pair(db):
    unicredit = Account(name="UniCredit conto corrente", kind="current", opening_balance=Decimal("1000"))
    fineco = Account(name="Fineco conto risparmio", kind="savings", opening_balance=Decimal("0"))
    db.session.add_all([unicredit, fineco])
    db.session.commit()
    return unicredit, fineco


def _preview(client, name: str, raw: bytes) -> str:
    return client.post("/export/bank", data={"file": (io.BytesIO(raw), name), "bank": "auto"},
                       content_type="multipart/form-data").get_data(as_text=True)


def _import(client, name: str, raw: bytes, account: Account) -> str:
    html = _preview(client, name, raw)
    rows = sorted(set(re.findall(r'name="include" value="(\d+)"', html)), key=int)
    response = client.post("/export/bank/confirm", data=form_data(html, "preview-form", include=rows,
                                                                  account_id=str(account.id)), follow_redirects=True)
    return response.get_data(as_text=True)


UNICREDIT = _csv("28.01.2026;28.01.2026;Giroconto verso Fineco - risparmio;Giroconto;-500,00",
                 "29.01.2026;29.01.2026;PAGAMENTO POS LIDL;Pagamento POS;-40,00")
FINECO = _csv("28.01.2026;28.01.2026;Giroconto da UniCredit - risparmio;Giroconto;500,00",
              "30.01.2026;30.01.2026;Giroconto verso UniCredit - dentista;Giroconto;-200,00")


def test_the_second_statement_joins_the_transfer(client, pair, app):
    unicredit, fineco = pair
    _import(client, "unicredit_gennaio.csv", UNICREDIT, unicredit)
    html = _preview(client, "unicredit_fineco.csv", FINECO)
    assert "Collega al giroconto: 28/01/2026" in html and "Possibile duplicato" not in html
    page = _import(client, "unicredit_fineco.csv", FINECO, fineco)
    assert "1 giroconto collegato al movimento già importato dall&#39;altro conto." in page

    transfers = Transaction.query.filter_by(type="transfer").order_by(Transaction.date).all()
    assert [(t.account_id, t.counter_account_id, t.amount) for t in transfers] == [
        (unicredit.id, fineco.id, Decimal("500.00")),  # joined: one movement with both accounts
        (fineco.id, None, Decimal("200.00")),          # its other half is not imported yet
    ]
    with app.test_request_context():
        assert accounts.balance(unicredit) == 460.0 and accounts.balance(fineco) == 300.0


def test_importing_a_statement_again_adds_nothing(client, pair):
    unicredit, fineco = pair
    _import(client, "unicredit_gennaio.csv", UNICREDIT, unicredit)
    _import(client, "unicredit_fineco.csv", FINECO, fineco)
    before = Transaction.query.count()
    _import(client, "unicredit_fineco.csv", FINECO, fineco)
    _import(client, "unicredit_gennaio.csv", UNICREDIT, unicredit)
    assert Transaction.query.count() == before


def test_a_transfer_is_not_joined_to_its_own_account(client, pair):
    """The same giroconto row imported on the same account is not the other half: it stays as it is."""
    unicredit, _ = pair
    _import(client, "unicredit_gennaio.csv", UNICREDIT, unicredit)
    incoming = _csv("28.01.2026;28.01.2026;Giroconto da Fineco - rimborso;Giroconto;500,00")
    _import(client, "unicredit_rimborso.csv", incoming, unicredit)
    halves = Transaction.query.filter_by(type="transfer").all()
    assert len(halves) == 2 and not any(t.account_id and t.counter_account_id for t in halves)


def test_a_plain_bonifico_arriving_days_later_becomes_a_giroconto(client, pair, app):
    """A bonifico to oneself, not called «giroconto», sent on Friday and booked by the other bank on Tuesday."""
    unicredit, fineco = pair
    _import(client, "unicredit_marzo.csv", _csv(
        "06.03.2026;06.03.2026;Bonifico SEPA a MARIO ROSSI IBAN IT40S0301503200000012345678;Bonifico SEPA;-300,00",
        "06.03.2026;06.03.2026;Bonifico SEPA a IDRAULICO BIANCHI fattura 12;Bonifico SEPA;-150,00"), unicredit)
    sent = Transaction.query.filter(Transaction.description.like("%MARIO ROSSI%")).one()
    assert sent.type == "expense"  # alone, a bonifico to oneself looks like any payment

    arriving = _csv("10.03.2026;10.03.2026;Bonifico da MARIO ROSSI IBAN IT60X0200801600000102345678;Bonifico;300,00",
                    "10.03.2026;10.03.2026;Bonifico da IDRAULICO BIANCHI rimborso;Bonifico;150,00")
    html = _preview(client, "unicredit_fineco_marzo.csv", arriving)
    assert html.count('name="pair-') == 2  # both look like the other side: the user decides
    rows = sorted(set(re.findall(r'name="include" value="(\d+)"', html)), key=int)
    # the plumber's refund is a different movement: «collega» unticked for it
    data = form_data(html, "preview-form", include=rows, account_id=str(fineco.id))
    plumber = re.search(r'name="pair-(\d+)"[^>]*>\s*<i[^>]*></i> Collega al giroconto: 06/03/2026 · Bonifico SEPA a IDRAULICO', html)
    data.pop(f"pair-{plumber.group(1)}")
    client.post("/export/bank/confirm", data=data)

    joined = db_refresh(sent)
    assert (joined.type, joined.category, joined.account_id, joined.counter_account_id) == (
        "transfer", "Giroconto", unicredit.id, fineco.id)
    assert Transaction.query.filter_by(type="income", account_id=fineco.id).count() == 1  # the refund, kept apart
    with app.test_request_context():
        assert accounts.balance(unicredit) == 550.0 and accounts.balance(fineco) == 450.0
    before = Transaction.query.count()
    _import(client, "unicredit_fineco_marzo.csv", arriving, fineco)  # again: both rows already there
    assert Transaction.query.count() == before


def test_up_to_fifteen_days_apart_never_before_it_left(client, pair):
    unicredit, fineco = pair
    _import(client, "unicredit_aprile.csv", _csv("10.04.2026;10.04.2026;Giroconto verso Fineco;Giroconto;-250,00"),
            unicredit)
    too_far = _csv("26.04.2026;26.04.2026;Giroconto da UniCredit;Giroconto;250,00",  # sixteen days later
                   "08.04.2026;08.04.2026;Giroconto da UniCredit;Giroconto;250,00")  # before it left
    assert 'name="pair-' not in _preview(client, "unicredit_fineco_aprile.csv", too_far)
    slow = _csv("25.04.2026;25.04.2026;Bonifico da MARIO ROSSI;Bonifico;250,00")  # fifteen days: still the same
    assert "Collega al giroconto: 10/04/2026" in _preview(client, "unicredit_fineco_aprile.csv", slow)
    _import(client, "unicredit_fineco_aprile.csv", slow, fineco)
    joined = Transaction.query.one()
    assert (joined.account_id, joined.counter_account_id) == (unicredit.id, fineco.id)


def db_refresh(tx):
    from app.extensions import db
    db.session.expire_all()
    return db.session.get(Transaction, tx.id)


@pytest.mark.parametrize("first", ["unicredit", "fineco"])
def test_the_two_bank_sample_files_in_either_order(client, pair, app, first):
    unicredit, fineco = pair
    for account in (unicredit, fineco):
        account.opening_balance = two.OPENING["unicredit" if account is unicredit else "fineco"]
    files = {"unicredit": (two.UNICREDIT_FILE, unicredit), "fineco": (two.FINECO_FILE, fineco)}
    order = [first, "fineco" if first == "unicredit" else "unicredit"]
    for key in order:
        name, account = files[key]
        _import(client, name, (two.OUT / name).read_bytes(), account)

    moves = two.build()
    transfers = Transaction.query.filter_by(type="transfer")
    assert transfers.count() == sum(m.transfer for m in moves) // 2  # giroconti and bonifici to oneself, once each
    assert transfers.filter((Transaction.account_id.is_(None)) | (Transaction.counter_account_id.is_(None))).count() == 0
    with app.test_request_context():
        summary = two.summary(moves)
        assert accounts.balance(unicredit) == float(summary["unicredit"]["closing"])
        assert accounts.balance(fineco) == float(summary["fineco"]["closing"])
