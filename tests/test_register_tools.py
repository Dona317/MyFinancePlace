"""The tools of the October review: spending groups (two levels), the review of the register, bulk edit, the
dashboard's windows and blocks, the accounts' bank / number / favourite and the account of an import."""
from datetime import date

from app.models.account import Account
from app.models.cluster import ClusterRule
from app.models.transaction import Transaction
from app.services import accounts, analytics_clusters, clusters, dashboard_prefs, review
from tests.conftest import make_tx


def add(db, **values):
    tx = make_tx(**values)
    db.session.add(tx)
    db.session.commit()
    return tx


def bank(db, name="Conto", kind="current", **values):
    account = Account(name=name, kind=kind, currency="EUR", **values)
    db.session.add(account)
    db.session.commit()
    return account


# ── Spending groups ────────────────────────────────────────────────────────────

def test_a_saving_category_gives_its_group(db):
    assert clusters.suggest(add(db, description="Versamento", category="Investimenti", amount=50)) == clusters.SAVING
    assert clusters.suggest(add(db, description="Spesa", category="Alimentari", amount=40)) == clusters.NECESSARY


def test_a_group_chosen_by_hand_is_remembered_for_similar_transactions(db):
    first = add(db, description="Esselunga spesa", counterparty="Esselunga", category="Alimentari", amount=30,
                cluster=clusters.LIFESTYLE)
    clusters.learn(first)
    assert ClusterRule.query.one().keyword == "esselunga"
    later = make_tx(description="Esselunga centro", counterparty="Esselunga", category="Alimentari", amount=20)
    assert clusters.suggest(later) == clusters.LIFESTYLE


def test_income_and_transfers_have_no_group(db):
    assert clusters.suggest(make_tx(type="income", category="Stipendio")) is None
    assert clusters.suggest(make_tx(type="transfer", category="Investimenti")) is None


def test_two_level_breakdown_adds_up_to_the_expenses(sample_data):
    rows = analytics_clusters.cluster_breakdown(date(2026, 1, 1), date(2027, 1, 1))
    assert sum(row["amount"] for row in rows) == 1400  # June 800 + May 600; income and the transfer left out
    for row in rows:
        assert abs(sum(c["amount"] for c in row["categories"]) - row["amount"]) < 0.01


def test_the_form_saves_the_group_and_remembers_it(client, db):
    client.post("/transactions/new", data={"date": "2026-06-01", "description": "Cinema Odeon", "amount": "-12",
                                           "category": "Svago", "tags": "Odeon", "cluster": clusters.LIFESTYLE})
    assert Transaction.query.one().cluster == clusters.LIFESTYLE
    assert ClusterRule.query.one().cluster == clusters.LIFESTYLE


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
    client.post("/transactions/bulk-edit", data={"scope": "selection", "ids": [pick.id], "category_to": "Svago",
                                                 "recurring_to": "yes"})
    db.session.refresh(keep)
    db.session.refresh(pick)
    assert (pick.category, pick.is_recurring, pick.recurrence) == ("Svago", True, "monthly")
    assert keep.category != "Svago" and not keep.is_recurring


def test_bulk_edit_needs_a_change(client, db):
    tx = add(db, description="Uno", amount=10)
    response = client.post("/transactions/bulk-edit", data={"scope": "selection", "ids": [tx.id]}, follow_redirects=True)
    assert "Scegli almeno una modifica" in response.get_data(as_text=True)


def test_list_filters_by_a_date_range(client, db):
    add(db, description="Prima", date=date(2026, 3, 1), amount=1)
    add(db, description="Dentro", date=date(2026, 3, 15), amount=1)
    html = client.get("/transactions/?start=2026-03-10&end=2026-03-31").get_data(as_text=True)
    rows = html.split("<tbody>")[1].split("</tbody>")[0]
    assert "Dentro" in rows and "Prima" not in rows


def test_the_form_is_a_full_screen_page_with_a_close_button(client, db):
    tx = add(db, description="Pizza", amount=20)
    form = client.get(f"/transactions/{tx.id}/edit?next=/transactions/").get_data(as_text=True)
    assert 'class="focus"' in form and 'id="sidebar"' not in form and 'id="form-close"' in form
    assert 'href="/transactions/" class="btn btn-ghost btn-icon form-close"' in form  # the X goes back
    assert 'id="f-type" value="expense"' in form and "type-switch" in form


def test_a_new_transaction_is_an_expense_unless_switched_or_signed(client, db):
    base = {"date": "2026-06-01", "description": "X"}
    client.post("/transactions/new", data=base | {"amount": "10", "type": "expense"})
    client.post("/transactions/new", data=base | {"amount": "10", "type": "income"})
    client.post("/transactions/new", data=base | {"amount": "+10", "type": "expense"})  # the sign wins
    client.post("/transactions/new", data=base | {"amount": "-10", "type": "income"})
    assert [t.type for t in Transaction.query.order_by(Transaction.id)] == ["expense", "income", "income", "expense"]


def test_a_recurring_one_ends_after_the_remaining_payments(client, db):
    client.post("/transactions/new", data={"date": "2026-06-15", "description": "Rata auto", "amount": "250",
                                           "type": "expense", "is_recurring": "on", "recurrence": "monthly",
                                           "recurrence_end_mode": "count", "recurrence_count": "3"})
    tx = Transaction.query.one()
    assert tx.recurrence_end == date(2026, 8, 15)  # June, July, August


def test_the_import_page_is_its_own(client, db):
    imports = client.get("/export/import").get_data(as_text=True)
    exports = client.get("/export/").get_data(as_text=True)
    assert 'id="bank-import"' in imports and 'id="bank-import"' not in exports and 'id="backup"' in exports


# ── Review of the register ─────────────────────────────────────────────────────

def test_review_finds_an_income_booked_as_expense(db):
    tx = add(db, description="Stipendio giugno", amount=1800, type="expense")
    findings, note = review.review([tx], categories=[])
    assert note is None and [(f.kind, f.value) for f in findings] == [("type", "income")]


def test_review_suggests_a_transfer_for_an_investment(db):
    tx = add(db, description="Acquisto ETF MSCI World", amount=500, type="expense")
    findings, _ = review.review([tx], categories=[])
    assert [(f.kind, f.value) for f in findings] == [("type", "transfer")]


def test_review_moves_a_withdrawal_to_the_cash_wallet(client, db):
    current = bank(db)
    tx = add(db, description="PRELIEVO BANCOMAT", amount=50, type="expense", account_id=current.id)
    findings, _ = review.review([tx], categories=[])
    assert [f.kind for f in findings] == ["cash"]
    client.post("/transactions/review/apply", data={"apply": [findings[0].token]})
    db.session.refresh(tx)
    assert tx.type == "transfer" and tx.counter_account.kind == "cash"


def test_applying_a_suggestion_changes_the_transaction(client, db):
    tx = add(db, description="Stipendio giugno", amount=1800, type="expense")
    client.post("/transactions/review/apply", data={"apply": [f"{tx.id}|type|income"]})
    db.session.refresh(tx)
    assert tx.type == "income"


# ── Dashboard ──────────────────────────────────────────────────────────────────

def test_a_card_keeps_its_own_window(client, db):
    response = client.post("/dashboard/window", json={"card": "income", "window": {"period": "last_n", "n": 4}})
    assert response.get_json()["label"] == "Ultimi 4 mesi"
    assert dashboard_prefs.window("income") == {"period": "last_n", "n": 4}
    assert dashboard_prefs.window("expenses") == {"period": "this_month"}  # the others keep the default
    assert client.post("/dashboard/window", json={"card": "income", "window": {"period": "nope"}}).status_code == 400
    client.post("/dashboard/windows/reset")
    assert dashboard_prefs.window("income") == {"period": "this_month"}


def test_a_custom_window_covers_both_dates(db):
    start, end = dashboard_prefs.window_range({"period": "custom", "start": "2026-03-10", "end": "2026-03-01"})
    assert (start, end) == (date(2026, 3, 1), date(2026, 3, 11))  # dates in any order, the last day included


def test_the_layout_is_saved_and_cleaned(client, db):
    client.post("/dashboard/layout", json={"widgets": [{"id": "health", "span": 3}, {"id": "nope"}, {"id": "health"}]})
    layout = dashboard_prefs.layout()
    assert layout[0] == {"id": "health", "span": 3, "height": 0, "visible": True}
    assert len(layout) == len(dashboard_prefs.WIDGETS)  # unknown and repeated blocks dropped, missing ones added
    assert dashboard_prefs.settings_order()[0] == "dashboard_health"  # Settings follows the same order
    page = client.get("/settings/").get_data(as_text=True)
    assert page.index('name="dashboard_health"') < page.index('name="dashboard_cashflow_chart"')


def test_a_block_keeps_the_height_chosen(client, db):
    client.post("/dashboard/layout", json={"widgets": [{"id": "recent", "span": 2, "height": 2}, {"id": "health", "height": 9}]})
    layout = {w["id"]: w for w in dashboard_prefs.layout()}
    assert layout["recent"]["height"] == 2 and layout["health"]["height"] == 0  # an unknown height: automatic
    assert 'data-widget="recent" data-span="2" data-height="2"' in client.get("/dashboard").get_data(as_text=True)


def test_dashboard_renders_with_data(client, sample_data):
    html = client.get("/dashboard?year=2026&part=Q2").get_data(as_text=True)
    assert 'id="cashFlowChart"' in html and 'data-widget="health"' in html and "kpi-strip" in html
    assert "start=2026-04-01" in html and "end=2026-06-30" in html  # the pies cover the second quarter


def test_the_period_can_span_several_years(client, sample_data):
    html = client.get("/dashboard?year=2026&year_to=2025&part=Q2").get_data(as_text=True)
    # from 2025 to 2026 (any order), whole years: no quarter, the cards and the charts over both
    assert "2025–2026" in html and 'id="dash-part" name="part"' in html and "Anni interi" in html
    assert "start=2025-01-01" in html and "end=2026-12-31" in html
    single = client.get("/dashboard?year=2026&year_to=2026&part=year").get_data(as_text=True)
    assert "Tutto l’anno" in single and "2025–2026" not in single


def test_settings_save_keeps_the_tab_and_the_dashboard_choices(client, db):
    response = client.post("/settings/save", data={"tab": "moduli", "dashboard_forecast": "year",
                                                   "dashboard_default_window": "last_n", "dashboard_default_months": "6"})
    assert response.headers["Location"].endswith("#moduli")
    assert dashboard_prefs.forecast_choice() == "year"
    assert dashboard_prefs.default_window() == {"period": "last_n", "n": 6}


# ── Accounts and the account of an import ─────────────────────────────────────

def test_one_favourite_account_at_a_time(client, db):
    first, second = bank(db, "Fineco 1"), bank(db, "Fineco 2")
    client.post(f"/accounts/{first.id}/favorite")
    client.post(f"/accounts/{second.id}/favorite")
    db.session.refresh(first)
    db.session.refresh(second)
    assert (first.favorite, second.favorite) == (False, True) and accounts.favorite() == second


def test_codes_are_kept_whole_and_shown_masked(client, db):
    account = bank(db, "Fineco 1", bank="Fineco", account_number="00012345678", iban="IT60X0542811101000000123456")
    assert accounts.masked(account.iban) == "•••• 3456"
    html = client.get("/accounts/").get_data(as_text=True)
    assert "•••• 5678" in html and 'data-copy="00012345678"' in html and "Fineco" in html


def test_the_statement_proposes_the_account_of_its_iban(db):
    bank(db, "Fineco 1", iban="IT60X0542811101000000123456")
    other = bank(db, "Intesa", favorite=True)
    assert accounts.found_in("Estratto conto IBAN IT60 X054 2811 1010 0000 0123 456").name == "Fineco 1"
    assert accounts.found_in("nessun codice") is None
    assert accounts.favorite() == other


def test_import_needs_the_account(client, db):
    bank(db, "Fineco 1")
    response = client.post("/export/bank/confirm", data={"payload": "x"})
    assert response.status_code == 302  # an invalid payload is refused before anything is saved


def test_the_cards_on_top_keep_order_width_and_visibility(client, db):
    client.post("/dashboard/layout", json={"kpis": [{"id": "debt", "span": 2}, {"id": "income", "visible": False},
                                                    {"id": "nope"}, {"id": "debt"}, {"id": "tbd", "span": 5}]})
    kpis = dashboard_prefs.kpi_layout()
    assert kpis[0] == {"id": "debt", "span": 2, "visible": True}
    assert kpis[1]["visible"] is False and kpis[2] == {"id": "tbd", "span": 1, "visible": True}  # a wrong width: one
    assert len(kpis) == len(dashboard_prefs.KPI_CARDS)
    page = client.get("/dashboard").get_data(as_text=True)
    assert 'data-widget="debt" data-span="2"' in page and ">TBD<" in page
    assert client.post("/dashboard/layout", json={"reset": True}).status_code == 200
    assert dashboard_prefs.kpi_layout() == dashboard_prefs.default_kpis()


def test_income_and_expenses_are_sections_of_their_own(client, sample_data):
    page = client.get("/reports/spending?period=custom&start=2026-01-01&end=2026-12-31").get_data(as_text=True)
    assert "Netto del periodo" in page and "/accounting/cash-flow?year=2026" in page
    assert 'name="tab"' not in page  # the period and filters stay on Uscite
    assert "Entrate" in client.get("/reports/income").get_data(as_text=True)
    flow = client.get("/accounting/cash-flow?year=2026").get_data(as_text=True)
    assert "/reports/income?" in flow and "/reports/spending?" in flow and 'aria-current="page"' in flow


def test_accounting_opens_on_its_first_tab(client, db):
    response = client.get("/accounting/")
    assert response.status_code == 302 and response.headers["Location"].endswith("/accounting/balance-sheet")
    page = client.get("/accounting/growth").get_data(as_text=True)
    assert page.count('class="statement-tab"') == 4 and "Crescita del patrimonio" in page


def test_income_and_expenses_have_palettes_of_their_own(client, sample_data):
    from app.services import palettes
    page = client.get("/dashboard").get_data(as_text=True)
    assert "--inc-1:#12B886" in page and "--exp-1:#FA5252" in page and "var(--exp-1)" in page
    client.post("/settings/save", data={"palette_income": "blu", "palette_expense": "viola", "tab": "visualizza"})
    page = client.get("/dashboard").get_data(as_text=True)
    assert f"--inc-1:{palettes.INCOME['blu'][1][0]}" in page and f"--exp-1:{palettes.EXPENSE['viola'][1][0]}" in page
    assert not set(palettes.INCOME["verdi"][1]) & set(palettes.EXPENSE["caldi"][1])  # the defaults never share a colour
    assert palettes.chosen({"palette_income": "nope"})[0] == palettes.INCOME["verdi"][1]


def test_the_round_plus_opens_a_small_window_and_the_form_in_a_pop_up(client, db):
    page = client.get("/dashboard").get_data(as_text=True)
    assert 'id="add-chooser"' in page and "/transactions/new?embed=1&amp;next=/transactions/embed-done&amp;from=add" in page
    assert "/export/import?embed=1&amp;only=bank" in page
    only_bank = client.get("/export/import?embed=1&only=bank").get_data(as_text=True)
    assert 'target="_top"' in only_bank and "mappatura manuale" not in only_bank  # the bank statement only
    response = client.post("/transactions/new", data={"date": "2026-10-15", "description": "Pranzo", "amount": "12",
                                                     "type": "expense", "next": "/transactions/embed-done", "embed": "1"})
    assert response.headers["Location"].endswith("/transactions/embed-done")
    done = client.get("/transactions/embed-done").get_data(as_text=True)
    assert '"tx-done"' in done and "Transazione aggiunta." in done  # the message goes to the page under the pop-up
