"""The round + on the Portafoglio pages adds positions (one, or many from a file) in the pop-up, as for transactions;
the dashboard overview shows what is invested and what is owed next to the period's income and expenses."""
from app.models.wealth import Holding


def test_the_round_plus_on_the_portfolio_offers_positions(client, db):
    page = client.get("/portfolio/").get_data(as_text=True)
    assert 'id="add-bubble" title="Nuova posizione"' in page
    assert "Posizione singola" in page and "Più posizioni da un file" in page
    assert "/portfolio/new?embed=1" in page and "/portfolio/import?embed=1" in page
    elsewhere = client.get("/dashboard").get_data(as_text=True)
    assert 'id="add-bubble" title="Nuova Transazione"' in elsewhere and "Posizione singola" not in elsewhere


def test_the_position_form_in_the_popup_closes_it_after_saving(client, db):
    done = "/transactions/embed-done?reload=1"
    page = client.get(f"/portfolio/new?embed=1&from=add&next={done}").get_data(as_text=True)
    assert "data-popup-back" in page and 'class="embedded"' in page
    response = client.post(f"/portfolio/new?embed=1&from=add&next={done}",
                           data={"name": "Fondo prova", "asset_class": "ETF", "quantity": "1", "avg_price": "100",
                                 "price_source": "auto"})
    assert response.status_code == 302 and response.headers["Location"].endswith(done)
    assert Holding.query.filter_by(name="Fondo prova").count() == 1


def test_the_file_import_in_the_popup_has_no_section_backup(client, db):
    page = client.get("/portfolio/import?embed=1&from=add").get_data(as_text=True)
    assert "data-close-embed" in page and 'id="archive"' not in page
    assert 'id="archive"' in client.get("/portfolio/import").get_data(as_text=True)


def test_the_overview_shows_portfolio_and_debts(client, db):
    page = client.get("/dashboard").get_data(as_text=True)
    assert "Portafoglio e debiti" in page and "Nessun debito" in page
