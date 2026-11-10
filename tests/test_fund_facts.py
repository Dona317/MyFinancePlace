"""A fund's characteristics, all editable (issuer, domicile, TER, distribution, replication, index, launch date,
currency hedging), and the chart of the positions by domicile (sede)."""
from datetime import date
from decimal import Decimal

from app.models.wealth import Holding
from app.services import fund_facts, wealth


def test_the_domicile_comes_from_the_isin_unless_set(app):
    with app.test_request_context():
        etf = Holding(name="World", asset_class="ETF", isin="IE00B4L5Y983", quantity=1, avg_price=1)
        assert (fund_facts.domicile_code(etf), fund_facts.domicile_name(etf)) == ("IE", "Irlanda")
        etf.domicile = "LU"
        assert fund_facts.domicile_name(etf) == "Lussemburgo"
        assert fund_facts.domicile_name(Holding(name="Casa", asset_class="Immobile", quantity=1, avg_price=1)) == "Non indicata"
        assert fund_facts.country_name("XS").startswith("Internazionale")


def test_every_characteristic_is_editable_and_shown(client, db):
    form = {"name": "iShares Core MSCI World", "asset_class": "ETF", "quantity": "10", "avg_price": "80",
            "price_source": "auto", "isin": "IE00B4L5Y983", "issuer": "iShares", "domicile": "ie", "ter": "0,20",
            "distribution": "acc", "replication": "sampling", "index_name": "MSCI World", "launch_date": "2009-09-25",
            "currency_hedged": "on"}
    assert client.post("/portfolio/new", data=form).status_code == 302
    etf = Holding.query.one()
    assert (etf.issuer, etf.domicile, etf.ter, etf.distribution, etf.replication, etf.index_name) == (
        "iShares", "IE", Decimal("0.200"), "acc", "sampling", "MSCI World")
    assert etf.launch_date == date(2009, 9, 25) and etf.currency_hedged is True
    page = client.get(f"/portfolio/{etf.id}").text
    assert "Caratteristiche" in page and "Irlanda" in page and "Fisica a campione" in page and "0,2 %" in page
    edit = client.get(f"/portfolio/{etf.id}/edit").text
    assert 'value="iShares"' in edit and "Caratteristiche del fondo" in edit
    bad = client.post(f"/portfolio/{etf.id}/edit", data=form | {"domicile": "Irlanda"})
    assert "due lettere" in bad.text and Holding.query.one().domicile == "IE"
    assert "TER: una percentuale" in client.post(f"/portfolio/{etf.id}/edit", data=form | {"ter": "15"}).text
    client.post(f"/portfolio/{etf.id}/edit", data=form | {"distribution": "", "currency_hedged": ""})
    assert (etf.distribution, etf.currency_hedged) == (None, False)


def test_positions_by_domicile(client, db):
    db.session.add_all([Holding(name="A", asset_class="ETF", isin="IE00B4L5Y983", quantity=10, avg_price=100),
                        Holding(name="B", asset_class="ETF", isin="LU0274208692", quantity=5, avg_price=100),
                        Holding(name="C", asset_class="ETF", isin="IE00BK5BQT80", quantity=1, avg_price=100)])
    db.session.commit()
    with client.application.test_request_context():
        summary = wealth.portfolio_summary(Holding.query.all())
    assert summary["domiciles"] == [("Irlanda", 1100.0), ("Lussemburgo", 500.0)]
    assert "domicileChart" in client.get("/portfolio/").text
