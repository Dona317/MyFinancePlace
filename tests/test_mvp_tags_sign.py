"""Signed amounts in the form, the counterparty as the first tag, the tag pool, the AI tag to confirm, the dashboard charts."""
from datetime import date

import pytest

from app.models.transaction import Transaction
from app.routes.transactions import all_tags, parse_tags
from app.services import analytics
from app.services.ai_classification import AI_TAG
from tests.conftest import make_tx


@pytest.mark.parametrize("amount, extra, kind", [
    ("-45,20", {}, "expense"),
    ("1.200", {}, "income"),
    ("300", {"transfer": "1"}, "transfer"),
    ("-300", {"transfer": "1"}, "transfer"),
])
def test_the_sign_gives_the_type(client, db, amount, extra, kind):
    client.post("/transactions/new", data={"date": "2026-06-01", "amount": amount, "description": "x"} | extra)
    tx = Transaction.query.one()
    assert tx.type == kind and tx.amount > 0  # stored as before: positive amount + type


def test_edit_form_shows_the_sign(client, db):
    expense, income = make_tx(amount=12.5, type="expense"), make_tx(amount=80, type="income")
    db.session.add_all([expense, income])
    db.session.commit()
    assert 'value="-12,50"' in client.get(f"/transactions/{expense.id}/edit").get_data(as_text=True)
    assert 'value="80,00"' in client.get(f"/transactions/{income.id}/edit").get_data(as_text=True)


def test_tags_counterparty_and_pool(client, db):
    assert parse_tags(" Esselunga, spesa ,esselunga,, casa ") == ["Esselunga", "spesa", "casa"]
    client.post("/transactions/new", data={"date": "2026-06-01", "amount": "-30", "description": "Spesa",
                                           "tags": "Esselunga, spesa"})
    tx = Transaction.query.one()
    assert tx.counterparty == "Esselunga" and tx.tags == ["Esselunga", "spesa"]
    db.session.add(make_tx(tags=["spesa", "casa"]))
    db.session.commit()
    assert all_tags()[0] == "spesa" and set(all_tags()) == {"Esselunga", "spesa", "casa"}  # most used first
    page = client.get("/transactions/new").get_data(as_text=True)
    assert "data-tag-input" in page and "&#34;spesa&#34;" in page and 'name="counterparty"' not in page
    # the list: no counterparty column, tags as links to filter; income with its "+"
    html = client.get("/transactions/?tag=casa").get_data(as_text=True)
    assert ">Controparte<" not in html and 'class="tag-chip"' in html
    assert html.count('class="bulk-select') == 1  # only the one tagged "casa"


def test_ai_tag_is_confirmed_with_one_click(client, db):
    tx = make_tx(tags=["Coop", AI_TAG])
    other = make_tx(tags=[AI_TAG])
    db.session.add_all([tx, other])
    db.session.commit()
    html = client.get("/transactions/").get_data(as_text=True)
    assert "tag-chip tag-ai" in html and "Da confermare (AI): 2" in html
    client.post("/transactions/confirm-ai", data={"ids": [str(tx.id)]})
    assert db.session.get(Transaction, tx.id).tags == ["Coop"] and AI_TAG in db.session.get(Transaction, other.id).tags


def test_income_and_expense_series_for_the_dashboard(client, db):
    db.session.add_all([
        make_tx(date=date(2026, 1, 10), category="Stipendio", type="income", amount=2000),
        make_tx(date=date(2026, 2, 10), category="Stipendio", type="income", amount=2000),
        make_tx(date=date(2026, 2, 12), category="Dividendi e cedole", type="income", amount=50),
        make_tx(date=date(2026, 1, 5), category="Casa", amount=800),
        make_tx(date=date(2026, 2, 5), category="Casa", amount=800),
        make_tx(date=date(2026, 2, 6), category="Svago", amount=40),
    ])
    db.session.commit()
    trend = analytics.monthly_category_trend(2026, 1, "income", months=3, other=True)
    assert trend["labels"] == ["Gen", "Feb", "Mar"]
    assert trend["datasets"][0] == {"label": "Stipendio", "data": [2000.0, 2000.0, 0.0]}
    assert trend["datasets"][1]["label"] == "Altre" and trend["datasets"][1]["data"] == [0.0, 50.0, 0.0]
    cumulative = analytics.cumulative_series(2026, months=3)
    assert cumulative["income_cumulative"] == [2000.0, 4050.0, 4050.0]
    assert cumulative["expenses_cumulative"] == [800.0, 1640.0, 1640.0]
    html = client.get("/dashboard?year=2026").get_data(as_text=True)
    for canvas in ("expensePieChart", "incomePieChart", "expenseTrendChart", "incomeTrendChart", "cumulativeChart"):
        assert f'id="{canvas}"' in html
    assert "Dividendi e cedole" in html.split('id="incomePieChart"')[1].split("</ul>")[0]
