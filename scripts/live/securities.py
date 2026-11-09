"""
Live: securities accounts and portfolios (F42). Two broker accounts, one ETF with an opening position, trades
from the holding's page on both brokers; then the database must show one securities account per broker, every
operation (commissions included) in a dossier and in «Portafoglio principale», positions that add up to the holding,
and the holding's own figures (the «Tutti» view) as before F42. Then the interface: portfolios created, renamed and
starred, a purchase placed in a portfolio and a securities account, a sale above the position refused, the
securities account's page with its liquidity, the rebalancing turned into orders confirmed at the executed price.
Screenshots of the pages go to LIVE_OUT/shots.
"""

import sys

from common import AUTH, OUT, check, launch, local_assets, sql, summary
from common import BASE as B
from playwright.sync_api import sync_playwright

SHOTS = OUT / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    b = launch(p)
    ctx = b.new_context(viewport={"width": 1400, "height": 900}, device_scale_factor=2, storage_state=AUTH)
    pg = ctx.new_page()
    local_assets(pg)
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("dialog", lambda d: d.accept())

    def go(selector):
        with pg.expect_navigation():
            pg.click(selector)

    def choose(name, value=None, label=None):
        """Pick an option of a select, or of a combo field (a hidden <select> behind a text box), by value or text."""
        pg.eval_on_selector(f"select[name={name}]", """(el, [value, label]) => {
            const opt = [...el.options].find(o => value !== null ? o.value === value : o.text.trim() === label);
            if (!opt) throw new Error("no option " + (value ?? label));
            el.value = opt.value; el.dispatchEvent(new Event("change", {bubbles: true}));
            const box = el.id.endsWith("-select") ? el.form.querySelector("#" + el.id.slice(0, -7)) : null;
            if (box) box.value = opt.text.trim();  // a combo: the text box shows the choice
        }""", [value, label])

    def shot(name):
        pg.screenshot(path=str(SHOTS / f"f42_{name}.png"), full_page=True)

    # two broker accounts (a run again starts clean)
    sql("DELETE FROM transactions WHERE holding_id IN (SELECT id FROM holdings WHERE name = 'ETF Mondo F42'); "
        "DELETE FROM holdings WHERE name = 'ETF Mondo F42'; "
        "DELETE FROM securities_accounts WHERE name LIKE 'Titoli % F42%'; DELETE FROM accounts WHERE name LIKE '% F42'")
    for name in ("Directa F42", "Degiro F42"):
        pg.goto(B + "/accounts/new")
        pg.fill("[name=name]", name)
        pg.click(".page-form button[type=submit]")
        pg.wait_for_load_state()
    check("broker accounts saved", sql("SELECT count(*) FROM accounts WHERE name LIKE '% F42'") == "2")

    # an ETF already owned: 20 units at 90
    pg.goto(B + "/portfolio/new")
    pg.fill("#f-name", "ETF Mondo F42")
    pg.fill("#f-ticker", "SWDA")
    choose("asset_class", "ETF")
    pg.fill("#f-quantity", "20")
    pg.fill("#f-avg_price", "90")
    pg.fill("#f-current_price", "120")
    pg.fill("#f-purchase_date", "2024-01-02")
    go(".main-content button[type=submit].btn-primary")
    holding = sql("SELECT id FROM holdings WHERE name = 'ETF Mondo F42'")
    check("holding saved", holding.isdigit(), holding)

    # trades on both brokers, from the holding's page
    for kind, day, units, price, account, fee in (("buy", "2025-02-03", "10", "100", "Directa F42", "2"),
                                                  ("buy", "2025-03-03", "5", "110", "Degiro F42", ""),
                                                  ("sell", "2025-06-02", "3", "120", "Directa F42", "")):
        pg.goto(f"{B}/portfolio/{holding}/operation")
        choose("kind", kind)
        pg.fill("[name=on]", day)
        pg.fill("[name=units]", units)
        pg.fill("[name=price]", price)
        choose("account_id", label=account)
        pg.fill("[name=fee]", fee)
        if kind == "buy" and account.startswith("Directa"):
            shot("1_nuova_operazione")
        go("button:has-text('Salva operazione')")
    pg.goto(f"{B}/portfolio/{holding}")
    shot("2_pagina_titolo")
    check("holding page shows the operations", pg.content().count("ETF Mondo F42") >= 3)
    pg.goto(B + "/portfolio/")
    shot("3_portafoglio")

    # the database: dossiers, portfolio, every operation placed
    dossiers = sql("SELECT string_agg(s.name || '>' || a.name, ',' ORDER BY s.name) FROM securities_accounts s "
                   "JOIN accounts a ON a.id = s.settlement_account_id WHERE a.name LIKE '% F42'")
    check("one securities account per broker", dossiers == "Titoli Degiro F42>Degiro F42,Titoli Directa F42>Directa F42",
          dossiers)
    check("default portfolio", sql("SELECT name FROM portfolios WHERE is_default") == "Portafoglio principale")
    unplaced = sql(f"SELECT count(*) FROM transactions t WHERE (t.holding_id = {holding} OR t.fee_for_id IN "
                   f"(SELECT id FROM transactions WHERE holding_id = {holding})) "
                   "AND (t.securities_account_id IS NULL OR t.portfolio_id IS NULL)")
    placed = sql(f"SELECT count(*) FROM transactions t WHERE t.holding_id = {holding} OR t.fee_for_id IN "
                 f"(SELECT id FROM transactions WHERE holding_id = {holding})")
    check("every operation and commission in a dossier and a portfolio", unplaced == "0" and placed == "4",
          f"{placed} operations, {unplaced} without place")
    by_dossier = sql(f"SELECT string_agg(s.name || '=' || q, ',' ORDER BY s.name) FROM (SELECT securities_account_id, "
                     f"sum(units)::int AS q FROM transactions WHERE holding_id = {holding} AND units IS NOT NULL "
                     "GROUP BY 1) x JOIN securities_accounts s ON s.id = x.securities_account_id")
    check("units by dossier", by_dossier == "Titoli Degiro F42=5,Titoli Directa F42=7", by_dossier)
    figures = sql(f"SELECT quantity::numeric(10,2) || '|' || avg_price::numeric(10,4) FROM holdings WHERE id = {holding}")
    # «Tutti» as before F42: (20 × 90 + 10 × 100 + 2 + 5 × 110) / 35 = 95,7714; a sale keeps the average
    check("holding figures unchanged (Tutti)", figures == "32.00|95.7714", figures)

    # step 2: the page of portfolios and securities accounts — create, rename, star
    pg.goto(B + "/portfolio/portfolios")
    pg.fill("form[action$='/portfolios/new'] [name=name]", "Pensione F42")
    pg.fill("form[action$='/portfolios/new'] [name=description]", "Lungo periodo")
    go("form[action$='/portfolios/new'] button[type=submit]")
    pension = sql("SELECT id FROM portfolios WHERE name = 'Pensione F42'")
    pg.fill(f"form[action$='/portfolios/{pension}/rename'] [name=name]", "Pensione")
    go(f"form[action$='/portfolios/{pension}/rename'] button[type=submit]")
    go(f"form[action$='/portfolios/{pension}/default'] button[type=submit]")
    check("portfolio renamed and starred", sql(f"SELECT name || '|' || is_default FROM portfolios WHERE id = {pension}") == "Pensione|true")
    shot("4_portafogli_e_conti_titoli")

    # a purchase for the pension from the form, with its securities account and portfolio
    pg.goto(f"{B}/portfolio/{holding}/operation")
    choose("kind", "buy")
    pg.fill("[name=on]", "2025-07-01")
    pg.fill("[name=units]", "4")
    pg.fill("[name=price]", "115")
    choose("account_id", label="Degiro F42")
    choose("securities_account_id", label="Titoli Degiro F42")
    choose("portfolio_id", label="Pensione")
    shot("5_operazione_con_conto_titoli_e_portafoglio")
    go("button:has-text('Salva operazione')")
    check("purchase placed in the pension", sql(f"SELECT count(*) FROM transactions WHERE holding_id = {holding} "
                                                f"AND portfolio_id = {pension} AND units = 4") == "1")
    # a sale above the position is refused
    pg.goto(f"{B}/portfolio/{holding}/operation")
    choose("kind", "sell")
    pg.fill("[name=on]", "2025-07-02")
    pg.fill("[name=units]", "9")
    pg.fill("[name=price]", "116")
    choose("account_id", label="Degiro F42")
    choose("securities_account_id", label="Titoli Degiro F42")
    choose("portfolio_id", label="Pensione")
    go("button:has-text('Salva operazione')")
    check("sale above the position refused", "hai solo 4 quote" in pg.content())

    # the securities account's page: positions and liquidity
    degiro = sql("SELECT id FROM securities_accounts WHERE name = 'Titoli Degiro F42'")
    pg.goto(f"{B}/portfolio/dossiers/{degiro}")
    check("securities account page with liquidity", "Liquidità" in pg.content())
    shot("6_conto_titoli")
    pg.goto(f"{B}/portfolio/?portfolio={pension}")
    shot("7_posizioni_filtrate_per_portafoglio")

    # rebalancing: a 70/30 model, orders prepared, executed price corrected, confirmed
    pg.goto(B + "/portfolio/new")
    pg.fill("#f-name", "Obbligazioni F42")
    pg.fill("#f-ticker", "AGGH")
    choose("asset_class", "ETF")
    pg.fill("#f-quantity", "0")
    pg.fill("#f-avg_price", "5")
    pg.fill("#f-current_price", "5")
    go(".main-content button[type=submit].btn-primary")
    bonds = sql("SELECT id FROM holdings WHERE name = 'Obbligazioni F42'")
    sql("UPDATE portfolio_templates SET active = false; "
        "INSERT INTO portfolio_templates (name, band, active, created_at) VALUES ('70/30 F42', 5, true, now())")
    model = sql("SELECT id FROM portfolio_templates WHERE name = '70/30 F42'")
    for position, (label, target, holding_id) in enumerate((("Azioni", 70, holding), ("Obbligazioni", 30, bonds))):
        sql(f"INSERT INTO template_slots (template_id, position, label, target) VALUES ({model}, {position}, '{label}', {target})")
        slot = sql(f"SELECT id FROM template_slots WHERE template_id = {model} AND label = '{label}'")
        sql(f"INSERT INTO slot_holdings (slot_id, holding_id) VALUES ({slot}, {holding_id})")
    pg.goto(B + "/portfolio/rebalance?mode=full")
    shot("8_ribilanciamento")
    go("text=Prepara gli ordini")
    check("orders prepared", "Conferma ordini eseguiti" in pg.content())
    pg.fill("[name=price-0]", "119,40")  # the executed price differs a little from the last one
    shot("9_ordini_da_confermare")
    go("button:has-text('Conferma ordini eseguiti')")
    check("orders confirmed as trades", "ordini del ribilanciamento registrati" in pg.content())
    check("executed price kept", sql("SELECT count(*) FROM transactions WHERE notes = 'Ribilanciamento «70/30 F42»' "
                                     "AND unit_price = 119.4") != "0")
    shot("10_dopo_la_conferma")

    check("no JavaScript errors", not errors, "; ".join(errors[:3]))
    b.close()

sys.exit(summary("securities (F42)"))
