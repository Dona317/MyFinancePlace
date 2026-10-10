"""
The two-bank fictitious statements (samples/dati_fittizi/genera_due_banche.py): January 2022 – September 2026, and
every giroconto in both files on the same day for the same amount. The committed files must be the generator's output
and must be read by the bank import as UniCredit and Fineco.
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


def test_every_transfer_is_in_both_files_on_the_same_day():
    out = Counter((m.day, -m.amount) for m in MOVES if m.transfer and m.amount < 0)
    arriving = Counter((m.day, m.amount) for m in MOVES if m.transfer and m.amount > 0)
    assert out == arriving and sum(out.values()) > 50
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
            assert sum(r.type == "transfer" for r in preview.rows) == sum(m.transfer for m in mine)
