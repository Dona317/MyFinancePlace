"""Editing and deleting transactions, bulk delete, and the duplicate finder."""
import re
from datetime import date

import pytest

from app.models.duplicate import DuplicateDismissal
from app.models.transaction import Transaction
from app.services import duplicates
from tests.conftest import make_tx
from tests.form_helper import form_data


def add(db, **values):
    tx = make_tx(**values)
    db.session.add(tx)
    db.session.commit()
    return tx


# ── Edit ───────────────────────────────────────────────────────────────────────

def test_editing_keeps_a_category_outside_the_default_list(client, db):
    """Regression: imported categories (e.g. "Commissioni", "Sport") were wiped when saving the edit form."""
    tx = add(db, description="Palestra", category="Sport", amount=40)
    page = client.get(f"/transactions/{tx.id}/edit").get_data(as_text=True)
    client.post(f"/transactions/{tx.id}/edit", data=form_data(page, "edit-form", description="Palestra FIT"))
    db.session.refresh(tx)
    assert (tx.description, tx.category) == ("Palestra FIT", "Sport")


def test_invalid_edit_shows_an_error_instead_of_crashing(client, db):
    tx = add(db, description="Cena", amount=30)
    page = client.get(f"/transactions/{tx.id}/edit").get_data(as_text=True)
    response = client.post(f"/transactions/{tx.id}/edit", data=form_data(page, "edit-form", amount="abc"))
    assert response.status_code == 302
    db.session.refresh(tx)
    assert float(tx.amount) == 30  # nothing half-saved


@pytest.mark.parametrize("amount", ["nan", "NaN", "sNaN", "inf", "-Infinity", "1e20", "0", "12345678901"])
def test_form_rejects_unusable_amounts(client, db, amount):
    page = client.get("/transactions/new").get_data(as_text=True)
    data = form_data(page, "edit-form", date="2026-06-01", description="Test", amount=amount, type="expense")
    response = client.post("/transactions/new", data=data)
    assert response.status_code == 200 and "Controlla i dati" in response.get_data(as_text=True)
    assert Transaction.query.count() == 0


def test_edit_page_can_delete_and_return_to_where_you_were(client, db):
    tx = add(db, description="Da eliminare")
    page = client.get(f"/transactions/{tx.id}/edit?next=/transactions/duplicates").get_data(as_text=True)
    assert "Elimina" in page
    response = client.post(f"/transactions/{tx.id}/delete", data=form_data(page, "delete-form"))
    assert response.location.endswith("/transactions/duplicates")
    assert Transaction.query.count() == 0


def test_redirects_never_leave_the_site(client, db):
    tx = add(db)
    for target in ("https://evil.example", "//evil.example", "/\\\\evil.example"):
        response = client.post(f"/transactions/{tx.id}/delete", data={"next": target})
        assert response.location.endswith("/transactions/")
        tx = add(db)


def test_bulk_delete(client, db):
    ids = [add(db, description=f"T{i}").id for i in range(4)]
    page = client.get("/transactions/").get_data(as_text=True)
    assert "Elimina selezionate" in page
    client.post("/transactions/delete-selected", data=form_data(page, "bulk-form", ids=[str(ids[0]), str(ids[2])]))
    assert sorted(t.description for t in Transaction.query.all()) == ["T1", "T3"]


def test_every_listed_transaction_has_edit_and_delete(client, db):
    for i in range(3):
        add(db, description=f"T{i}")
    page = client.get("/transactions/").get_data(as_text=True)
    assert len(re.findall(r'title="Modifica"', page)) == 3 and len(re.findall(r'title="Elimina"', page)) == 3


# ── Duplicate finder ───────────────────────────────────────────────────────────

@pytest.fixture()
def twice_imported(db):
    """The same three movements imported from Fineco (Excel) and Intesa-style (PDF) descriptions."""
    a = [
        add(db, date=date(2026, 6, 3), description="Pagamento Visa Debit presso ESSELUNGA MILANO", amount=87.50),
        add(db, date=date(2026, 6, 5), description="Pagamento carta - NETFLIX.COM AMSTERDAM", amount=17.99),
        add(db, date=date(2026, 6, 27), description="Bonifico da ACME SPA per STIPENDIO", amount=2800, type="income"),
    ]
    b = [
        add(db, date=date(2026, 6, 4), description="ESSELUNGA MILANO", amount=87.50),      # booked a day later
        add(db, date=date(2026, 6, 5), description="NETFLIX.COM AMSTERDAM", amount=17.99),
        add(db, date=date(2026, 6, 27), description="Accredito stipendio ACME SPA", amount=2800, type="income"),
    ]
    # Not duplicates: same amount but other merchant / another month / opposite direction
    add(db, date=date(2026, 6, 4), description="PAGAMENTO POS CONAD CITY", amount=87.50)
    add(db, date=date(2026, 7, 5), description="NETFLIX.COM AMSTERDAM", amount=17.99)
    add(db, date=date(2026, 6, 3), description="Rimborso ESSELUNGA MILANO", amount=87.50, type="income")
    return a, b


def test_find_groups(twice_imported):
    a, b = twice_imported
    groups = duplicates.find_groups()
    assert sorted(sorted(g.ids) for g in groups) == sorted(sorted([x.id, y.id]) for x, y in zip(a, b))
    netflix = next(g for g in groups if a[1].id in g.ids)
    esselunga = next(g for g in groups if a[0].id in g.ids)
    assert netflix.identical  # same day; only the bank's filler words ("Pagamento carta") differ
    assert not esselunga.identical  # booked one day apart


def test_identical_rows_are_flagged_identical(db):
    add(db, date=date(2026, 6, 1), description="AFFITTO GIUGNO", amount=800)
    add(db, date=date(2026, 6, 1), description="AFFITTO GIUGNO", amount=800)
    [group] = duplicates.find_groups()
    assert group.identical


def test_window(twice_imported):
    assert len(duplicates.find_groups(window_days=0)) == 2  # Esselunga is one day apart


def test_sensitivity(db):
    add(db, date=date(2026, 6, 1), description="AMAZON EU", amount=25)
    add(db, date=date(2026, 6, 1), description="AMAZON MARKETPLACE", amount=25)  # similarity ~0.45
    assert len(duplicates.find_groups(threshold=duplicates.SENSITIVITY["alta"])) == 1
    assert duplicates.find_groups(threshold=duplicates.SENSITIVITY["normale"]) == []


def test_duplicates_page_keep_one(client, twice_imported):
    a, b = twice_imported
    page = client.get("/transactions/duplicates").get_data(as_text=True)
    assert page.count("Tieni la selezionata") == 3
    # the card of the Esselunga group, and the id of its "keep" form
    card = next(c for c in page.split('class="card mb-16"') if f'name="keep" value="{a[0].id}"' in c)
    group_form = re.search(r'id="(keep-\d+)"', card).group(1)
    kept, dropped = a[0].id, b[0].id
    client.post("/transactions/duplicates/keep", data=form_data(page, group_form))
    remaining = {t.id for t in Transaction.query.all()}
    assert kept in remaining and dropped not in remaining  # the first (pre-selected) one is kept


def test_duplicates_dismiss_hides_the_group_for_good(client, twice_imported):
    a, b = twice_imported
    client.post("/transactions/duplicates/dismiss", data={"ids": [a[1].id, b[1].id]})
    assert DuplicateDismissal.query.count() == 1
    assert all(a[1].id not in g.ids for g in duplicates.find_groups())
    assert Transaction.query.count() == 9  # nothing deleted


def test_transactions_page_links_to_duplicates(client, twice_imported):
    page = client.get("/transactions/").get_data(as_text=True)
    assert "3 gruppi di possibili duplicati" in page


def test_deleting_a_transaction_removes_its_dismissals(client, twice_imported):
    a, b = twice_imported
    duplicates.dismiss([a[1].id, b[1].id])
    client.post(f"/transactions/{a[1].id}/delete")
    assert DuplicateDismissal.query.count() == 0  # ON DELETE CASCADE


def test_import_preview_warns_about_similar_transactions(client, db):
    """A movement already saved (typed by hand or from another export) is unchecked in the preview."""
    from tests.statements import fineco_xlsx
    add(db, date=date(2026, 6, 4), description="ESSELUNGA MILANO", amount=87.50)
    import io
    html = client.post("/export/bank", data={"file": (io.BytesIO(fineco_xlsx()), "f.xlsx")},
                       content_type="multipart/form-data").get_data(as_text=True)
    assert "Possibile duplicato di: 04/06/2026 · ESSELUNGA MILANO" in html
    data = form_data(html, "preview-form")
    assert "0" not in data["include"] and "1" in data["include"]  # Esselunga (row 0) unchecked
