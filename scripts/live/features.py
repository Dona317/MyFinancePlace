"""
Live: the features added after the first runs. Currencies and accounts, signed amounts, tags and subcategories,
transfers, budget, merchant from the causale, column guessing, dashboard charts and their switches, reports,
categories and rules, language, reminders, password change, and a crawl of every page in light and dark mode,
desktop and phone (screenshots in LIVE_SHOTS when set).
"""

import sys

from playwright.sync_api import sync_playwright

from common import AUTH, BASE as B, OUT, SHOTS, check, launch, local_assets, run, sql, summary

with sync_playwright() as p:
    br = launch(p)
    ctx = br.new_context(
        viewport={"width": 1440, "height": 900}, locale="it-IT", accept_downloads=True, storage_state=AUTH
    )
    pg = ctx.new_page()
    local_assets(pg)
    js = []
    pg.on("pageerror", lambda e: js.append(f"{pg.url}: {e}"))
    pg.on("dialog", lambda d: d.accept())

    def alert():
        return " | ".join(t.strip() for t in pg.locator(".alert").all_inner_texts())

    def submit():
        pg.click(".main-content button[type=submit].btn-primary")
        pg.wait_for_load_state()

    def currencies():
        pg.goto(B + "/settings/currencies")
        pg.select_option("#c-cur", "USD")
        pg.fill("#c-on", "2026-06-01")
        pg.fill("#c-rate", "0,8")
        pg.click("text=Salva cambio")
        pg.wait_for_load_state()
        check("exchange rate saved", sql("select count(*) from exchange_rates") != "0", alert())
        for name, cur, bal in (("Conto Fineco", "EUR", "1000"), ("Conto USD", "USD", "500")):
            pg.goto(B + "/accounts/new")
            pg.fill("[name=name]", name)
            pg.select_option("[name=currency]", cur)
            pg.fill("[name=opening_balance]", bal)
            pg.click(".page-form button[type=submit]")
            pg.wait_for_load_state()
        check("two accounts created", sql("select count(*) from accounts") == "2")
        pg.goto(B + "/transactions/new")
        pg.fill("#f-date", "2026-06-01")
        pg.fill("#f-amount", "-100")
        pg.fill("[name=description]", "Hotel New York")
        pg.select_option("#f-account", label="Conto Fineco")
        check("account amount hidden when currencies match", pg.is_hidden("#account-amount-group"))
        pg.select_option("#f-currency", "USD")
        check("account amount asked for a USD expense on a EUR account", pg.is_visible("#account-amount-group"))
        submit()
        check(
            "USD expense saved",
            sql("select currency from transactions where description='Hotel New York'") == "USD",
            alert(),
        )
        pg.goto(B + "/accounts/")
        check(
            "accounts page shows balances in their currency",
            "$" in pg.inner_text("table") or "USD" in pg.inner_text("table"),
        )

    run("A. Currencies and accounts", currencies)

    def signed_tags_subcategories():
        pg.goto(B + "/transactions/new")
        pg.fill("#f-date", "2026-09-12")
        pg.fill("#f-amount", "-72,21")
        pg.fill("[name=description]", "Enel bolletta settembre")
        check("sign shows expense", "Uscita" in pg.inner_text("#amount-kind"))
        pg.select_option("#f-category", "Luce")
        tag = pg.locator(".tag-picker-input").first
        tag.click()
        pg.keyboard.type("casa")
        pg.keyboard.press("Enter")
        submit()
        row = sql(
            "select type, amount, category, array_to_string(tags, ',') from transactions where description='Enel bolletta settembre'"
        )
        check("signed expense with subcategory and tag", row.startswith("expense|72.21|Luce|") and "casa" in row, row)
        pg.goto(B + "/transactions/new")
        pg.fill("#f-date", "2026-09-27")
        pg.fill("#f-amount", "1500")
        pg.fill("[name=description]", "Bonifico da ACME SPA per STIPENDIO 09/2026")
        check("positive sign shows income", "Entrata" in pg.inner_text("#amount-kind"))
        submit()
        check(
            "income saved from a positive amount",
            sql("select type from transactions where amount=1500 and description like 'Bonifico da ACME%'") == "income",
        )
        pg.goto(B + "/transactions/?category=Bollette")
        check("filter by main category includes subcategories", "Enel bolletta settembre" in pg.inner_text("tbody"))

    run("B. Signed amounts, tags, subcategories", signed_tags_subcategories)

    def split():
        pg.goto(B + "/transactions/new")
        pg.fill("#f-date", "2026-09-14")
        pg.fill("#f-amount", "-100")
        pg.fill("[name=description]", "Supermercato spesa e casa")
        pg.select_option("#f-category", "Alimentari")
        pg.click("#split-open")
        rows = pg.locator(".split-row")
        rows.nth(0).locator(".split-amount").fill("70")
        rows.nth(1).locator("select").select_option("Casa")
        check("left to assign shown as you type", "30" in pg.inner_text("#split-left"))
        rows.nth(1).locator(".split-amount").fill("30")
        submit()
        parts = sql("select string_agg(s.category || ' ' || s.amount, ', ' order by s.id) from transaction_splits s "
                    "join transactions t on t.id = s.transaction_id where t.description = 'Supermercato spesa e casa'")
        check("split transaction saved with its parts", parts == "Alimentari 70.00, Casa 30.00", parts)
        pg.goto(B + "/transactions/?q=Supermercato spesa")
        check("list shows both categories", "Alimentari + Casa" in pg.inner_text("tbody"))
        pg.goto(B + "/reports/?tab=spending&period=custom&start=2026-09-14&end=2026-09-14&category=Casa")
        check("report filtered by category shows the part", "di" in pg.inner_text(".report-list"))
        pg.goto(B + "/reports/summary?year=2026")
        check("summary page", pg.locator(".summary-table").count() == 1)
    run("B2. Split transaction", split)

    def transfer():
        pg.goto(B + "/transactions/new")
        pg.fill("#f-date", "2026-09-15")
        pg.fill("#f-amount", "-200")
        pg.fill("[name=description]", "Giroconto verso USD")
        pg.check("#f-transfer")
        check("transfer: destination account shown", pg.is_visible("#f-counter"))
        pg.select_option("#f-account", label="Conto Fineco")
        pg.select_option("#f-counter", label="Conto USD")
        pg.fill("#f-counter-amount", "230")
        submit()
        check(
            "transfer saved between accounts",
            sql("select type from transactions where description='Giroconto verso USD'") == "transfer",
            alert(),
        )

    run("C. Transfer between accounts", transfer)

    def budget():
        pg.goto(B + "/lifestyle/budget?month=2026-09")
        pg.fill("input[name='every-Alimentari']", "300")
        pg.fill("input[name='every-Bollette']", "150")
        submit()
        check("budget saved", "300" in pg.input_value("input[name='every-Alimentari']"), alert())
        pg.goto(B + "/lifestyle/?year=2026")
        check("lifestyle page shows budgets", "Alimentari" in pg.content())

    run("D. Budget", budget)

    def merchant():
        sql(
            "update transactions set counterparty=null, tags=array_remove(tags, 'Esselunga') where description ilike '%esselunga%'"
        )
        pg.goto(B + "/transactions/")
        btn = pg.locator("text=/Compila controparti/")
        check("fill-counterparties button offered", btn.count() == 1)
        btn.first.click()
        pg.wait_for_load_state()
        check("counterparties filled from the causale", "controparte" in alert(), alert())
        check(
            "Esselunga is the counterparty",
            sql("select count(*) from transactions where counterparty='Esselunga'") != "0",
        )

    run("E. Merchant from the causale", merchant)

    def columns():
        open(str(OUT / "headerless.csv"), "w").write(
            "01/09/2026;Pagamento POS ESSELUNGA MILANO;-45,20\n02/09/2026;Stipendio ACME;1800,00\n"
            "03/09/2026;NETFLIX.COM;-12,99\n05/09/2026;Farmacia Comunale;-8,50\n"
        )
        pg.goto(B + "/export/")
        pg.set_input_files("#import-file", str(OUT / "headerless.csv"))
        pg.wait_for_function("document.getElementById('import-status').textContent.length > 0")
        got = {f: pg.eval_on_selector(f"select[name=col_{f}]", "e=>e.value") for f in ("date", "amount", "description")}
        check("columns recognised from the values (no header)", all(got.values()), got)
        pg.select_option("select[name=col_date]", got["description"])  # wrong on purpose
        pg.click("#import-submit")
        pg.wait_for_load_state()
        check("wrong column: preview instead of an error", pg.locator(".row-include").count() == 4, alert())
        if pg.locator("#import-button").count():
            pg.click("#import-button")
            pg.wait_for_load_state()
        check(
            "rows imported",
            sql("select count(*) from transactions where description='NETFLIX.COM' and amount=12.99") == "1",
            alert(),
        )

    run("F. Column guessing", columns)

    def dashboard():
        pg.goto(B + "/dashboard?year=2026")
        pg.wait_for_timeout(800)
        kpi = pg.inner_text(".kpi-grid")
        check("amounts written like the server does (€ 1.234,56)", "€ " in kpi and " €" not in kpi, kpi[:80])
        check("Sankey drawn", pg.locator("svg.sankey .sankey-band").count() > 2)
        check("monthly net chart", pg.evaluate("!!Chart.getChart('netChart')"))
        check("yearly three bars", pg.evaluate("Chart.getChart('yearChart')?.data.datasets[0].data.length") == 3)
        if SHOTS:
            pg.screenshot(path=f"{SHOTS}/dashboard_full.png", full_page=True)
        pg.goto(B + "/settings/")
        pg.click("label.toggle-switch:has(input[name=dashboard_sankey])")
        pg.wait_for_load_state()
        pg.goto(B + "/dashboard?year=2026")
        check(
            "Sankey hidden from settings",
            pg.locator("svg.sankey").count() == 0 and pg.locator("#netChart").count() == 1,
        )
        pg.goto(B + "/settings/")
        pg.click("label.toggle-switch:has(input[name=dashboard_sankey])")
        pg.wait_for_load_state()
        pg.goto(B + "/dashboard?year=2026")
        check("Sankey back on", pg.locator("svg.sankey").count() == 1)

    run("G. Dashboard charts and toggles", dashboard)

    def reports():
        for u in [
            "/reports/?period=this_year",
            "/reports/?tab=income&period=last_12",
            "/reports/?tab=cashflow&period=last_12",
            "/reports/?period=custom&start=2026-09-01&end=2026-09-30&category=Bollette",
        ]:
            r = pg.goto(B + u)
            check(f"report {u}", r.status == 200 and pg.locator("table, canvas").count() > 0, r.status)
        check("tax export", pg.request.get(B + "/export/tax/2026").status == 200)
        check("printable report", pg.request.get(B + "/export/pdf?year=2026").status == 200)

    run("H. Reports and exports", reports)

    def categories_rules():
        pg.goto(B + "/settings/categories")
        pg.fill("#new-name", "Animali")
        pg.select_option("#new-kind", "expense")
        pg.fill("#new-hint", "veterinario, cibo")
        pg.click("form:has(#new-name) button[type=submit]")
        pg.wait_for_load_state()
        check("category added", sql("select count(*) from categories where name='Animali'") == "1", alert())
        if pg.locator("#new-parent").count():
            pg.fill("#new-name", "Veterinario")
            pg.select_option("#new-parent", label="Animali")
            pg.click("form:has(#new-name) button[type=submit]")
            pg.wait_for_load_state()
            check(
                "subcategory added",
                sql("select p.name from categories c join categories p on p.id=c.parent_id where c.name='Veterinario'")
                == "Animali",
            )
        pg.fill("input[aria-label='Nome di Animali']", "Animali domestici")
        pg.click("button[aria-label='Salva Animali']")
        pg.wait_for_load_state()
        check("category renamed", sql("select count(*) from categories where name='Animali domestici'") == "1", alert())
        pg.click("button[aria-label='Elimina Animali domestici']")
        pg.wait_for_load_state()
        check("category deleted", sql("select count(*) from categories where name='Animali domestici'") == "0", alert())
        pg.goto(B + "/settings/rules")
        pg.fill("#r-keyword", "farmacia")
        pg.select_option("#r-category", "Salute")
        pg.click("form:has(#r-keyword) button[type=submit]")
        pg.wait_for_load_state()
        check("rule added", sql("select count(*) from category_rules where keyword ilike 'farmacia'") != "0", alert())
        pg.locator("form[action$='/rules/apply'] button").first.click()
        pg.wait_for_load_state()
        check("rules applied", pg.locator(".alert").count() > 0, alert())

    run("I. Categories and rules", categories_rules)

    def language():
        pg.goto(B + "/settings/")
        with pg.expect_navigation():
            pg.select_option("#s-language", "en")
        pg.goto(B + "/dashboard?year=2026")
        check("interface in English", "Where the money goes" in pg.content() and "net worth" in pg.content().lower())
        pg.goto(B + "/transactions/new")
        check("English form", "Description" in pg.content())
        pg.goto(B + "/settings/")
        with pg.expect_navigation():
            pg.select_option("#s-language", "it")
        pg.goto(B + "/dashboard")
        check("back to Italian", "Patrimonio" in pg.content())

    run("J. Language", language)

    def notifications():
        r = pg.goto(B + "/notifications/")
        check("reminders page", r.status == 200)

    run("K. Reminders", notifications)

    def password():
        pg.goto(B + "/settings/account")
        pg.fill("#pw-current", "password-1")
        pg.fill("#pw-new", "password-nuova-1")
        pg.fill("#pw-confirm", "password-nuova-1")
        pg.click("form:has(#pw-current) button[type=submit]")
        pg.wait_for_load_state()
        check("password changed", "password" in alert().lower(), alert())
        c2 = br.new_context()
        p2 = c2.new_page()
        p2.goto(B + "/auth/login")
        p2.fill("#username", "anna")
        p2.fill("#password", "password-1")
        p2.click("button[type=submit]")
        p2.wait_for_load_state()
        check("old password refused", "/auth/login" in p2.url)
        p2.fill("#username", "anna")
        p2.fill("#password", "password-nuova-1")
        p2.click("button[type=submit]")
        p2.wait_for_load_state()
        check("new password accepted", "/auth/login" not in p2.url)
        c2.close()

    run("L. Password change", password)

    def crawl():
        urls = set()
        for u in [
            "/dashboard",
            "/transactions/",
            "/export/",
            "/settings/",
            "/accounting/",
            "/lifestyle/",
            "/reports/",
            "/portfolio/",
            "/debt/",
            "/insurance/",
            "/documents/",
            "/snapshots/",
            "/accounts/",
            "/forecast/",
        ]:
            pg.goto(B + u)
            for h in pg.eval_on_selector_all("a[href^='/']", "els => els.map(e => e.getAttribute('href'))"):
                h = h.split("#")[0]
                if h and not any(
                    x in h
                    for x in ("logout", "/csv", "/json", "download", "/pdf", "/tax/", "/backup", "delete", "/api")
                ):
                    urls.add(h)
        urls = sorted(urls)
        bad = []
        for theme in ("light", "dark"):
            for width in (1440, 390):
                c = br.new_context(viewport={"width": width, "height": 900}, storage_state=AUTH, locale="it-IT")
                q = c.new_page()
                local_assets(q)
                errs = []
                q.on("pageerror", lambda e: errs.append(str(e)))
                q.goto(B + "/dashboard")
                q.evaluate(f"localStorage.setItem('mfp-theme','{theme}')")
                for u in urls:
                    errs.clear()
                    r = q.goto(B + u)
                    q.wait_for_timeout(150)
                    over = q.evaluate("document.documentElement.scrollWidth - innerWidth")
                    if r.status != 200 or errs or over > 1:
                        bad.append((theme, width, u, r.status, over, errs[:1]))
                    if SHOTS and theme == "light" and width == 1440:
                        q.screenshot(
                            path=f"{SHOTS}/{u.strip('/').replace('/', '_').replace('?', '_') or 'root'}.png",
                            full_page=True,
                        )
                c.close()
        check(f"crawl {len(urls)} pages × light/dark × desktop/phone: no errors, no overflow", not bad, bad[:5])

    run("M. Crawl", crawl)

    check("no JavaScript errors", not js, js[:3])
    br.close()
sys.exit(summary("features"))
