"""
Live: the fictitious investments (samples/dati_fittizi/investimenti). The backup is restored from the Export page;
then every page of the Portfolio section must open without errors, the rebalancing must show the equities above
their band and propose orders, and the statements of the two securities accounts must import only this month's
trades — the history already in the backup is recognized («Già importato») and importing it twice adds nothing.
Screenshots of the pages go to LIVE_OUT/shots (inv_*.png). Run it last: the restore replaces the data.
"""

import re
import sys

from common import AUTH, OUT, ROOT, check, confirm, launch, local_assets, run, sql, summary
from common import BASE as B
from playwright.sync_api import sync_playwright

DATA = ROOT / "samples" / "dati_fittizi" / "investimenti"
STATEMENTS = DATA / "conti_titoli"
SHOTS = OUT / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    b = launch(p)
    ctx = b.new_context(viewport={"width": 1400, "height": 900}, storage_state=AUTH)
    pg = ctx.new_page()
    local_assets(pg)
    errors = []
    pg.on("pageerror", lambda e: errors.append(f"{pg.url}: {e}"))

    def shot(name):
        pg.screenshot(path=str(SHOTS / f"inv_{name}.png"), full_page=True)

    def restore():
        pg.goto(B + "/export/")
        pg.set_input_files("form[action$='/export/restore'] input[type=file]", str(DATA / "backup_investimenti.zip"))
        pg.check("form[action$='/export/restore'] input[name=confirm]")
        pg.click("form[action$='/export/restore'] button[type=submit]")
        confirm(pg)
        check("backup restored", "Backup ripristinato" in pg.content(), pg.url)
        check("25 holdings", sql("SELECT count(*) FROM holdings") == "25", sql("SELECT count(*) FROM holdings"))
        check("2 securities accounts and the pension container", sql("SELECT count(*) FROM securities_accounts") == "3")
        check("2 portfolios, «Crescita» starred", sql("SELECT string_agg(name || is_default::text, ',' ORDER BY name) FROM portfolios") == "Crescitatrue,Redditofalse")
        check("2 active models", sql("SELECT count(*) FROM portfolio_templates WHERE active") == "2")
        check("every trade has its fingerprint",
              sql("SELECT count(*) FROM transactions t JOIN securities_accounts s ON s.id = t.securities_account_id "
                  "WHERE t.units IS NOT NULL AND t.import_ref IS NULL AND s.broker IN ('Fineco', 'Directa')") == "0")

    def pages():
        folio = sql("SELECT id FROM portfolios WHERE name = 'Reddito'")
        dossier = sql("SELECT id FROM securities_accounts WHERE name = 'Conto titoli Directa'")
        vwce = sql("SELECT id FROM holdings WHERE isin = 'IE00BK5BQT80'")
        btp = sql("SELECT id FROM holdings WHERE isin = 'IT0005518128'")
        urls = ["/portfolio/", "/portfolio/overview", "/portfolio/orders", "/portfolio/income", "/portfolio/performance",
                "/portfolio/highlights", "/portfolio/composition", "/portfolio/portfolios", "/portfolio/prices",
                "/portfolio/fees", "/portfolio/models", "/portfolio/rules", "/portfolio/import",
                f"/portfolio/dossiers/{dossier}", f"/portfolio/{vwce}", f"/portfolio/{btp}",
                f"/portfolio/?portfolio={folio}", "/"]
        for url in urls:
            response = pg.goto(B + url)
            pg.wait_for_load_state("networkidle")
            check(f"page {url}", response.status == 200, str(response.status))
            shot(re.sub(r"\W+", "_", url.strip("/")) or "index")

    def rebalance():
        pg.goto(B + "/portfolio/rebalance?mode=full")
        text = pg.inner_text("main")
        check("rebalancing: equities in the model", "Azioni" in text)
        check("rebalancing: out of band shown", re.search(r"fuori|tolleranza|banda", text, re.I) is not None)
        shot("rebalance_full")
        pg.goto(B + "/portfolio/rebalance?amount=5000")
        shot("rebalance_new_money")
        pg.goto(B + "/portfolio/rebalance/orders?mode=full")
        orders = pg.locator("input[name^=do-]").count()
        check("rebalancing: orders proposed", orders >= 2, str(orders))
        shot("rebalance_orders")
        folio = sql("SELECT id FROM portfolios WHERE name = 'Reddito'")
        response = pg.goto(f"{B}/portfolio/rebalance?portfolio={folio}&mode=full")
        check("rebalancing of «Reddito»", response.status == 200 and "Obbligazioni" in pg.inner_text("main"))
        shot("rebalance_reddito")

    def upload(name, account):
        """Upload a statement, pick the broker's account; the preview's rows: (new, already imported)."""
        pg.goto(B + "/portfolio/import")
        pg.set_input_files("#broker-file", str(STATEMENTS / name))
        with pg.expect_navigation():
            pg.click("form[enctype] button[type=submit] >> nth=0")
        if pg.locator("select[name=account_id]").count() == 0:  # the mapping screen: the guess is kept
            with pg.expect_navigation():
                pg.click("main button[type=submit].btn-primary")
        pg.select_option("select[name=account_id]", label=account)
        return pg.locator("input[name=include]").count(), pg.locator("tbody tr.row-off").count()

    def save():
        with pg.expect_navigation():
            pg.click("main button[type=submit].btn-primary >> text=Importa le operazioni scelte")

    def statements():
        trades = int(sql("SELECT count(*) FROM transactions WHERE units IS NOT NULL"))
        new, old = upload("storico_fineco.csv", "Liquidità Fineco")
        check("Fineco history: only this month's 3 trades are new", new == 3, f"{new} new, {old} already there")
        check("Fineco history: the older ones recognized", old > 60, str(old))
        shot("import_fineco_preview")
        save()
        check("Fineco: imported", "3 operazioni importate" in pg.content())
        check("Fineco: the small-cap ETF created", sql("SELECT count(*) FROM holdings WHERE isin = 'IE00BF4RFH31'") == "1")
        check("Fineco: world ETF sold in its dossier",
              sql("SELECT quantity::numeric(10,0) FROM holdings WHERE isin = 'IE00BK5BQT80'") == "294")
        new, old = upload("mese_corrente_fineco.csv", "Liquidità Fineco")
        check("Fineco this month again: nothing new", new == 0 and old == 3, f"{new} new, {old} old")
        new, old = upload("mese_corrente_directa.csv", "Liquidità Directa")
        check("Directa this month: 3 new trades", new == 3, f"{new} new, {old} old")
        save()
        new, old = upload("storico_directa.csv", "Liquidità Directa")
        check("Directa history after this month: nothing new", new == 0 and old == 19, f"{new} new, {old} old")
        check("Directa: dividends and coupons skipped", "righe ignorate" in pg.content())
        shot("import_directa_preview")
        after = int(sql("SELECT count(*) FROM transactions WHERE units IS NOT NULL"))
        check("6 trades added in all", after - trades == 6, f"{trades} → {after}")
        check("Directa: the new BTP in its dossier", sql(
            "SELECT s.name FROM transactions t JOIN holdings h ON h.id = t.holding_id "
            "JOIN securities_accounts s ON s.id = t.securities_account_id WHERE h.isin = 'IT0005634800'")
              == "Conto titoli Directa")
        check("Directa: Microsoft sold", sql("SELECT quantity::numeric(10,0) FROM holdings WHERE isin = 'US5949181045'") == "5")
        pg.goto(B + "/portfolio/")
        shot("index_after_import")

    run("restore the investments backup", restore)
    run("every page of the portfolio", pages)
    run("rebalancing", rebalance)
    run("the statements of the two securities accounts", statements)
    check("no JavaScript errors", not errors, "; ".join(errors[:3]))
    b.close()

sys.exit(summary("investments"))
