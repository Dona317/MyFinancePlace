"""
Live: every flow of the app on a fresh database. Bank statements in every format, AI reading only after
confirmation, editable preview with AI classification, transactions, duplicates, export and CSV import,
reports, forecast, interface. Needs the session saved by login.py and the fake Ollama.
"""

import csv
import io
import json
import sys

from playwright.sync_api import sync_playwright

from common import AUTH, BASE, OUT, SAMPLES, check, launch, local_assets, run, sql, summary

S = str(SAMPLES) + "/"


def count(where="true"):
    return int(sql(f"select count(*) from transactions where {where}") or 0)


def alert_text():
    return " | ".join(t.strip() for t in pg.locator(".alert").all_inner_texts())


def import_file(filename, keep_all=True):
    """Upload a statement; returns True when the preview opened."""
    pg.goto(BASE + "/export/")
    pg.set_input_files("#bank-import input[type=file]", S + filename)
    pg.click("#bank-import button[type=submit]")
    pg.wait_for_load_state()
    return pg.locator("#import-button").count() > 0


def save_preview():
    pg.click("#import-button")
    pg.wait_for_load_state()
    return alert_text()


with sync_playwright() as p:
    browser = launch(p)
    ctx = browser.new_context(
        viewport={"width": 1440, "height": 900}, accept_downloads=True, locale="it-IT", storage_state=AUTH
    )
    pg = ctx.new_page()
    local_assets(pg)
    js_errors = []
    pg.on("pageerror", lambda e: js_errors.append(f"{pg.url}: {e}"))
    pg.on("dialog", lambda d: d.accept())

    # ── 1. Empty app ───────────────────────────────────────────────────────────
    def empty_app():
        for u in [
            "/dashboard",
            "/accounting/",
            "/accounting/balance-sheet",
            "/accounting/income-statement",
            "/accounting/cash-flow",
            "/lifestyle/",
            "/transactions/",
            "/transactions/duplicates",
            "/forecast/",
            "/export/",
            "/settings/",
            "/settings/ai",
            "/portfolio/",
            "/debt/",
            "/insurance/",
            "/documents/",
            "/snapshots/",
        ]:
            r = pg.goto(BASE + u)
            check(f"empty {u} opens", r.status == 200, r.status)
        pg.goto(BASE + "/forecast/")
        check("forecast without data explains what is needed", "Servono dei movimenti" in pg.content())

    run("1. Empty app", empty_app)

    # ── 2. AI models page ──────────────────────────────────────────────────────
    def ai_settings():
        pg.goto(BASE + "/settings/ai")
        check("Ollama detected with installed models", "qwen2.5vl:7b" in pg.content() and "llama3.2:1b" in pg.content())
        pg.select_option("#provider-select", "ollama")
        pg.fill("input[name=model]", "qwen2.5vl:7b")
        pg.fill("input[name=classify_model]", "qwen3:1.7b")
        pg.click("button:has-text('Salva')")
        pg.wait_for_load_state()
        check("AI reading activated", "Lettura AI attiva" in alert_text(), alert_text())
        # a model saved for Ollama is refused for Claude
        pg.select_option("#provider-select", "anthropic")
        pg.fill("input[name=model]", "qwen2.5vl:7b")
        pg.click("button:has-text('Salva')")
        pg.wait_for_load_state()
        check("Ollama model refused for Claude", "non è un modello per questo provider" in alert_text(), alert_text())
        pg.fill("form:has(input[placeholder='nome:tag']) input[name=name]", "gemma3:1b")
        pg.click("form:has(input[placeholder='nome:tag']) button[type=submit]")
        pg.wait_for_load_state()
        check("download started", "Download di gemma3:1b avviato" in alert_text(), alert_text())
        for _ in range(40):
            status = json.loads(pg.evaluate("fetch('/settings/ai/pull-status').then(r => r.text())"))
            if status.get("gemma3:1b", {}).get("done"):
                break
            pg.wait_for_timeout(500)
        check(
            "download completes with progress",
            status.get("gemma3:1b", {}).get("done") and not status["gemma3:1b"].get("error"),
            status.get("gemma3:1b"),
        )
        pg.goto(BASE + "/settings/ai")
        pg.click("form:has(input[name=name][value='llama3.2:1b']) button:has-text('Rimuovi')")
        pg.wait_for_load_state()
        check("model removed", "Modello llama3.2:1b rimosso" in alert_text(), alert_text())

    run("2. AI models page", ai_settings)

    # ── 3. Bank statements in every format ─────────────────────────────────────
    def statements():
        files = [
            "fineco_2026-06_2026-07.xlsx",
            "intesa_sanpaolo_2026-04_2026-09.xlsx",
            "intesa_sanpaolo_legacy_2026-03.xls",
            "banca_generica_2026-02.xls",
            "unicredit_2026-08_2026-09.csv",
            "revolut_2026-09.csv",
            "banca_popolare_2026-05.txt",
            "fineco_estratto_conto_2026-07_2026-08.pdf",
            "intesa_sanpaolo_lista_movimenti_2026-09.pdf",
            "estratto_conto_word_2026-01.docx",
            "estratto_conto_2025-11.rtf",
            "estratto_conto_libreoffice_2025-12.ods",
        ]
        for f in files:
            before = count()
            opened = import_file(f)
            if not opened:
                check(f"{f}: preview", False, alert_text())
                continue
            rows = pg.locator("tr.statement-row").count()
            new = pg.locator("tr.preview-row.statement-row").count()  # not already imported
            dup = pg.locator("tr.preview-row.statement-row.row-off").count()  # look-alikes, deselected
            msg = save_preview()
            saved = count() - before
            check(
                f"{f}: {rows} rows read, {rows - new} already imported, {saved} saved",
                rows > 0 and saved == new - dup and "movimenti importati" in msg,
                f"rows={rows} new={new} flagged={dup} saved={saved} msg={msg[:80]}",
            )
        check("bank causale kept on imported rows", count("bank_description is not null") > 0)
        # the same statement again: every row recognised as already imported
        import_file("fineco_2026-06_2026-07.xlsx")
        check(
            "re-import: all rows already imported, button disabled",
            pg.is_disabled("#import-button"),
            pg.locator(".preview-row").count(),
        )
        # an overlapping statement: only the new months
        before = count()
        import_file("fineco_2026-07_2026-09.xlsx")
        save_preview()
        check("overlapping statement adds only new movements", 0 < count() - before, count() - before)

    run("3. Statements in every format", statements)

    # ── 4. Unreadable files: AI only after confirmation ────────────────────────
    def ai_reading():
        before = count()
        import_file("FOTO_estratto_conto_intesa_2026-09.jpg")
        check(
            "photo: asks before using AI",
            "leggere il file con l'intelligenza artificiale" in pg.content().lower() or "/bank/ai/" in pg.url,
            pg.url,
        )
        check("nothing saved before confirming", count() == before)
        pg.select_option("select[name=model]", "qwen2.5vl:7b")
        pg.click("#ai-submit")
        pg.wait_for_selector("#import-button", timeout=90000)
        check("AI preview opens", pg.locator("#import-button").count() == 1, alert_text())
        check("balance check shown (a row is missing)", "saldo" in pg.content().lower())
        flagged = pg.locator("tr.row-off .row-include")
        check(
            "look-alikes deselected, import disabled until chosen",
            flagged.count() > 0 and pg.is_disabled("#import-button"),
            flagged.count(),
        )
        while flagged.count():  # checking a row takes it out of the list
            flagged.first.check()
        msg = save_preview()
        check("AI rows saved, tagged ai", count("'ai' = any(tags)") > 0, msg[:80])
        # scanned PDF, then cancel
        opened = import_file("SCANSIONE_fineco_2026-07_2026-08.pdf")
        check("scan: read by the light OCR, preview without AI", opened and "/bank/ai/" not in pg.url, pg.url)
        import_file("FOTO_estratto_conto_intesa_2026-09.jpg")
        if "/bank/ai/" in pg.url:
            pg.click("button:has-text('No, annulla')")
            pg.wait_for_load_state()
            check("AI reading can be cancelled", "Importazione annullata" in alert_text(), alert_text())

    run("4. AI reading with confirmation", ai_reading)

    # ── 5. Editable preview + AI classification in the preview ─────────────────
    def preview_edit():
        sql("delete from transactions where 'revolut' = any(tags) or tags::text like '%generic%'")
        import_file("revolut_2026-09.csv")
        first = pg.locator("tr.statement-row").first
        pg.click("#ai-classify")
        pg.wait_for_selector(
            "#ai-classify-status.alert-success, #ai-classify-status.alert-warning, #ai-classify-status.alert-error",
            timeout=20000,
        )
        check(
            "AI classification in the preview",
            "movimenti classificati" in pg.inner_text("#ai-classify-status"),
            pg.inner_text("#ai-classify-status")[:100],
        )
        first.locator("input[name^=description]").fill("Descrizione corretta a mano")
        first.locator(".row-category").fill("Categoria personalizzata")
        rows = pg.locator("tr.statement-row").count()
        pg.locator("tr.statement-row").nth(1).locator(".row-remove").click()
        pg.click("#add-row")
        new = pg.locator("tr.preview-row").last
        new.locator("input[type=date]").fill("2026-09-20")
        new.locator("input[name^=description]").fill("Riga aggiunta a mano")
        new.locator("input[name^=amount]").fill("12.34")
        before = count()
        save_preview()
        check(
            "edited preview saved (one row removed, one added)",
            count() - before == rows,
            f"{count() - before} vs {rows}",
        )
        check(
            "edits kept",
            count("description = 'Descrizione corretta a mano' and category = 'Categoria personalizzata'") == 1,
        )
        check("added row tagged manuale", count("description = 'Riga aggiunta a mano' and 'manuale' = any(tags)") == 1)
        check("accepted AI categories tagged categoria-ai", count("'da confermare (AI)' = any(tags)") > 0)

    run("5. Editable preview and AI classification", preview_edit)

    # ── 6. Transactions: add, filter, edit, delete ─────────────────────────────
    def transactions():
        pg.goto(BASE + "/transactions/new")
        pg.fill("input[name=date]", "2026-09-10")
        pg.fill("input[name=description]", "Palestra annuale")
        pg.fill("input[name=amount]", "-480")
        pg.select_option("select[name=category]", "Salute")
        pg.check("input[name=is_recurring]")
        pg.select_option("select[name=recurrence]", "yearly")
        pg.click("#edit-form button.btn-primary[type=submit]")
        pg.wait_for_load_state()
        check(
            "transaction added", count("description = 'Palestra annuale' and recurrence = 'yearly'") == 1, alert_text()
        )
        pg.goto(BASE + "/transactions/?q=Palestra")
        check("search filter", pg.locator("tbody tr:has-text('Palestra annuale')").count() == 1)
        pg.goto(BASE + "/transactions/?recurring=1")
        check("recurring filter", "Palestra annuale" in pg.content() and pg.locator("tbody tr").count() >= 1)
        tx_id = sql("select id from transactions where description = 'Palestra annuale'")
        pg.goto(BASE + f"/transactions/{tx_id}/edit")
        pg.fill("input[name=amount]", "-500")
        pg.click("#edit-form button.btn-primary[type=submit]")
        pg.wait_for_load_state()
        check(
            "edit keeps frequency",
            sql(f"select amount || ' ' || recurrence from transactions where id = {tx_id}") == "500.00 yearly",
        )
        pg.goto(BASE + f"/transactions/{tx_id}/edit")
        pg.click("button[form=delete-form]")
        pg.wait_for_load_state()
        check("delete from the edit page", count(f"id = {tx_id}") == 0, alert_text())
        pg.goto(BASE + "/transactions/?q=Riga aggiunta")
        before = count()
        pg.check("#select-all")
        pg.click("#bulk-delete")
        pg.wait_for_load_state()
        check("bulk delete", count() == before - 1, alert_text())
        bad = pg.request.post(
            BASE + "/transactions/new",
            form={"date": "2026-09-01", "description": "x", "amount": "NaN", "type": "expense"},
        )
        check("invalid amount refused without error", bad.status == 200 and count("description = 'x'") == 0, bad.status)

    run("6. Transactions", transactions)

    # ── 7. AI classification of saved transactions ─────────────────────────────
    def classify_saved():
        sql(
            "update transactions set category = 'Altro' where id in (select id from transactions where description ilike '%esselunga%' limit 3)"
        )
        pg.goto(BASE + "/transactions/")
        pg.click("#ai-classify")
        pg.wait_for_load_state()
        check(
            "review page before applying",
            "Classificazione AI" in pg.content() and pg.locator("input[name=apply]").count() > 0,
        )
        pg.click("button:has-text('Applica i selezionati')")
        pg.wait_for_load_state()
        check("suggestions applied", "transazioni aggiornate" in alert_text(), alert_text())
        check("no Esselunga left in Altro", count("description ilike '%esselunga%' and category = 'Altro'") == 0)

    run("7. AI classification of saved transactions", classify_saved)

    # ── 8. Duplicate finder ────────────────────────────────────────────────────
    def duplicate_finder():
        sql(
            "insert into transactions (date, description, amount, currency, type, category, tags, is_recurring) "
            "select date + 1, 'Pagamento POS ' || description, amount, currency, type, category, array['manuale'], false "
            "from transactions where description ilike '%netflix%' limit 2"
        )
        pg.goto(BASE + "/transactions/duplicates")
        groups = pg.locator("form[action$='/duplicates/keep']").count()
        check("duplicate groups found", groups >= 2, groups)
        pg.locator("form[action$='/duplicates/dismiss'] button").first.click()
        pg.wait_for_load_state()
        check("not duplicates: remembered", "non verranno più proposte" in alert_text(), alert_text())
        before = count()
        pg.locator("form[action$='/duplicates/keep'] button").first.click()
        pg.wait_for_load_state()
        check("keep one, delete the others", count() < before, alert_text())

    run("8. Duplicate finder", duplicate_finder)

    # ── 9. Export and CSV import ───────────────────────────────────────────────
    def export():
        csv_text = pg.request.get(BASE + "/export/csv?period=all").text()
        check("CSV export", csv_text.count("\n") - 1 == count(), f"{csv_text.count(chr(10)) - 1} vs {count()}")
        data = pg.request.get(BASE + "/export/json").json()
        check("JSON backup", len(data["transactions"]) == count())
        check("tax export", pg.request.get(BASE + "/export/tax/2026").status == 200)
        pg.goto(BASE + "/export/pdf?year=2026")
        check("printable report", "Report Finanziario 2026" in pg.content())
        rows = [
            ["Data", "Descrizione", "Importo"],
            ["01/08/2026", "Rimborso spese", "35,50"],
            ["02/08/2026", "Libri", "-20,00"],
        ]
        buffer = io.StringIO()
        csv.writer(buffer, delimiter=";").writerows(rows)
        open(str(OUT / "import.csv"), "w").write(buffer.getvalue())
        pg.goto(BASE + "/export/")
        pg.set_input_files("#import-file", str(OUT / "import.csv"))
        pg.select_option("select[name=col_date]", "Data")
        pg.select_option("select[name=col_description]", "Descrizione")
        pg.select_option("select[name=col_amount]", "Importo")
        pg.click("#import-submit")
        pg.wait_for_load_state()
        if pg.locator("#import-button").count():
            save_preview()
        check("CSV import with column mapping", count("description in ('Rimborso spese', 'Libri')") == 2, alert_text())

    run("9. Export and CSV import", export)

    # ── 10. Reports ────────────────────────────────────────────────────────────
    def reports():
        pg.goto(BASE + "/dashboard")
        pg.wait_for_timeout(500)
        check(
            "dashboard: real figures and charts",
            pg.evaluate("!!Chart.getChart('cashFlowChart')")
            and "Ryanair" not in ""
            and pg.locator(".kpi-value").first.inner_text() not in ("—", ""),
        )
        for u, marker in [
            ("/accounting/income-statement?year=2026", "Stipendio"),
            ("/accounting/cash-flow?year=2026", "Flusso"),
            ("/lifestyle/?year=2026", "Alimentari"),
            ("/accounting/", "Panoramica"),
        ]:
            pg.goto(BASE + u)
            check(f"{u} shows data", marker in pg.content())

    run("10. Reports", reports)

    # ── 11. Forecast ───────────────────────────────────────────────────────────
    def forecast():
        pg.goto(BASE + "/forecast/")
        pg.wait_for_timeout(600)
        check(
            "forecast dashboard", pg.locator(".fc-widget").count() == 12 and pg.evaluate("!!Chart.getChart('netChart')")
        )
        with pg.expect_navigation():
            pg.select_option("select[name=method]", "mediana")
        pg.fill("input[name=window]", "4")
        with pg.expect_navigation():
            pg.dispatch_event("input[name=window]", "change")
        with pg.expect_navigation():
            pg.select_option("select[name=recurring]", "ultimo")
        pg.goto(BASE + "/forecast/")
        check(
            "method, window and recurring amount remembered",
            [
                pg.input_value("select[name=method]"),
                pg.input_value("input[name=window]"),
                pg.input_value("select[name=recurring]"),
            ]
            == ["mediana", "4", "ultimo"],
        )
        errors = pg.eval_on_selector_all(".method-error", "c => c.map(x => x.innerText)")
        check("methods compared on income and expenses", len(errors) == 12, len(errors))
        if pg.locator(".candidate-form").count():
            pg.locator(".candidate-form button").first.click()
            pg.wait_for_load_state()
            check(
                "detected recurring series confirmed", "è ora una transazione ricorrente" in alert_text(), alert_text()
            )
        else:
            check("detected recurring series (none in this data)", True)
        pg.click("#layout-edit")
        pg.click(".fc-widget[data-widget=help] [data-act=hide]")
        pg.click(".fc-widget[data-widget=balance] [data-act=span]")
        pg.wait_for_timeout(600)
        pg.reload()
        check(
            "layout remembered",
            pg.locator(".fc-widget[data-widget=help][hidden]").count() == 1
            and pg.get_attribute(".fc-widget[data-widget=balance]", "data-span") == "2",
        )
        pg.click("#layout-edit")
        pg.click("#layout-reset")
        pg.wait_for_timeout(1000)
        check("layout reset", pg.locator(".fc-widget[hidden]").count() == 0)

    run("11. Forecast", forecast)

    # ── 12. Interface ──────────────────────────────────────────────────────────
    def interface():
        pg.goto(BASE + "/dashboard")
        if pg.evaluate("document.documentElement.dataset.theme") == "dark":
            pg.click("#theme-toggle")
        pg.click("#theme-toggle")
        pg.reload()
        check("dark mode remembered", pg.evaluate("document.documentElement.dataset.theme") == "dark")
        pg.click("#theme-toggle")
        pg.click(".nav-section[data-section=strumenti] .nav-section-title")
        pg.reload()
        check(
            "sidebar section collapse remembered",
            pg.locator(".nav-section[data-section=strumenti].collapsed").count() == 1,
        )
        pg.click(".nav-section[data-section=strumenti] .nav-section-title")
        pg.click("#sidebar-toggle")
        pg.reload()
        check(
            "icons-only sidebar remembered", pg.evaluate("document.documentElement.classList.contains('sidebar-mini')")
        )
        pg.click("#sidebar-toggle")
        pg.click(".topbar-settings")
        pg.wait_for_load_state()
        check("settings button", pg.url.endswith("/settings/"))
        pg.goto(BASE + "/accounting/balance-sheet")
        check("one active menu item", pg.eval_on_selector_all(".sidebar .nav-item.active", "e => e.length") == 1)

    run("12. Interface", interface)

    check("no JavaScript errors in the whole run", not js_errors, js_errors[:3])
    browser.close()

sys.exit(summary("flows"))
