"""
The two-bank fictitious statements (samples/dati_fittizi/genera_due_banche.py): January 2022 – September 2026, and
every movement between the two accounts in both files for the same amount, up to 15 days apart. The committed files
must be the generator's output and must be read by the bank import as UniCredit and Fineco.
"""
import sys
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.services import bank_import

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "samples" / "dati_fittizi"))
import genera_due_banche as two  # noqa: E402

MOVES = two.build()


def test_four_years_and_nine_months_of_both_accounts():
    for account in ("unicredit", "fineco"):
        days = [m.day for m in MOVES if m.account == account]
        assert min(days) < date(2022, 1, 15) and max(days) > date(2026, 9, 20)
    assert two.build() == MOVES  # deterministic


def test_every_transfer_is_in_both_files():
    """Same amount, out of one account and into the other the same day or up to 15 days later; called
    «giroconto» or a plain bonifico to oneself."""
    out = sorted(((m.day, -m.amount) for m in MOVES if m.transfer and m.amount < 0), key=lambda x: (x[1], x[0]))
    arriving = sorted(((m.day, m.amount) for m in MOVES if m.transfer and m.amount > 0), key=lambda x: (x[1], x[0]))
    assert len(out) == len(arriving) > 50
    assert [amount for _, amount in out] == [amount for _, amount in arriving]
    assert all(0 <= (back - sent).days <= 15 for (sent, _), (back, _) in zip(out, arriving))
    assert any((back - sent).days > 7 for (sent, _), (back, _) in zip(out, arriving))  # some slow ones
    assert any(sent != back for (sent, _), (back, _) in zip(out, arriving))  # not always instant
    styles = {m.short for m in MOVES if m.transfer and m.amount < 0}
    assert styles == {"Giroconto", "Bonifico SEPA", "Bonifico istantaneo"}
    for account in ("unicredit", "fineco"):  # both ways: savings out of UniCredit, deposits back from Fineco
        assert any(m.transfer and m.amount < 0 and m.account == account for m in MOVES)


def test_the_kinds_of_spending_asked_for():
    kinds = Counter(m.kind for m in MOVES)
    for kind in ("rent", "mortgage", "utilities", "groceries", "travel", "wedding", "home", "shopping", "salary",
                 "other_income", "tax", "interest"):
        assert kinds[kind], kind
    texts = " ".join(m.full for m in MOVES)
    assert "lavatrice" in texts and "Skipass" in texts and "regalo di nozze" in texts


def test_balances_stay_positive():
    for account, data in two.summary(MOVES).items():
        assert data["lowest"] > 0 and data["closing"] > 0, account


def test_the_committed_files_are_read_by_the_import(app):
    with app.test_request_context():
        for name, bank, account in ((two.UNICREDIT_FILE, "unicredit", "unicredit"),
                                    (two.FINECO_FILE, "fineco", "fineco")):
            preview = bank_import.analyze_statement(name, (two.OUT / name).read_bytes())
            mine = [m for m in MOVES if m.account == account]
            assert preview.bank.key == bank and len(preview.rows) == len(mine), name
            assert sum((r.amount for r in preview.rows), Decimal(0)) == sum((m.amount for m in mine), Decimal(0))
            # «giroconto» is read as a transfer straight away; a plain bonifico only once joined to the other side
            assert sum(r.type == "transfer" for r in preview.rows) == sum(m.short == "Giroconto" for m in mine)
