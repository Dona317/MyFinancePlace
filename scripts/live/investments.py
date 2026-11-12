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
        check("rebalancing: out of band shown", "1 parti fuori dalla tolleranza" in text, text[:200])
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

    def model_settings():
        """The rebalancing's settings: the band of the model changed from its page, then the rebalancing follows it."""
        model = sql("SELECT id FROM portfolio_templates WHERE name = 'Allocazione per classi'")
        pg.goto(f"{B}/portfolio/models/{model}")
        pg.fill("#band", "12")
        with pg.expect_navigation():
            pg.click("#model-form button[type=submit].btn-primary")
        check("model: band saved", sql(f"SELECT band::int FROM portfolio_templates WHERE id = {model}") == "12")
        pg.goto(B + "/portfolio/rebalance?mode=full")
        check("model: with a band of 12 points nothing is out of band", "Tutte le parti sono entro ± 12" in pg.inner_text("main"))
        shot("rebalance_band_12")
        pg.goto(f"{B}/portfolio/models/{model}")
        pg.fill("#band", "5")
        with pg.expect_navigation():
            pg.click("#model-form button[type=submit].btn-primary")
        check("model: band back to 5", sql(f"SELECT band::int FROM portfolio_templates WHERE id = {model}") == "5")

    def two_portfolios():
        """Two new portfolios from the page; the star moved to one and back to «Crescita» (the old bug: no star)."""
        for name in ("Pensione", "Figli"):
            pg.goto(B + "/portfolio/portfolios")
            pg.fill("form[action$='/portfolios/new'] input[name=name]", name)
            with pg.expect_navigation():
                pg.click("form[action$='/portfolios/new'] button[type=submit]")
        check("two portfolios created", sql("SELECT count(*) FROM portfolios WHERE name IN ('Pensione', 'Figli')") == "2")
        # after a change the page opens where it was being read, not at the top
        pg.set_viewport_size({"width": 1400, "height": 420})
        pg.goto(B + "/portfolio/portfolios")
        pg.locator("form[action$='/portfolios/new']").scroll_into_view_if_needed()
        before = pg.evaluate("window.scrollY")
        pg.fill("form[action$='/portfolios/new'] input[name=name]", "Prova scroll")
        with pg.expect_navigation():
            pg.click("form[action$='/portfolios/new'] button[type=submit]")
        pg.wait_for_load_state("load")
        after = pg.evaluate("window.scrollY")
        check("the page stays where it was after a change", before > 100 and abs(after - before) < 150,
              f"{before} → {after}")
        pg.goto(B + "/portfolio/rules")
        check("another page opens at the top", pg.evaluate("window.scrollY") == 0)
        pg.set_viewport_size({"width": 1400, "height": 900})
        sql("DELETE FROM portfolios WHERE name = 'Prova scroll'")
        for name in ("Pensione", "Crescita", "Crescita"):
            folio = sql(f"SELECT id FROM portfolios WHERE name = '{name}'")
            pg.goto(B + "/portfolio/portfolios")
            with pg.expect_navigation():
                pg.click(f"form[action$='/portfolios/{folio}/default'] button[type=submit]")
            check(f"star on «{name}»", sql("SELECT string_agg(name, ',') FROM portfolios WHERE is_default") == name)
        shot("portfolios")

    def pac_and_calendar():
        """A PAC for «Pensione» in the Directa account from the form; its instalment in the deadlines; the .ics and the
        Google Calendar link make it a recurring event."""
        pg.goto(B + "/portfolio/plans/new")
        pg.fill("#f-name", "PAC Pensione")
        pg.fill("#f-amount", "250")
        pg.fill("#f-day", "20")
        pg.select_option("#f-portfolio_id", label="Pensione")
        pg.select_option("#f-securities_account_id", label="Conto titoli Directa")
        with pg.expect_navigation():
            pg.click("#plan-form button[type=submit].btn-primary")
        check("PAC saved with its portfolio and securities account", sql(
            "SELECT p.name || '/' || s.name FROM investment_plans i JOIN portfolios p ON p.id = i.portfolio_id "
            "JOIN securities_accounts s ON s.id = i.securities_account_id WHERE i.name = 'PAC Pensione'")
              == "Pensione/Conto titoli Directa")
        check("PAC listed with where it buys", "Pensione · Conto titoli Directa" in pg.content())
        nxt = sql("SELECT to_char(date_trunc('month', now()) + interval '1 month', 'YYYY-MM')")
        pg.goto(f"{B}/deadlines/?month={nxt}")
        text = pg.inner_text("main")
        check("deadlines: both PACs next month", "PAC «PAC Pensione»" in text and "PAC «PAC mensile Fineco»" in text)
        links = pg.eval_on_selector_all("a.deadline-gcal", "els => els.map(e => e.href)")
        pac_links = [link for link in links if "PAC" in link]
        check("Google Calendar link of a PAC repeats", pac_links and all("recur=RRULE" in link for link in pac_links),
              str(pac_links[:1]))
        shot("deadlines")
        ics = pg.request.get(B + "/deadlines/scadenze.ics?future=1").text()
        unfolded = ics.replace("\r\n ", "")
        events = [e for e in unfolded.split("BEGIN:VEVENT")[1:] if "PAC" in e.split("SUMMARY:")[1].split("\r\n")[0]]
        check("ics: one recurring event per PAC", len(events) == 2 and all("RRULE:FREQ=MONTHLY" in e for e in events),
              f"{len(events)} events")
        check("ics: the Pensione PAC on the 20th", any("BYMONTHDAY=20" in e and "PAC Pensione" in e for e in events))
        check("ics: lines folded with a space", all(len(line.encode()) <= 75 for line in ics.split("\r\n")))
        (OUT / "scadenze.ics").write_text(ics)

    def theoretical_orders():
        """The rebalancing with 5.000 € of new money saved as theoretical orders: nothing moves; confirmed with the
        liquidity left on the account, 12,50 € less than expected, which become the commissions."""
        before = sql("SELECT count(*) FROM transactions")
        pg.goto(B + "/portfolio/rebalance/orders?mode=new&amount=5000")
        dossier = sql("SELECT id FROM securities_accounts WHERE name = 'Dossier Fineco'")
        pg.select_option("select[name=securities_account_id]", value=dossier)
        with pg.expect_navigation():
            pg.click("button[name=action][value=plan]")
        text = pg.inner_text("main")
        check("theoretical orders saved", "Ordini salvati come teorici" in pg.content() and "lorda di commissioni" in text)
        check("theoretical orders move nothing", sql("SELECT count(*) FROM transactions") == before)
        orders = int(sql("SELECT count(*) FROM planned_orders"))
        check("theoretical orders listed", orders >= 2, str(orders))
        shot("planned")
        pg.goto(B + "/portfolio/")
        check("positions warn about the theoretical orders", "ordini teorici non ancora confermati" in pg.content())
        pg.goto(B + "/portfolio/planned")
        box = pg.locator(".fee-cash input").first
        expected = float(box.get_attribute("placeholder").replace(",", "."))
        box.fill(f"{expected - 12.5:.2f}".replace(".", ","))
        with pg.expect_navigation():
            pg.click(".planned-batch button[type=submit].btn-primary")
        check("confirmed: commissions from the liquidity", "12,50 € ricavati dalla liquidità" in pg.content(),
              pg.url)
        check("confirmed: trades recorded, nothing left", sql("SELECT count(*) FROM planned_orders") == "0"
              and int(sql("SELECT count(*) FROM transactions")) > int(before))
        check("confirmed: commissions add up to 12,50", sql(
            "SELECT sum(amount) FROM transactions WHERE fee_for_id IS NOT NULL AND date = current_date") == "12.50")
        shot("planned_confirmed")

    def archive():
        """The investments exported on their own, a holding deleted, the file restored from the page: everything
        comes back, the rest of the archive untouched."""
        before = (sql("SELECT count(*) FROM transactions"), sql("SELECT count(*) FROM holdings"),
                  sql("SELECT string_agg(name, ',' ORDER BY name) FROM portfolios"))
        response = pg.request.get(B + "/portfolio/archive")
        check("investments exported", response.ok and response.headers["content-type"] == "application/zip")
        path = OUT / "investimenti.zip"
        path.write_bytes(response.body())
        sql("DELETE FROM holdings WHERE isin = 'NL0010273215'")
        pg.goto(B + "/portfolio/import")
        pg.set_input_files("#archive-file", str(path))
        pg.check("#archive input[name=confirm]")
        pg.click("#archive button[type=submit]")
        confirm(pg)
        check("investments restored", "Investimenti ripristinati" in pg.content(), pg.url)
        after = (sql("SELECT count(*) FROM transactions"), sql("SELECT count(*) FROM holdings"),
                 sql("SELECT string_agg(name, ',' ORDER BY name) FROM portfolios"))
        check("restored as they were", after == before, f"{before} → {after}")
        shot("archive_restored")

    run("restore the investments backup", restore)
    run("every page of the portfolio", pages)
    run("rebalancing", rebalance)
    run("the statements of the two securities accounts", statements)
    run("the model's settings", model_settings)
    run("two new portfolios and the star", two_portfolios)
    run("a PAC, its deadlines and the calendar", pac_and_calendar)
    run("theoretical orders and commissions", theoretical_orders)
    run("the investments exported and restored", archive)
    check("no JavaScript errors", not errors, "; ".join(errors[:3]))
    b.close()

sys.exit(summary("investments"))
