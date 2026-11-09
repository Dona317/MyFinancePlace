"""
F70: the asset class (azionario, obbligazionario, oro…) apart from the instrument (ETF, azione, fondo…): estimated
from the instrument and the name until the user sets it, one chart each on the positions page.
"""
from decimal import Decimal

import pytest

from app.models.wealth import Holding
from app.services import asset_classes, wealth


@pytest.mark.parametrize("instrument, name, ticker, expected", [
    ("ETF", "Vanguard FTSE All-World", "VWCE", "Azionario"),
    ("ETF", "iShares Core Global Aggregate Bond", "AGGH", "Obbligazionario"),
    ("ETF", "Xtrackers II EUR Overnight Rate Swap", "XEON", "Monetario e liquidità"),
    ("ETF", "Invesco Physical Gold ETC", "SGLD", "Oro e metalli preziosi"),
    ("ETF", "iShares Diversified Commodity Swap", None, "Materie prime"),
    ("ETF", "iShares Developed Markets Property Yield", None, "Immobiliare"),
    ("Fondo", "Vanguard LifeStrategy 60% Equity", None, "Bilanciato"),
    ("Fondo", "Fondo azionario Europa", None, "Azionario"),
    ("Azione", "Enel", "ENEL.MI", "Azionario"),
    ("Obbligazione", "BTP Italia 2030", None, "Obbligazionario"),
    ("Criptovaluta", "Bitcoin", "BTC", "Criptovalute"),
    ("Conto Risparmio", "Conto deposito", None, "Monetario e liquidità"),
    ("Immobile", "Casa al mare", None, "Immobiliare"),
    ("Fondo Pensione", "Fondo negoziale", None, "Bilanciato"),
    ("Oggetti di valore", "Lingotto d'oro 100 g", None, "Oro e metalli preziosi"),
    ("Oggetti di valore", "Quadro", None, "Altro"),
    ("Veicolo", "Auto", None, "Altro"),
])
def test_the_class_is_estimated_from_the_instrument_and_the_name(instrument, name, ticker, expected):
    assert asset_classes.estimate(instrument, name, ticker) == expected


def test_the_users_choice_wins_over_the_estimate(app, db):
    etf = Holding(name="ETF tematico", asset_class="ETF", quantity=1, avg_price=1)
    assert (asset_classes.of(etf), asset_classes.is_estimated(etf)) == ("Azionario", True)
    etf.allocation_class = "Materie prime"
    assert (asset_classes.of(etf), asset_classes.is_estimated(etf)) == ("Materie prime", False)


def test_form_saves_the_class_and_the_page_shows_both_charts(client, db):
    form = client.get("/portfolio/new").text
    assert "Tipo di strumento" in form and "Classe di attivo" in form and "stimata dal nome" in form
    client.post("/portfolio/new", data={"name": "Invesco Physical Gold", "asset_class": "ETF", "allocation_class": "",
                                        "quantity": "10", "avg_price": "200", "price_source": "auto"})
    client.post("/portfolio/new", data={"name": "ETF Mondo", "asset_class": "ETF", "allocation_class": "Bilanciato",
                                        "quantity": "10", "avg_price": "100", "price_source": "auto"})
    gold, world = Holding.query.order_by(Holding.id).all()
    assert (gold.allocation_class, world.allocation_class) == (None, "Bilanciato")
    assert "stimata: Oro e metalli preziosi" in client.get(f"/portfolio/{gold.id}/edit").text
    summary = wealth.portfolio_summary([gold, world])
    assert dict(summary["classes"]) == {"Oro e metalli preziosi": 2000.0, "Bilanciato": 1000.0}
    assert dict(summary["allocation"]) == {"ETF": 3000.0}
    page = client.get("/portfolio/").text
    assert "assetClassChart" in page and "allocationChart" in page and "Per tipo di strumento" in page
    assert Decimal(gold.quantity) == 10
