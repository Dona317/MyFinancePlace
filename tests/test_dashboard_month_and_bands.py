"""22 Nov 2026: income and expenses of the period under «Come sto» (Panoramica), of the month under way in «Questo
mese»; «Nel tempo» and «Futuro» open; the cash-flow chart shown again."""
from datetime import date, timedelta

from app.services import accounts, dashboard_charts, dashboard_prefs, settings_store
from app.services.periods import add_months
from tests.conftest import make_tx


def test_the_month_card_counts_the_month_only(client, db):
    today = date.today()
    first = today.replace(day=1)
    last_month = add_months(first, -1)
    db.session.add_all([
        make_tx(date=first, description="Stipendio", amount=2000, type="income", category="Stipendio"),
        make_tx(date=first, description="Affitto", amount=500, category="Casa"),
        make_tx(date=first, description="Riconciliazione", amount=900, category=accounts.reconciliation_category()),
        make_tx(date=last_month, description="Stipendio", amount=1800, type="income", category="Stipendio"),
        make_tx(date=last_month, description="Affitto", amount=600, category="Casa"),
        make_tx(date=first - timedelta(days=400), description="Molto prima", amount=9999, category="Casa"),
    ])
    db.session.commit()
    card = dashboard_charts.month_totals(today)
    assert card["now"]["income"] == 2000 and card["now"]["expenses"] == 500  # no reconciliation, no older months
    assert card["now"]["savings_rate"] == 75.0
    assert card["previous"]["income"] == 1800 and card["previous"]["expenses"] == 600
    assert card["average"] == {"income": 150.0, "expenses": 50.0, "savings_rate": 66.7}
    page = client.get("/dashboard?view=month").get_data(as_text=True)
    assert 'data-widget="month_totals"' in page and f"Entrate e uscite — {card['label']}" in page
    assert "Media 12 mesi" in page and 'data-widget="period_totals"' not in page


def test_panoramica_shows_the_period_card_first_and_every_band_open(client, db):
    page = client.get("/dashboard").get_data(as_text=True)
    assert page.index('data-widget="period_totals"') < page.index('data-band="month"')  # under «Come sto»
    assert all(f'data-band="{band}" open' in page for band in ("month", "time", "future"))
    assert 'data-widget="cashflow"' in page and "mfp-dash-band-v2-" in page


def test_blocks_hidden_before_are_shown_once(client, db):
    saved = [dict(w, visible=False) if w["id"] in ("period_totals", "cashflow", "expense_pie") else w
             for w in dashboard_prefs.default_layout()]
    settings_store.set_json(dashboard_prefs.LAYOUT_SETTING, saved)
    settings_store.set_json(dashboard_prefs.PRESETS_SETTING, {"active": 1, "items": [{"name": "P", "layout": saved}]})
    assert dashboard_prefs.reveal() == ["period_totals", "cashflow", "sankey"]
    shown = {w["id"]: w["visible"] for w in dashboard_prefs.layout()}
    assert shown["period_totals"] and shown["cashflow"] and shown["sankey"] and not shown["expense_pie"]
    preset = settings_store.get_json(dashboard_prefs.PRESETS_SETTING)["items"][0]["layout"]
    assert all(w["visible"] for w in preset if w["id"] in ("period_totals", "cashflow"))
    hidden_again = [dict(w, visible=False) if w["id"] == "cashflow" else w for w in dashboard_prefs.layout()]
    dashboard_prefs.save_layout(hidden_again)
    assert dashboard_prefs.reveal() == []  # once: hidden afterwards, it stays hidden
    assert not {w["id"]: w["visible"] for w in dashboard_prefs.layout()}["cashflow"]


def test_reveal_with_nothing_saved(db):
    assert dashboard_prefs.reveal() == ["period_totals", "cashflow", "sankey"]


def test_the_flow_of_money_is_in_come_sto_and_shown_again_once(client, db):
    from app.services import dashboard_prefs, settings_store
    assert dashboard_prefs.BAND_OF["sankey"] == "now" and "sankey" not in dashboard_prefs.DEFAULT_HIDDEN
    saved = [dict(item, visible=item["id"] != "sankey") for item in dashboard_prefs.default_layout()]
    settings_store.set_json(dashboard_prefs.LAYOUT_SETTING, saved)
    settings_store.set_json("ui.settings", {"dashboard_sankey": False})
    settings_store.set_json(dashboard_prefs.REVEALED_SETTING, ["cashflow", "period_totals"])
    assert dashboard_prefs.reveal() == ["sankey"]
    assert next(w for w in dashboard_prefs.layout() if w["id"] == "sankey")["visible"]
    assert settings_store.get_json("ui.settings", expect=dict)["dashboard_sankey"] is True
    assert dashboard_prefs.reveal() == []
