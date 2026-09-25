from datetime import date, timedelta

import re

import pytest

from app.models.transaction import Transaction
from app.services import forecast
from tests.conftest import make_tx

TODAY = date(2026, 9, 15)


def assert_divs_balanced(html):
    assert len(re.findall(r"<div\b", html)) == len(re.findall(r"</div>", html))


def tx(d, description, amount, type="expense", category="Altro", **kw):
    return make_tx(date=d, description=description, amount=amount, type=type, category=category, **kw)


# ── Methods ────────────────────────────────────────────────────────────────────

def test_methods_on_a_known_series():
    history = [100, 200, 300, 400]
    assert forecast.predict("media", history, 2, 4) == [250, 250]
    assert forecast.predict("media", history, 1, 2) == [350]            # only the last N months
    assert forecast.predict("mediana", [100, 110, 900, 120], 1, 4) == [115]  # the one-off month is ignored
    assert forecast.predict("ponderata", history, 1, 4) == [300]        # (100·1 + 200·2 + 300·3 + 400·4) / 10
    ema = forecast.predict("esponenziale", history, 1, 4)[0]           # α = 0.4: between the mean and the last value
    assert 250 < ema < 400
    assert forecast.predict("trend", history, 3, 4) == [500, 600, 700]  # the line continues
    assert forecast.predict("trend", [300, 200, 100], 5, 3) == [0, 0, 0, 0, 0]  # amounts never go negative


def test_seasonal_method_uses_the_same_month_a_year_earlier():
    year = [100] * 11 + [500]                  # December costs more
    history = year + [110] * 11                # this year runs 10% higher
    predicted = forecast.predict("stagionale", history, 1, 3)
    assert predicted == [pytest.approx(550)]   # last December scaled by the recent level (+10%)
    # without a full year it falls back to the moving average
    assert forecast.predict("stagionale", [100, 200], 1, 6) == [150]


def test_empty_history_forecasts_zero():
    assert forecast.predict("trend", [], 3, 6) == [0, 0, 0]


def test_occurrences_follow_the_frequency_and_stop_at_the_end_date():
    rent = tx(date(2026, 1, 31), "Affitto", 700, is_recurring=True, recurrence="monthly")
    got = forecast.occurrences(rent, date(2026, 2, 1), date(2026, 5, 1))
    assert got == [date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]   # day clamped, not drifting
    gym = tx(date(2026, 3, 2), "Palestra", 10, is_recurring=True, recurrence="weekly", recurrence_end=date(2026, 3, 20))
    assert forecast.occurrences(gym, date(2026, 3, 1), date(2026, 4, 1)) == [date(2026, 3, 9), date(2026, 3, 16)]
    insurance = tx(date(2025, 11, 5), "Assicurazione", 400, is_recurring=True, recurrence="yearly")
    assert forecast.occurrences(insurance, date(2026, 1, 1), date(2027, 1, 1)) == [date(2026, 11, 5)]


# ── The forecast ───────────────────────────────────────────────────────────────

def household():
    """Six complete months (Mar–Aug 2026) plus the first half of September."""
    rows = []
    for m in range(3, 10):
        rows.append(tx(date(2026, m, 1), "Affitto", 700, category="Casa"))
        if m < 9:
            rows.append(tx(date(2026, m, 27), "Stipendio ACME", 2500, type="income", category="Stipendio"))
            rows.append(tx(date(2026, m, 10), "Esselunga", 300 + 20 * m, category="Alimentari"))
        rows.append(tx(date(2026, m, 5), "Giroconto", 1000, type="transfer", category="Giroconto"))
    # only the latest rent and salary are flagged: the earlier rows must not be counted twice
    rent = [r for r in rows if r.description == "Affitto"][-1]
    rent.is_recurring, rent.recurrence = True, "monthly"
    salary = [r for r in rows if r.description == "Stipendio ACME"][-1]
    salary.is_recurring, salary.recurrence = True, "monthly"
    rows.append(tx(date(2026, 9, 8), "Esselunga", 150, category="Alimentari"))
    return rows


def test_forecast_adds_scheduled_and_variable_parts():
    fc = forecast.build(household(), "media", 3, 6, TODAY)
    assert fc.history_months == 6
    assert [t.description for t in fc.scheduled] == ["Affitto", "Stipendio ACME"]
    assert fc.recurring_monthly == 1800
    october = fc.next_month
    assert october["label"] == "Ott 26"
    assert october["scheduled_income"] == 2500 and october["scheduled_expenses"] == 700
    # groceries: mean of Jun–Aug (420, 440, 460); rent and salary are not counted again as variable
    assert october["income"] == 2500
    assert october["expenses"] == pytest.approx(700 + 440)
    assert len(fc.months) == 7 and fc.months[0]["current"]
    # transfers don't change the balance
    assert fc.balance_now == pytest.approx(6 * 2500 - 7 * 700 - sum(300 + 20 * m for m in range(3, 9)) - 150)
    assert fc.final_balance == pytest.approx(fc.balance_now + sum(r["net"] for r in fc.months[1:])
                                             + (fc.months[0]["net"] - (0 - 700 - 150)))


def test_current_month_adds_what_is_still_to_come():
    fc = forecast.build(household(), "media", 3, 3, TODAY)
    september = fc.current
    assert fc.cutoff == date(2026, 9, 8)  # the last recorded movement, not today
    # salary on the 27th is still to come; rent (1st) and 150 of groceries are already recorded
    assert september["income"] == 2500
    remaining = (30 - 8) / 30
    assert september["expenses"] == pytest.approx(700 + 150 + 440 * remaining, abs=0.01)


def test_categories_compare_the_forecast_with_the_window_average():
    fc = forecast.build(household(), "media", 3, 3, TODAY)
    by_name = {c["category"]: c for c in fc.categories}
    assert by_name["Casa"]["scheduled"] == 700 and by_name["Casa"]["variable"] == 0
    assert by_name["Alimentari"]["variable"] == pytest.approx(440)
    assert by_name["Alimentari"]["average"] == pytest.approx(440)
    assert "Giroconto" not in by_name
    assert fc.categories[0]["type"] == "expense"


def test_methods_are_compared_on_the_past():
    rows = [tx(date(2026, m, 10), "Spesa", 100 * m, category="Alimentari") for m in range(1, 9)]
    fc = forecast.build(rows, "media", 4, 3, TODAY)
    by_key = {m["key"]: m for m in fc.methods}
    assert set(by_key) == set(forecast.METHODS)
    best = [m for m in fc.methods if m["best"]]
    assert [m["key"] for m in best] == ["trend"]           # steadily rising expenses: the trend wins
    assert by_key["trend"]["error"] == 0
    assert by_key["media"]["error"] > 0 and by_key["media"]["selected"]
    assert by_key["stagionale"]["fallback"]                # less than a year of history
    # the band spans every method's forecast
    for row in fc.months:
        assert row["low"] <= row["net"] <= row["high"]


def test_rolling_window_applies_to_incoming_flows():
    """Variable income (freelance fees) is estimated from the window exactly like expenses."""
    fees = [0, 0, 600, 900, 300]                        # May–Sep... last complete months: May–Aug
    rows = [tx(date(2026, m, 20), f"Fattura cliente {m}", a, type="income", category="Freelance")
            for m, a in zip(range(4, 9), fees) if a]
    fc = forecast.build(rows, "media", 3, 2, TODAY)
    assert fc.next_month["income"] == pytest.approx((600 + 900 + 300) / 3)
    assert fc.next_month["expenses"] == 0
    fc = forecast.build(rows, "mediana", 3, 2, TODAY)
    assert fc.next_month["income"] == 600
    by_name = {c["category"]: c for c in forecast.build(rows, "media", 2, 2, TODAY).categories}
    assert by_name["Freelance"]["type"] == "income" and by_name["Freelance"]["variable"] == pytest.approx(600)


def test_recurring_amounts_use_the_rolling_window_or_the_latest_amount():
    """A salary with a raise in August: the window mean lags, the latest amount follows it."""
    rows = [tx(date(2026, m, 27), "Stipendio ACME", a, type="income", category="Stipendio")
            for m, a in zip(range(3, 9), [2000, 2000, 2000, 2000, 2000, 2600])]
    rows[-1].is_recurring, rows[-1].recurrence = True, "monthly"
    rows.append(tx(date(2025, 11, 5), "Assicurazione casa", 400, category="Casa", is_recurring=True, recurrence="yearly"))
    rolling = forecast.build(rows, "media", 3, 3, TODAY, recurring="media")
    assert rolling.next_month["income"] == pytest.approx((2000 + 2000 + 2600) / 3)
    latest = forecast.build(rows, "media", 3, 3, TODAY, recurring="ultimo")
    assert latest.next_month["income"] == 2600
    # a yearly premium with no payment in the window keeps its latest amount
    november = [r for r in rolling.months if r["label"] == "Nov 26"][0]
    assert november["scheduled_expenses"] == 400
    assert rolling.upcoming[0]["amount"] == pytest.approx(2200)
    assert rolling.recurring_monthly == pytest.approx(2200 - 400 / 12, abs=0.01)
    # earlier rows of the flagged series are not counted again as variable income
    assert rolling.next_month["income"] == rolling.next_month["scheduled_income"]


def test_methods_are_measured_on_each_flow():
    """Income with a one-off month: the median wins; expenses rising steadily: the trend wins."""
    income = [1000, 1000, 5000, 1000, 1000, 1000, 1000, 1000]
    rows = [tx(date(2026, m, 27), "Compensi", a, type="income", category="Freelance") for m, a in zip(range(1, 9), income)]
    rows += [tx(date(2026, m, 10), "Spesa", 100 * m, category="Alimentari") for m in range(1, 9)]
    fc = forecast.build(rows, "media", 4, 3, TODAY)
    by_key = {m["key"]: m for m in fc.methods}
    assert [m["key"] for m in fc.methods if m["best_income"]] == ["mediana"]
    # the one-off month itself can't be foreseen (4000 off); after it the median is exact, the mean is not
    assert by_key["mediana"]["error_income"] == pytest.approx(4000 / 6, abs=0.01)
    assert by_key["media"]["error_income"] > by_key["mediana"]["error_income"]
    assert [m["key"] for m in fc.methods if m["best_expenses"]] == ["trend"]
    assert by_key["trend"]["error_expenses"] == 0
    for m in fc.methods:
        assert m["error"] == pytest.approx(m["error_income"] + m["error_expenses"])
    for row in fc.months:
        assert row["income_low"] <= row["income"] <= row["income_high"]
        assert row["expenses_low"] <= row["expenses"] <= row["expenses_high"]


def test_no_history():
    fc = forecast.build([], "media", 6, 3, TODAY)
    assert fc.history_months == 0 and fc.months[0]["net"] == 0 and fc.final_balance == 0
    assert all(m["error"] is None for m in fc.methods)


# ── Detection of recurring series ──────────────────────────────────────────────

def test_detects_regular_series_with_a_stable_amount():
    rows = [tx(date(2026, m, 12), "Netflix", 17.99, category="Abbonamenti") for m in range(5, 10)]
    rows += [tx(date(2026, 3, 1) + timedelta(days=7 * k), "Palestra", 10) for k in range(28)]
    rows += [tx(date(2026, m, 3), "Esselunga", a) for m, a in zip(range(5, 10), [80, 230, 45, 150, 310])]  # amount varies
    rows += [tx(date(2026, m, 20), "Vecchio abbonamento", 9.99) for m in range(1, 5)]  # stopped in April
    found = {c.template.description: c for c in forecast.detect_candidates(rows, TODAY)}
    assert set(found) == {"Netflix", "Palestra"}
    assert found["Netflix"].frequency == "monthly" and found["Netflix"].template.date == date(2026, 9, 12)
    assert found["Netflix"].next_date == date(2026, 10, 12)
    assert found["Palestra"].frequency == "weekly"


def test_flagged_series_are_not_suggested_again():
    rows = [tx(date(2026, m, 12), "Netflix", 17.99) for m in range(5, 10)]
    rows[-1].is_recurring = True
    assert forecast.detect_candidates(rows, TODAY) == []


# ── Pages ──────────────────────────────────────────────────────────────────────

def recent(months_back: int, day: int) -> date:
    today = date.today()
    y, m = forecast.shift_month(today.year, today.month, -months_back)
    return date(y, m, min(day, 28))


def test_page_renders_without_data(client, app):
    response = client.get("/forecast/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Servono dei movimenti" in html
    assert_divs_balanced(html)


def test_page_is_a_two_column_dashboard(client, db):
    db.session.add_all([tx(recent(k, 12), "Netflix", 17.99, category="Abbonamenti") for k in range(1, 6)])
    db.session.add_all([tx(recent(k, 3), "Esselunga", 100 + k, category="Alimentari") for k in range(1, 7)])
    db.session.add(tx(recent(1, 27), "Stipendio", 2500, type="income", category="Stipendio", is_recurring=True, recurrence="monthly"))
    db.session.commit()
    html = client.get("/forecast/").get_data(as_text=True)
    assert_divs_balanced(html)
    # one grid of two equal columns, with every panel in the default order
    assert html.count('class="fc-grid"') == 1 and "dash-grid" not in html
    assert re.findall(r'<section class="fc-widget" data-widget="(\w+)" data-span="(\d)"', html) == [
        (key, str(span)) for key, (_, span) in forecast.WIDGETS.items()]
    assert 'id="layout-edit"' in html and 'id="layout-bar"' in html
    for title in ("Netto mensile: storico e previsione", "Confronto dei metodi", "Saldo di cassa previsto",
                  "Mese per mese", "per categoria", "Prossime ricorrenti", "Sembrano ricorrenti", "Come funziona"):
        assert title in html
    for chart in ("netChart", "incomeChart", "expensesChart", "balanceChart"):
        assert f'id="{chart}"' in html
    assert "Entrate: storico e previsione" in html and "Uscite: storico e previsione" in html
    assert '<select name="recurring"' in html and "Err. entrate" in html and "Err. uscite" in html
    assert "Netflix" in html.split('<div class="card-header-title">Sembrano ricorrenti')[1]      # suggested
    assert "Stipendio" in html.split('<div class="card-header-title">Prossime ricorrenti')[1]    # scheduled
    for label, _ in forecast.METHODS.values():
        assert label in html
    assert 'href="/forecast/"' in client.get("/transactions/").get_data(as_text=True)  # sidebar link


def test_preferences_are_remembered_and_validated(client, app):
    assert forecast.preferences() == {"method": "media", "recurring": "media", "window": 6, "horizon": 12}
    response = client.post("/forecast/preferences", data={"method": "trend", "window": "9", "horizon": "24", "recurring": "ultimo"})
    assert response.status_code == 302
    assert forecast.preferences() == {"method": "trend", "recurring": "ultimo", "window": 9, "horizon": 24}
    html = client.get("/forecast/").get_data(as_text=True)
    assert 'name="window" value="9"' in html and '<option value="trend" selected>' in html
    # out of range or invalid values are clamped or ignored
    client.post("/forecast/preferences", data={"method": "magia", "window": "99", "horizon": "0", "recurring": "boh"})
    assert forecast.preferences() == {"method": "trend", "recurring": "ultimo", "window": 36, "horizon": 1}
    client.post("/forecast/preferences", data={"window": "abc"})
    assert forecast.preferences()["window"] == 6
    # values in the address are used for that page only
    html = client.get("/forecast/?method=mediana&window=3").get_data(as_text=True)
    assert '<option value="mediana" selected>' in html and 'name="window" value="3"' in html
    assert forecast.preferences()["method"] == "trend"


def test_confirming_a_suggestion_flags_the_latest_transaction(client, db):
    rows = [tx(recent(k, 12), "Netflix", 17.99, category="Abbonamenti") for k in range(1, 6)]
    db.session.add_all(rows)
    db.session.commit()
    latest = max(rows, key=lambda r: r.date)
    response = client.post(f"/forecast/recurring/{latest.id}", data={"frequency": "monthly"}, follow_redirects=True)
    assert "è ora una transazione ricorrente" in response.get_data(as_text=True)
    db.session.refresh(latest)
    assert latest.is_recurring and latest.recurrence == "monthly"
    assert Transaction.query.filter_by(is_recurring=True).count() == 1
    html = response.get_data(as_text=True)
    assert "Nessuna serie ricorrente da confermare" in html
    assert client.post(f"/forecast/recurring/{latest.id}", data={"frequency": "daily"}).status_code == 302
    assert client.post("/forecast/recurring/99999", data={"frequency": "monthly"}).status_code == 404


def test_transactions_can_be_filtered_to_recurring_ones(client, db):
    db.session.add_all([tx(date(2026, 6, 1), "Affitto", 700, is_recurring=True, recurrence="monthly"),
                        tx(date(2026, 6, 2), "Pizzeria Da Mario", 50)])
    db.session.commit()
    html = client.get("/transactions/?recurring=1").get_data(as_text=True)
    assert "Affitto" in html and "Pizzeria Da Mario" not in html
    assert "Pizzeria Da Mario" in client.get("/transactions/").get_data(as_text=True)


# ── Layout of the page ─────────────────────────────────────────────────────────

def test_layout_is_normalized():
    assert forecast.normalize_layout(None) == forecast.default_layout()
    items = forecast.normalize_layout([
        {"id": "months", "span": 2, "visible": False},
        {"id": "boh"}, "x", {"id": "months", "span": 1},     # unknown, malformed and repeated entries are dropped
        {"id": "net", "span": "7"},
    ])
    assert items[0] == {"id": "months", "span": 2, "visible": False}
    assert items[1] == {"id": "net", "span": 1, "visible": True}
    assert [w["id"] for w in items[2:]] == [k for k in forecast.WIDGETS if k not in ("months", "net")]  # the rest appended


def test_layout_is_saved_and_applied(client, db):
    db.session.add_all([tx(recent(k, 3), "Esselunga", 100 + k, category="Alimentari") for k in range(1, 4)])
    db.session.commit()
    widgets = [{"id": "balance", "span": 2, "visible": True}, {"id": "kpi", "span": 2, "visible": True},
               {"id": "methods", "span": 1, "visible": False}]
    response = client.post("/forecast/layout", json={"widgets": widgets})
    assert response.status_code == 200
    saved = response.get_json()["layout"]
    assert [w["id"] for w in saved[:3]] == ["balance", "kpi", "methods"] and len(saved) == len(forecast.WIDGETS)
    html = client.get("/forecast/").get_data(as_text=True)
    order = re.findall(r'<section class="fc-widget" data-widget="(\w+)" data-span="(\d)"[^>]*?( hidden)?>', html)
    assert order[:3] == [("balance", "2", ""), ("kpi", "2", ""), ("methods", "1", " hidden")]
    assert_divs_balanced(html)
    # reset
    assert client.post("/forecast/layout", json={"reset": True}).get_json()["layout"] == forecast.default_layout()
    assert forecast.layout() == forecast.default_layout()


def test_layout_endpoint_rejects_bad_input(client, app):
    assert client.post("/forecast/layout", data="nope", content_type="application/json").status_code == 400
    assert client.post("/forecast/layout", json={"widgets": "all"}).status_code == 400
    assert client.post("/forecast/layout", json=[1, 2]).status_code == 400
    assert forecast.layout() == forecast.default_layout()
