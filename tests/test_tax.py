"""F15: the Fisco pages — 730 deductions, capital gains and losses, stamp duty and IVAFE — with figures worked out
by hand."""
import json
from datetime import date
from decimal import Decimal

import pytest

from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction, TransactionSplit
from app.models.wealth import Holding
from app.services import accounts, capital_gains, settings_store, stamp_duty, tax_730, tax_rules
from tests.conftest import make_tx

D = Decimal


# ── Rules ──────────────────────────────────────────────────────────────────────

def test_rules_by_year():
    assert tax_rules.item(2024, "istruzione").ceiling == D(800)
    assert tax_rules.item(2025, "istruzione").ceiling == D(1000) and tax_rules.item(2030, "istruzione").ceiling == D(1000)
    assert tax_rules.item(2025, "sanitarie").threshold == D("129.11") and tax_rules.item(2025, "nope") is None
    assert tax_rules.gain_rate("Criptovaluta", 2025) == 26 and tax_rules.gain_rate("Criptovaluta", 2026) == 33
    assert tax_rules.gain_rate("Azione", 2026) == 26 and tax_rules.gain_rate("Obbligazione", 2026, D("12.5")) == D("12.5")
    assert tax_rules.irpef_rates(2026)[1] == 33 and tax_rules.irpef_rates(2040) == tax_rules.irpef_rates(2026)


# ── 730 ────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def expenses(db):
    cash = Account(name="Contanti", kind="cash")
    bank = Account(name="Banca", kind="current")
    db.session.add_all([cash, bank, Category(name="Salute", kind="expense"),
                        Category(name="Farmacia", kind="expense")])
    db.session.flush()
    farmacia = Category.query.filter_by(name="Farmacia").one()
    farmacia.parent_id = Category.query.filter_by(name="Salute").one().id
    split = make_tx(date=date(2025, 5, 2), description="Spesa e farmaci", amount=-100, category="Alimentari")
    split.splits = [TransactionSplit(category="Alimentari", amount=70), TransactionSplit(category="Farmacia", amount=30)]
    db.session.add_all([
        make_tx(date=date(2025, 2, 1), description="Dentista", amount=-300, category="Salute", account_id=bank.id),
        make_tx(date=date(2025, 3, 1), description="Farmaci", amount=-20, category="Farmacia", account_id=cash.id),
        split,
        make_tx(date=date(2025, 4, 1), description="Retta scuola", amount=-1500, category="Istruzione"),
        make_tx(date=date(2025, 6, 1), description="Fondo pensione", amount=-6000, category="Previdenza"),
        make_tx(date=date(2025, 7, 1), description="Erboristeria", amount=-40, category="Altro", tags=["detraibile"]),
        make_tx(date=date(2024, 7, 1), description="Visita 2024", amount=-500, category="Salute"),
        make_tx(date=date(2025, 8, 1), description="Rimborso", amount=50, type="income", category="Salute"),
    ])
    db.session.commit()


def test_730_default_lines(app, expenses):
    with app.test_request_context():
        data = tax_730.summary(2025)
    lines = {line.item.code: line for line in data["lines"]}
    health = lines["sanitarie"]
    assert health.paid == D(350)  # 300 + 20 (subcategory) + 30 (its part of a split), not 2024, not income
    assert health.counted == D("220.89") and health.benefit == D("41.97")  # (350 − 129,11) × 19%
    assert health.in_cash == 1 and len(health.entries) == 3
    school = lines["istruzione"]
    assert school.counted == D(1000) and school.benefit == D(190)  # ceiling per student from 2025
    assert data["detrazioni"] == D("231.97") and data["deduzioni"] == 0
    assert [tx.description for tx in data["unassigned"]] == ["Erboristeria"]
    with app.test_request_context():
        assert tax_730.summary(2024)["lines"][0].paid == D(500)


def test_730_mapping_people_and_deductions(app, client, expenses):
    r = client.post("/tax/730/categories?year=2025", data={
        "cat-sanitarie": ["Salute", "Inesistente"], "cat-istruzione": ["Istruzione"], "people-istruzione": "2",
        "cat-previdenza": ["Previdenza"], "cat-donazioni": ["Altro"], "people-sport": "99"}, follow_redirects=True)
    assert "Categorie del 730 salvate" in r.get_data(as_text=True)
    assert tax_730.mapping()["sanitarie"] == ["Salute"] and tax_730.people() == {"istruzione": 2}
    with app.test_request_context():
        data = tax_730.summary(2025)
    lines = {line.item.code: line for line in data["lines"]}
    assert lines["istruzione"].counted == D(1500)  # two students: up to 2.000
    assert lines["previdenza"].benefit == D("5164.57") and data["deduzioni"] == D("5164.57")
    assert lines["donazioni"].benefit == D(12)  # 30% of 40, no longer unassigned
    assert data["unassigned"] == []


def test_730_broken_settings_fall_back(app, db):
    settings_store.set(tax_730.MAP_SETTING, "{not json")
    settings_store.set(tax_730.MAP_SETTING + ".people", "[1]")
    assert tax_730.mapping() == tax_730.DEFAULT_MAP
    assert tax_730.people() == {}
    settings_store.set(tax_730.MAP_SETTING + ".people", "{bad")
    assert tax_730.people() == {}
    settings_store.set(tax_730.MAP_SETTING, json.dumps({"sanitarie": ["Salute", 3], "x": "no"}))
    assert tax_730.mapping() == {"sanitarie": ["Salute"]}


def test_730_pages_and_csv(client, expenses):
    page = client.get("/tax/730?year=2025").get_data(as_text=True)
    assert "Spese sanitarie" in page and "Erboristeria" in page and 'id="tax-map"' in page
    assert client.get("/tax/").status_code == 302
    csv = client.get("/tax/730.csv?year=2025").get_data(as_text=True)
    assert "E1;Spese sanitarie;2025-02-01;Dentista" in csv and "Retta scuola" in csv
    assert client.get("/tax/730?year=abc").status_code == 200


# ── Capital gains ──────────────────────────────────────────────────────────────

def _trade(db, holding, on, units, price, fee=0, account=None):
    tx = make_tx(date=on, description=f"{'Acquisto' if units > 0 else 'Vendita'} {holding.name}", type="transfer",
                 category="Investimenti", amount=abs(units * price), holding_id=holding.id, units=D(str(units)),
                 unit_price=D(str(price)), account_id=account.id if account and units > 0 else None,
                 counter_account_id=account.id if account and units < 0 else None)
    db.session.add(tx)
    db.session.flush()
    if fee:
        db.session.add(make_tx(date=on, description="Commissione", amount=-fee, category="Commissioni", fee_for_id=tx.id))
    return tx


@pytest.fixture()
def broker(db):
    account = Account(name="Broker", kind="other")
    db.session.add(account)
    db.session.flush()
    return account


def _holding(db, name, asset_class, quantity=0, avg=0, **extra):
    holding = Holding(name=name, asset_class=asset_class, quantity=quantity, avg_price=avg, **extra)
    db.session.add(holding)
    db.session.flush()
    return holding


def test_sale_with_average_cost_and_fees(app, db, broker):
    enel = _holding(db, "Enel", "Azione", quantity=15)
    _trade(db, enel, date(2025, 1, 10), 10, 100, fee=5, account=broker)
    _trade(db, enel, date(2025, 3, 10), 10, 120, account=broker)
    _trade(db, enel, date(2025, 6, 10), -5, 150, fee=5, account=broker)
    db.session.commit()
    data = capital_gains.year_summary(2025)
    sale = data["sales"][0]
    assert sale.cost == D("551.25") and sale.proceeds == D(745)  # avg (1000+5+1200)/20 = 110,25; 750 − 5
    assert sale.result == D("193.75") and sale.tax == D("50.38") and sale.kind == "diversi"
    box = data["boxes"][0]
    assert box["box"].label == "Broker" and box["gains"] == D("193.75") and data["tax"] == D("50.38")
    assert capital_gains.years() == [2025]


def test_losses_offset_later_gains_but_not_funds(app, db, broker):
    enel = _holding(db, "Enel", "Azione")
    etf = _holding(db, "ETF World", "ETF")
    _trade(db, enel, date(2024, 1, 1), 10, 100, account=broker)
    _trade(db, enel, date(2024, 6, 1), -5, 60, account=broker)      # loss 200 in 2024
    _trade(db, etf, date(2024, 1, 1), 10, 100, account=broker)
    _trade(db, etf, date(2025, 2, 1), -5, 140, account=broker)      # ETF gain 200: redditi di capitale, taxed in full
    _trade(db, enel, date(2025, 3, 1), -5, 150, account=broker)     # gain 250, offset by the 200 loss
    db.session.commit()
    y2024 = capital_gains.year_summary(2024)
    assert y2024["boxes"][0]["losses"] == D(200) and y2024["boxes"][0]["carried"][0].left == D(200)
    data = capital_gains.year_summary(2025)
    etf_sale, enel_sale = data["sales"]
    assert etf_sale.offset == 0 and etf_sale.tax == D(52)
    assert enel_sale.offset == D(200) and enel_sale.taxable == D(50) and enel_sale.tax == D(13)
    assert data["boxes"][0]["carried"] == [] and data["tax"] == D(65)


def test_government_bonds_crypto_regimes_and_expiry(app, db, broker):
    home = Account(name="Banca dichiarativa", kind="other", tax_regime="dichiarativo")
    db.session.add(home)
    btp = _holding(db, "BTP", "Obbligazione", tax_rate=D("12.5"))
    shares = _holding(db, "Azioni", "Azione")
    coin = _holding(db, "Bitcoin", "Criptovaluta")
    _trade(db, shares, date(2020, 1, 1), 10, 100, account=broker)
    _trade(db, shares, date(2020, 6, 1), -10, 90, account=broker)    # loss 100 in 2020: usable until 2024
    _trade(db, btp, date(2024, 1, 1), 10, 100, account=broker)
    _trade(db, btp, date(2025, 1, 1), -10, 120, account=broker)     # gain 200 at 12,5%: the 2020 loss expired
    _trade(db, shares, date(2025, 1, 1), 10, 100, account=broker)
    _trade(db, shares, date(2025, 2, 1), -10, 90, account=broker)   # loss 100 in 2025
    _trade(db, btp, date(2025, 3, 1), 10, 100, account=broker)
    _trade(db, btp, date(2025, 4, 1), -10, 130, account=broker)     # gain 300; the 100 loss offsets 100 / 0,4808
    _trade(db, coin, date(2025, 1, 1), 1, 1000, account=home)
    _trade(db, coin, date(2026, 1, 1), -1, 1500, account=home)      # crypto gain 500 at 33%, dichiarativo
    db.session.commit()
    data = capital_gains.year_summary(2025)
    first, loss, second = data["sales"]
    assert first.offset == 0 and first.tax == D(25)
    assert second.offset == (D(100) / D("0.4808")) and second.tax == ((D(300) - D(100) / D("0.4808")) * D("12.5") / 100).quantize(D("0.01"))
    later = capital_gains.year_summary(2026)
    crypto = later["sales"][0]
    assert crypto.rate == 33 and crypto.tax == D(165) and crypto.kind == "cripto"
    assert later["boxes"][0]["box"].regime == "dichiarativo"


def test_crypto_losses_only_for_crypto_and_estimates(app, db, broker):
    coin = _holding(db, "ETH", "Criptovaluta")
    shares = _holding(db, "Azioni", "Azione", quantity=5, avg=50)   # 5 left: 15 held before the recorded trades
    late = _holding(db, "Late", "Azione")
    _trade(db, coin, date(2025, 1, 1), 1, 1000, account=broker)
    _trade(db, coin, date(2025, 2, 1), -1, 400, account=broker)     # crypto loss 600
    _trade(db, shares, date(2025, 3, 1), -10, 80, account=broker)   # 10 units at 50 → gain 300, not offset
    _trade(db, late, date(2025, 4, 1), -1, 80, account=broker)      # sold before its purchase was recorded
    _trade(db, late, date(2025, 5, 1), 1, 70, account=broker)
    db.session.commit()
    data = capital_gains.year_summary(2025)
    gain = data["sales"][1]
    assert gain.offset == 0 and gain.result == D(300) and gain.estimated
    assert data["estimated"] and len(data["oversold"]) == 1


def test_investment_pages(client, db, broker):
    enel = _holding(db, "Enel", "Azione")
    home = Account(name="Dich", kind="other", tax_regime="dichiarativo")
    db.session.add(home)
    db.session.flush()
    _trade(db, enel, date(2025, 1, 10), 10, 100, account=home)
    _trade(db, enel, date(2025, 6, 10), -10, 90, account=home)
    db.session.commit()
    page = client.get("/tax/investments?year=2025").get_data(as_text=True)
    assert "Quadro RT" in page and "Minusvalenze ancora utilizzabili" in page and "Enel" in page
    assert "Nessuna vendita registrata" in client.get("/tax/investments?year=2019").get_data(as_text=True)


# ── Stamp duty and IVAFE ───────────────────────────────────────────────────────

def test_average_balance_and_account_duties(app, db):
    rich = Account(name="Ricco", kind="current", opening_balance=4000)
    poor = Account(name="Povero", kind="current", opening_balance=100)
    abroad = Account(name="Revolut", kind="current", opening_balance=9000, abroad=True)
    deposit = Account(name="Deposito", kind="savings", opening_balance=10000)
    db.session.add_all([rich, poor, abroad, deposit, Account(name="Carta", kind="card")])
    db.session.flush()
    db.session.add_all([
        make_tx(date=date(2025, 7, 2), description="Bonus", amount=4000, type="income", account_id=rich.id),
        make_tx(date=date(2025, 1, 1), description="Giro", amount=500, type="transfer", account_id=rich.id,
                counter_account_id=deposit.id),
        make_tx(date=date(2025, 3, 1), description="Se stesso", amount=1, type="transfer", account_id=poor.id,
                counter_account_id=poor.id),
    ])
    db.session.commit()
    average = accounts.average_balance(rich, date(2025, 1, 1), date(2025, 12, 31))
    assert average == pytest.approx(3500 + 4000 * 183 / 365, abs=0.01)  # 3.500 all year, +4.000 from 2 July
    assert accounts.average_balance(rich, date(2025, 2, 1), date(2025, 1, 1)) == 0.0
    assert accounts.average_balance(poor, date(2025, 1, 1), date(2025, 12, 31)) == 100
    duties = {d.name: d for d in stamp_duty.account_duties(2025, today=date(2026, 3, 1))}
    assert duties["Ricco"].amount == D("34.20") and duties["Povero"].amount == 0
    assert duties["Revolut"].tax == stamp_duty.IVAFE and duties["Revolut"].amount == D("34.20")
    assert duties["Deposito"].amount == D("21.00") and "Carta" not in duties  # 0,2% of 10.500


def test_holding_duties_and_page(app, client, db):
    db.session.add_all([
        Holding(name="ETF", asset_class="ETF", quantity=10, avg_price=100, current_price=150),
        Holding(name="ETF estero", asset_class="ETF", quantity=10, avg_price=100, abroad=True),
        Holding(name="Wallet", asset_class="Criptovaluta", quantity=1, avg_price=2000, abroad=True),
        Holding(name="Casa", asset_class="Immobile", quantity=1, avg_price=200000),
    ])
    db.session.commit()
    today = date.today()
    data = stamp_duty.year_summary(today.year, today=today)
    duties = {d.name: d for d in data["duties"]}
    assert duties["ETF"].amount == D(3) and duties["ETF"].tax == stamp_duty.BOLLO
    assert duties["ETF estero"].tax == stamp_duty.IVAFE and duties["Wallet"].tax == stamp_duty.IC
    assert "Casa" not in duties and data["total"] == D(9) and data["partial"]
    page = client.get(f"/tax/duties?year={today.year}").get_data(as_text=True)
    assert "IVAFE" in page and "Wallet" in page


# ── Forms and module switch ────────────────────────────────────────────────────

def test_account_and_holding_tax_fields(client, db):
    client.post("/accounts/new", data={"name": "Directa", "kind": "other", "currency": "EUR", "opening_balance": "0",
                                       "tax_regime": "dichiarativo", "abroad": "on"})
    account = Account.query.filter_by(name="Directa").one()
    assert account.tax_regime == "dichiarativo" and account.abroad
    client.post(f"/accounts/{account.id}/edit", data={"name": "Directa", "kind": "other", "currency": "EUR",
                                                      "opening_balance": "0", "active": "on"})
    assert account.tax_regime == "amministrato" and not account.abroad
    r = client.post("/portfolio/new", data={"name": "BTP", "asset_class": "Obbligazione", "quantity": "1",
                                            "avg_price": "100", "tax_rate": "150"})
    assert "tra 0 e 100" in r.get_data(as_text=True)
    client.post("/portfolio/new", data={"name": "BTP", "asset_class": "Obbligazione", "quantity": "1",
                                        "avg_price": "100", "tax_rate": "12,5", "abroad": "on"})
    btp = Holding.query.filter_by(name="BTP").one()
    assert btp.tax_rate == D("12.5") and btp.abroad


def test_module_can_be_switched_off(client, db):
    assert 'href="/tax/"' in client.get("/dashboard").get_data(as_text=True)
    client.post("/settings/save", data={})
    assert client.get("/tax/730").status_code == 404
    assert Transaction.query.count() == 0
