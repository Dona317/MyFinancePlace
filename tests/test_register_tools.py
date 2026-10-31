"""The register and dashboard tools: clusters (two-level spending), bank ↔ cash transfers, bulk edit, the review,
the window of the top figures and the custom chart series."""
from datetime import date

from app.models.account import Account
from app.models.cluster import ClusterRule
from app.models.transaction import Transaction
from app.services import analytics_clusters, cash, clusters, review
from tests.conftest import make_tx


def add(db, **values):
    tx = make_tx(**values)
    db.session.add(tx)
    db.session.commit()
    return tx


def bank(db, name="Conto", kind="current"):
    account = Account(name=name, kind=kind, currency="EUR")
    db.session.add(account)
    db.session.commit()
    return account


# ── Clusters ───────────────────────────────────────────────────────────────────

def test_a_discretionary_or_saving_category_gives_its_cluster(db):
    investing = add(db, description="Versamento", category="Investimenti", amount=50)
    assert clusters.suggest(investing) == clusters.SAVING
    groceries = add(db, description="Spesa", category="Alimentari", amount=40)
    assert clusters.suggest(groceries) == clusters.NECESSARY


def test_a_cluster_chosen_by_hand_is_remembered_for_similar_transactions(db):
    first = add(db, description="Esselunga spesa", counterparty="Esselunga", category="Alimentari", amount=30,
                cluster=clusters.LIFESTYLE)
    clusters.learn(first)
    assert ClusterRule.query.one().keyword == "esselunga"
    later = make_tx(description="Esselunga centro", counterparty="Esselunga", category="Alimentari", amount=20)
    assert clusters.suggest(later) == clusters.LIFESTYLE


def test_income_and_transfers_have_no_cluster(db):
    assert clusters.suggest(make_tx(type="income", category="Stipendio")) is None
    assert clusters.suggest(make_tx(type="transfer", category="Investimenti")) is None


def test_two_level_breakdown_adds_up_to_the_expenses(sample_data):
    rows = analytics_clusters.cluster_breakdown(date(2026, 1, 1), date(2027, 1, 1))
    total = sum(row["amount"] for row in rows)
    assert total == 1400  # June 800 + May 600; the income and the transfer are left out
    for row in rows:
        assert abs(sum(c["amount"] for c in row["categories"]) - row["amount"]) < 0.01


# ── Bank ↔ cash ────────────────────────────────────────────────────────────────

def test_a_bank_withdrawal_becomes_a_transfer_to_the_cash_account(db):
    current = bank(db)
    tx = add(db, description="PRELIEVO BANCOMAT 20", amount=20, account_id=current.id, category="Altro")
    assert cash.recognise_all() == 1
    db.session.refresh(tx)
    assert tx.type == "transfer" and tx.account_id == current.id
    assert tx.counter_account.kind == "cash"


def test_a_cash_deposit_goes_back_to_the_bank(db):
    current = bank(db)
    tx = add(db, description="Versamento contanti", type="income", amount=100, account_id=current.id)
    cash.recognise_all()
    db.session.refresh(tx)
    assert tx.type == "transfer" and tx.counter_account_id == current.id
    assert tx.account.kind == "cash"


def test_ordinary_expenses_are_not_moved(db):
    current = bank(db)
    add(db, description="Supermercato", amount=40, account_id=current.id)
    assert cash.recognise_all() == 0
    assert Account.query.filter_by(kind="cash").count() == 0  # no cash account made for nothing


# ── Bulk edit ──────────────────────────────────────────────────────────────────

def test_bulk_edit_changes_every_transaction_of_the_search(client, db):
    add(db, description="Stipendio marzo", type="income", amount=1000)
    add(db, description="Stipendio aprile", type="income", amount=1000)
    add(db, description="Affitto", amount=600)
    client.post("/transactions/bulk-edit", data={"scope": "search", "q": "Stipendio", "type_to": "expense"})
    types = {tx.description: tx.type for tx in Transaction.query.all()}
    assert types == {"Stipendio marzo": "expense", "Stipendio aprile": "expense", "Affitto": "expense"}


def test_bulk_edit_of_the_ticked_ones_only(client, db):
    keep = add(db, description="Uno", amount=10)
    pick = add(db, description="Due", amount=10)
    client.post("/transactions/bulk-edit", data={"scope": "selection", "ids": [pick.id], "category_to": "Svago"})
    db.session.refresh(keep)
    db.session.refresh(pick)
    assert pick.category == "Svago" and keep.category != "Svago"


# ── Review ─────────────────────────────────────────────────────────────────────

def test_review_finds_an_income_booked_as_expense(db):
    tx = add(db, description="Stipendio giugno", amount=1800, type="expense")
    findings, note = review.review([tx], categories=[])
    assert note is None
    assert [(f.kind, f.value) for f in findings] == [("type", "income")]


def test_review_suggests_a_transfer_for_an_investment(db):
    tx = add(db, description="Acquisto ETF MSCI World", amount=500, type="expense")
    findings, _ = review.review([tx], categories=[])
    assert [(f.kind, f.value) for f in findings] == [("type", "transfer")]


def test_applying_a_suggestion_changes_the_transaction(client, db):
    tx = add(db, description="Stipendio giugno", amount=1800, type="expense")
    client.post("/transactions/review/apply", data={"apply": [f"{tx.id}|type|income"]})
    db.session.refresh(tx)
    assert tx.type == "income"


# ── Dashboard ──────────────────────────────────────────────────────────────────

def test_the_window_of_the_top_figures_is_kept(client, db):
    client.post("/dashboard/kpi-period", data={"period": "last_3"})
    page = client.get("/dashboard").get_data(as_text=True)
    assert '<option value="last_3" selected' in page
    assert "Ultimi 3 mesi" in page


def test_an_unknown_window_is_ignored(client, db):
    client.post("/dashboard/kpi-period", data={"period": "tutto-l-anno-2099"})
    page = client.get("/dashboard").get_data(as_text=True)
    assert '<option value="this_month" selected' in page


def test_custom_chart_series(client, sample_data):
    data = client.get("/dashboard/series?metric=net&period=year&year=2026").get_json()
    assert len(data["labels"]) == 12
    assert data["values"][5] == 2200  # June: 3000 income − 800 expenses
    rate = client.get("/dashboard/series?metric=savings_rate&period=year&year=2026").get_json()
    assert rate["values"][5] == 73.3  # the savings rate, to a tenth as elsewhere in the app


def test_custom_chart_rejects_an_unknown_metric(client):
    assert client.get("/dashboard/series?metric=nope").status_code == 400


def test_signed_in_user_menu_holds_account_settings_and_sign_out(client, db):
    from app.services import users
    from tests.test_auth import login_on, sign_in  # noqa: F401 - sign-in fixture helpers
    users.create("anna", "password-1", is_admin=True)
    sign_in(client)
    html = client.get("/transactions/").get_data(as_text=True)
    menu = html.split('id="user-menu" role="menu" hidden>')[1].split("</div>")[0]
    assert 'href="/settings/"' in menu and 'href="/settings/account"' in menu and "/auth/logout" in menu
