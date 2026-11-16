"""T09 (16 Nov 2026): the horizon of Previsioni is chosen in the period box of the page bar and remembered; a period
brought by a link from another page says that it changed."""
from app.services import forecast, shared_period


def test_the_horizon_of_previsioni_is_in_the_period_box(app, client, db):
    page = client.get("/forecast/").get_data(as_text=True)
    bar = page[page.index('id="period-form"'):][:1500]
    assert 'name="horizon"' in bar and "Prossimi 12 mesi" in bar and page.count('name="horizon"') == 1
    response = client.get("/forecast/?remember=1&horizon=6")  # what the box sends
    assert response.status_code == 302 and "remember" not in response.headers["Location"]
    with app.test_request_context():
        assert forecast.preferences()["horizon"] == 6
    client.get("/forecast/?horizon=24")  # a link with a horizon: shown, not kept
    with app.test_request_context():
        assert forecast.preferences()["horizon"] == 6
    client.post("/forecast/preferences", data={"method": "trend"})  # the settings below keep the horizon of the box
    with app.test_request_context():
        assert forecast.preferences() == {"method": "trend", "recurring": "media", "window": 6, "horizon": 6}


def test_a_period_brought_by_a_link_says_that_it_changed(app, client, db):
    page = client.get("/transactions/?year=2025&part=M03", headers={"Referer": "http://localhost/dashboard"})
    html = page.get_data(as_text=True)
    assert "alert-info" in html and "Periodo: Mar 2025" in html and "bi-info-circle" in html
    with app.test_request_context():
        assert shared_period.saved().part == "M03"
    again = client.get("/transactions/?year=2025&part=M03", headers={"Referer": "http://localhost/dashboard"})
    assert "Periodo: Mar 2025" not in again.get_data(as_text=True)  # already the shared period: nothing changed
    box = client.get("/transactions/?year=2025&part=M04", headers={"Referer": "http://localhost/transactions/?q=x"})
    assert "Periodo:" not in box.get_data(as_text=True)  # chosen in the box of the page itself: no notice
    month = client.get("/transactions/?month=2025-06", headers={"Referer": "http://localhost/reports/"})
    assert "Periodo: Giu 2025" in month.get_data(as_text=True)  # a month clicked on a chart of another page
