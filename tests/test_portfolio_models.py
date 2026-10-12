"""
F19d: model portfolios — ready models to copy, own templates whose targets add up to 100 %, the holdings placed in
their slots, and the rebalancing with new money only or in full.
"""
from decimal import Decimal

import pytest

from app.models.portfolio_model import PortfolioTemplate, SlotHolding, TemplateSlot
from app.models.wealth import Holding
from app.services import backup, portfolio_models
from app.services.portfolio_models import SlotInput, TemplateError


def _holding(name, value, **fields):
    return Holding(name=name, quantity=Decimal(value) / 10, avg_price=10, current_price=10,
                   asset_class=fields.pop("asset_class", "ETF"), **fields)


@pytest.fixture()
def book(db):
    world = _holding("All-World", 7000, isin="IE00BK5BQT80", ticker="VWCE.DE")
    bonds = _holding("Global Agg", 2000, ticker="AGGH.MI")
    enel = _holding("Enel", 1000, asset_class="Azione")
    house = _holding("Casa", 300000, asset_class="Immobile")  # not an investment: never counted
    db.session.add_all([world, bonds, enel, house])
    db.session.commit()
    return world, bonds, enel


def test_ready_models_add_up_to_100():
    for name, description, slots in portfolio_models.READY.values():
        assert sum(Decimal(target) for _label, target, _instrument in slots) == 100, name
        assert all(len(isin) == 12 and ticker.endswith(".MI") for _l, _t, (isin, ticker) in slots)


def test_copy_rebalance_new_money(app, db, book):
    world, bonds, enel = book
    with app.test_request_context():
        template = portfolio_models.copy_ready("60-40")
        db.session.commit()
        assert template.active and [s.target for s in template.slots] == [60, 40]
        plan = portfolio_models.rebalance(template, "new", Decimal(1000))
    stocks, agg, outside = plan.lines
    assert (stocks.holdings, agg.holdings, outside.holdings) == ([world], [bonds], [enel])  # by ISIN, by ticker
    assert plan.total == Decimal(10000) and outside.outside
    assert (stocks.weight, agg.weight, outside.weight) == (Decimal(70), Decimal(20), Decimal(10))
    assert [line.label for line in plan.out_of_band] == ["Azioni globali", "Obbligazioni globali", "Fuori dal modello"]
    # after 1.000 € the bonds should be 4.400 €: they lack 2.400, more than the money, so it all goes there
    assert (stocks.move, agg.move, outside.move) == (Decimal(0), Decimal(1000), Decimal(0))
    assert agg.units == Decimal(100) and agg.via == bonds and plan.leftover == 0


def test_new_money_beyond_the_gaps_follows_the_targets(app, db, book):
    world, bonds, enel = book
    with app.test_request_context():
        template = portfolio_models.copy_ready("80-20")
        plan = portfolio_models.rebalance(template, "new", Decimal(10000), holdings=[world, bonds])
    stocks, agg = plan.lines
    # total after = 19.000: stocks lack 15.200 − 7.000 = 8.200, bonds 3.800 − 2.000 = 1.800; nothing spare
    assert (stocks.move, agg.move) == (Decimal(8200), Decimal(1800))
    plan = portfolio_models.rebalance(template, "new", Decimal(20000), holdings=[world, bonds])
    # total after = 29.000: gaps 16.200 and 3.800 = 20.000 exactly
    assert sum(line.move for line in plan.lines) == Decimal(20000)
    plan = portfolio_models.rebalance(template, "new", Decimal(0), holdings=[])
    assert all(line.move == 0 and line.units is None for line in plan.lines)
    assert plan.lines[0].suggestion == "VWCE.MI"


def test_full_rebalance_sells_too(app, db, book):
    world, bonds, enel = book
    with app.test_request_context():
        template = portfolio_models.copy_ready("60-40")
        plan = portfolio_models.rebalance(template, "full")
    stocks, agg, outside = plan.lines
    assert (stocks.move, agg.move, outside.move) == (Decimal(-1000), Decimal(2000), Decimal(-1000))
    assert stocks.units == Decimal(-100) and plan.mode == "full"


def test_slots_by_hand_and_by_class(app, db, book):
    world, bonds, enel = book
    template = PortfolioTemplate(name="Mio", band=10)
    db.session.add(template)
    portfolio_models.save(template, "Mio", "", Decimal(10), [
        SlotInput("Italia", Decimal(20), holding_ids=[world.id]),
        SlotInput("Azioni", Decimal(50), asset_class="Azione"),
        SlotInput("ETF", Decimal(30), asset_class="ETF")])
    db.session.commit()
    with app.test_request_context():
        lines, total = portfolio_models.standing(template)
    assert [(line.label, [h.name for h in line.holdings]) for line in lines] == [
        ("Italia", ["All-World"]), ("Azioni", ["Enel"]), ("ETF", ["Global Agg"])]
    assert total == Decimal(10000)


@pytest.mark.parametrize("slots, band, message", [
    ([], None, "Aggiungi almeno una parte"),
    ([SlotInput("A", Decimal(60)), SlotInput("B", Decimal(30))], None, "Gli obiettivi sommano 90 %"),
    ([SlotInput("A", Decimal(0)), SlotInput("B", Decimal(100))], None, "tra 0 e 100"),
    ([SlotInput("A", Decimal(100))], Decimal(60), "La tolleranza"),
])
def test_save_refuses(app, db, slots, band, message):
    template = PortfolioTemplate(name="x")
    with app.test_request_context(), pytest.raises(TemplateError, match=message):
        portfolio_models.save(template, "x", None, band, slots)
    with app.test_request_context(), pytest.raises(TemplateError, match="Dai un nome"):
        portfolio_models.save(template, " ", None, None, [SlotInput("A", Decimal(100))])


def test_pages(client, db, book):
    world, bonds, enel = book
    page = client.get("/portfolio/rebalance", follow_redirects=True).get_data(as_text=True)
    assert "Scegli o crea prima un portafoglio modello" in page and "Permanent Portfolio" in page
    page = client.post("/portfolio/models/ready/60-40", follow_redirects=True).get_data(as_text=True)
    assert "«60/40» copiato" in page and 'value="IE00BK5BQT80"' in page
    template = PortfolioTemplate.query.one()

    page = client.get("/portfolio/rebalance?mode=new&amount=1000,00").get_data(as_text=True)
    assert "Compra € 1.000,00" in page and "100 quote" in page and "Fuori dal modello" in page
    page = client.get("/portfolio/rebalance?mode=full").get_data(as_text=True)
    assert "Vendi € 1.000,00" in page and "Compra € 2.000,00" in page

    form = {"rows": "3", "name": "Mio 70/30", "band": "3", "description": "prova",
            "label-0": "Azioni", "target-0": "70", "class-0": "Azione", "holdings-0": [str(world.id)],
            "label-1": "Bond", "target-1": "30", "ticker-1": "aggh.mi", "label-2": "", "target-2": ""}
    page = client.post(f"/portfolio/models/{template.id}", data=form, follow_redirects=True).get_data(as_text=True)
    assert "Portafoglio modello salvato." in page and "Ribilanciamento" in page
    db.session.refresh(template)
    assert [(s.label, s.target, s.ticker, s.holding_ids) for s in template.slots] == [
        ("Azioni", Decimal(70), None, {world.id}), ("Bond", Decimal(30), "AGGH.MI", set())]

    form.update({"target-1": "20"})
    page = client.post(f"/portfolio/models/{template.id}", data=form).get_data(as_text=True)
    assert "Gli obiettivi sommano 90 %: devono fare 100 %." in page and 'value="Mio 70/30"' in page
    form.update({"target-1": "", "label-1": "Bond"})
    page = client.post(f"/portfolio/models/{template.id}", data=form).get_data(as_text=True)
    assert "Ogni parte ha bisogno di un nome e di un obiettivo" in page

    new = {"rows": "1", "name": "Tutto", "band": "", "label-0": "Tutto", "target-0": "100"}
    page = client.post("/portfolio/models/new", data=new, follow_redirects=True).get_data(as_text=True)
    assert "Portafoglio modello salvato." in page and "I tuoi modelli" in page  # not active: back to the list
    other = PortfolioTemplate.query.filter_by(name="Tutto").one()
    assert not other.active and other.band == 5
    assert "Gli obiettivi" in client.post("/portfolio/models/new", data={**new, "target-0": "50"}).get_data(as_text=True)
    assert PortfolioTemplate.query.count() == 2

    client.post(f"/portfolio/models/{other.id}/activate")
    db.session.refresh(template)
    db.session.refresh(other)
    assert other.active and not template.active
    assert "Tutto" in client.get("/portfolio/models").get_data(as_text=True)
    assert "Nuovo portafoglio modello" in client.get("/portfolio/models/new").get_data(as_text=True)
    client.post(f"/portfolio/models/{other.id}/delete")
    assert PortfolioTemplate.query.count() == 1 and TemplateSlot.query.count() == 2


def test_unknown_ready_model(client, db):
    page = client.post("/portfolio/models/ready/nope", follow_redirects=True).get_data(as_text=True)
    assert "Modello pronto sconosciuto." in page and "Nessun modello" in page


def test_backup_keeps_the_templates(app, db, book):
    world = book[0]
    with app.test_request_context():
        template = portfolio_models.copy_ready("permanent")
        template.slots[0].links.append(SlotHolding(holding_id=world.id))
        db.session.commit()
        data = backup.export_data()
        backup.restore(data, {})
    restored = PortfolioTemplate.query.one()
    assert [s.target for s in restored.slots] == [25, 25, 25, 25] and restored.slots[0].holding_ids == {world.id}
