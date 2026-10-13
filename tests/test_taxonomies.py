"""F22: classifications of the user's own for the holdings, with percentages."""
from decimal import Decimal

import pytest

from app.models.taxonomy import HoldingCategory, Taxonomy, TaxonomyCategory
from app.models.wealth import Holding
from app.services import taxonomies


@pytest.fixture()
def book(db):
    world = Holding(name="VWCE", asset_class="ETF", quantity=10, avg_price=100, current_price=100)    # 1000
    bond = Holding(name="BTP", asset_class="Obbligazione", quantity=1, avg_price=500, current_price=500)  # 500
    db.session.add_all([world, bond])
    risk = taxonomies.create("Rischio", False, "Basso\n Alto \n\n")
    theme = taxonomies.create("Tema", True, "Clima\nTecnologia")
    db.session.commit()
    return world, bond, risk, theme


def test_assign_and_exposure(db, book):
    world, bond, risk, theme = book
    low, high = risk.categories
    climate, tech = theme.categories
    assert [c.name for c in risk.categories] == ["Basso", "Alto"]
    taxonomies.assign(world, risk, {high.id: Decimal(100)})
    taxonomies.assign(bond, risk, {low.id: Decimal(1)})  # a single choice is the whole value
    taxonomies.assign(world, theme, {climate.id: Decimal(60), tech.id: Decimal(30), 999: Decimal(5)})
    db.session.commit()
    assert taxonomies.exposure(risk, [world, bond]) == [("Alto", 1000.0, 66.7), ("Basso", 500.0, 33.3)]
    assert taxonomies.exposure(theme, [world, bond]) == [("Clima", 600.0, 40.0), ("Non indicato", 600.0, 40.0),
                                                          ("Tecnologia", 300.0, 20.0)]
    assert taxonomies.of_holding(world) == {risk.id: {high.id: 100}, theme.id: {climate.id: 60, tech.id: 30}}
    taxonomies.assign(world, theme, {climate.id: None, tech.id: Decimal(0)})  # emptied: out of the classification
    assert theme.id not in taxonomies.of_holding(world)
    assert taxonomies.exposure(theme, []) == []


def test_rules(db, book):
    world, bond, risk, theme = book
    low, high = risk.categories
    climate, tech = theme.categories
    with pytest.raises(ValueError, match="una sola categoria"):
        taxonomies.assign(world, risk, {low.id: Decimal(50), high.id: Decimal(50)})
    with pytest.raises(ValueError, match="superano 100"):
        taxonomies.assign(world, theme, {climate.id: Decimal(70), tech.id: Decimal(40)})
    with pytest.raises(ValueError, match="da 0 a 100"):
        taxonomies.assign(world, theme, {climate.id: Decimal(-5)})
    with pytest.raises(ValueError, match="già"):
        taxonomies.create("rischio", False)
    with pytest.raises(ValueError, match="nome"):
        taxonomies.create(" ", False)
    with pytest.raises(ValueError, match="c'è già"):
        taxonomies.add_category(risk, "basso")
    with pytest.raises(ValueError, match="c'è già"):
        taxonomies.rename_category(high, "BASSO")
    with pytest.raises(ValueError, match="già"):
        taxonomies.update(theme, "Rischio", True)


def test_back_to_a_single_choice_keeps_the_biggest_share(db, book):
    world, bond, risk, theme = book
    climate, tech = theme.categories
    taxonomies.assign(world, theme, {climate.id: Decimal(30), tech.id: Decimal(70)})
    taxonomies.update(theme, "Tema", False)
    db.session.commit()
    assert taxonomies.of_holding(world)[theme.id] == {tech.id: 100}


def test_pages(client, db, book):
    world, bond, risk, theme = book
    low, high = risk.categories
    climate, tech = theme.categories
    page = client.get(f"/portfolio/{world.id}").get_data(as_text=True)
    assert "Classificazioni" in page and f'name="w-{climate.id}"' in page
    client.post(f"/portfolio/{world.id}/classify", data={f"t-{risk.id}": high.id, f"w-{climate.id}": "60", f"w-{tech.id}": "40"})
    assert HoldingCategory.query.count() == 3
    page = client.post(f"/portfolio/{world.id}/classify", data={f"w-{climate.id}": "90", f"w-{tech.id}": "40"},
                       follow_redirects=True).get_data(as_text=True)
    assert "superano 100" in page and HoldingCategory.query.count() == 3  # nothing changed
    page = client.get("/portfolio/composition").get_data(as_text=True)
    assert "chart-t%d" % risk.id in page and "Tecnologia" in page

    assert "Rischio" in client.get("/settings/taxonomies").get_data(as_text=True)
    client.post("/settings/taxonomies/new", data={"name": "ESG", "categories": "Sì\nNo"})
    esg = Taxonomy.query.filter_by(name="ESG").one()
    assert [c.name for c in esg.categories] == ["Sì", "No"]
    assert "già" in client.post("/settings/taxonomies/new", data={"name": "esg"}, follow_redirects=True).get_data(as_text=True)
    yes, no = esg.categories
    client.post(f"/settings/taxonomies/{esg.id}", data={"name": "ESG ok", "multiple": "on", f"cat-{yes.id}": "Conforme",
                                                        f"cat-{no.id}": "No", f"delete-{no.id}": "on", "new_category": "Forse"})
    db.session.refresh(esg)
    assert esg.name == "ESG ok" and esg.multiple and [c.name for c in esg.categories] == ["Conforme", "Forse"]
    assert "già" in client.post(f"/settings/taxonomies/{esg.id}", data={"name": "ESG ok", "new_category": "forse"},
                                    follow_redirects=True).get_data(as_text=True)
    client.post(f"/settings/taxonomies/{esg.id}/delete")
    assert Taxonomy.query.filter_by(name="ESG ok").first() is None and TaxonomyCategory.query.count() == 4
    db.session.delete(world)
    db.session.commit()
    assert HoldingCategory.query.count() == 0  # the holding's assignments go with it
