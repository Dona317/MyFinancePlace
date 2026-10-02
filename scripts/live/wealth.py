"""
Live: wealth pages on top of the flows run. Portfolio and prices, debts with their plan, insurance reminders,
goals and contributions, documents upload and link, balance sheet, snapshots and compare, backup and restore.
"""

import io
import json
import sys
import zipfile
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

from common import AUTH, BASE as B, OUT, check, launch, local_assets, summary

with sync_playwright() as p:
    b = launch(p)
    ctx = b.new_context(viewport={"width": 1400, "height": 900}, accept_downloads=True, storage_state=AUTH)
    pg = ctx.new_page()
    local_assets(pg)
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("dialog", lambda d: d.accept())

    def go(selector):
        with pg.expect_navigation():
            pg.click(selector)

    # Portfolio
    pg.goto(B + "/portfolio/")
    check("portfolio empty state", "Nessuna posizione" in pg.content())
    go("text=Aggiungi Posizione >> nth=0")
    pg.fill("#f-name", "Vanguard FTSE All-World")
    pg.fill("#f-ticker", "VWCE")
    pg.select_option("#f-asset_class", "ETF")
    pg.fill("#f-quantity", "120")
    pg.fill("#f-avg_price", "98,40")
    pg.fill("#f-current_price", "121,15")
    pg.fill("#f-purchase_date", "2024-03-01")
    go("button:has-text('Aggiungi al Portafoglio')")
    check("holding saved", "Posizione «Vanguard FTSE All-World» aggiunta" in pg.content())
    for name, cls, q, price in [
        ("Conto deposito Illimity", "Conto Risparmio", "1", "15.000"),
        ("Bitcoin", "Criptovaluta", "0,15", "42000"),
        ("BTP Italia 2030", "Obbligazione", "50", "99,5"),
        ("Fondo pensione", "Fondo Pensione", "1", "8.400"),
    ]:
        pg.goto(B + "/portfolio/new")
        pg.fill("#f-name", name)
        pg.select_option("#f-asset_class", cls)
        pg.fill("#f-quantity", q)
        pg.fill("#f-avg_price", price)
        go(".main-content button[type=submit].btn-primary")
    pg.goto(B + "/portfolio/prices")
    pg.fill("input[aria-label='Nuovo prezzo di Bitcoin']", "58000")
    go("text=Salva prezzi")
    check("price updated", "Prezzi aggiornati: 1" in pg.content())

    # Debt
    pg.goto(B + "/debt/new")
    pg.select_option("#f-type", "Mutuo")
    pg.fill("#f-name", "Mutuo casa — Intesa")
    pg.fill("#f-principal", "180.000")
    pg.fill("#f-annual_rate", "2,9")
    pg.fill("#f-start_date", "2021-05-10")
    pg.fill("#f-term_months", "300")
    go("button:has-text('Aggiungi Debito')")
    check("debt plan shown", "Piano di Ammortamento" in pg.content() and "Rate Rimanenti" in pg.content())
    pg.goto(B + "/debt/new")
    pg.select_option("#f-type", "Prestito Auto")
    pg.fill("#f-name", "Findomestic auto")
    pg.fill("#f-principal", "14000")
    pg.fill("#f-annual_rate", "6,5")
    pg.fill("#f-start_date", "2024-09-01")
    pg.fill("#f-term_months", "48")
    go(".main-content button[type=submit].btn-primary")
    pg.goto(B + "/debt/new")
    pg.select_option("#f-type", "Carta di Credito")
    pg.fill("#f-name", "Amex")
    pg.fill("#f-principal", "650")
    pg.fill("#f-balance", "650")
    go(".main-content button[type=submit].btn-primary")
    pg.goto(B + "/debt/")
    check("debt index charts", pg.locator("#debtAmortChart").count() == 1 and pg.locator("#debtPieChart").count() == 1)

    # Insurance
    soon = (date.today() + timedelta(days=25)).isoformat()
    pg.goto(B + "/insurance/new")
    pg.select_option("#f-type", "Auto")
    pg.fill("#f-company", "UnipolSai")
    pg.select_option("#f-frequency", "biannual")
    pg.fill("#f-premium", "310")
    pg.fill("#f-coverage_limit", "6.000.000")
    pg.fill("#f-expiry_date", soon)
    go(".main-content button[type=submit].btn-primary")
    pg.goto(B + "/insurance/new")
    pg.select_option("#f-type", "Casa")
    pg.fill("#f-company", "Generali")
    pg.fill("#f-premium", "240")
    pg.fill("#f-expiry_date", (date.today() + timedelta(days=200)).isoformat())
    go(".main-content button[type=submit].btn-primary")
    check("insurance reminder", "scade entro 60 giorni" in pg.content() and "€ 860,00" in pg.content())

    # Goals
    pg.goto(B + "/lifestyle/goals")
    go(".suggestion >> nth=0")
    check(
        "suggestion prefilled",
        pg.input_value("#f-name") == "Fondo d'emergenza" and pg.input_value("#f-target_amount") != "",
    )
    pg.fill("#f-saved_amount", "4.000")
    pg.fill("#f-target_date", (date.today() + timedelta(days=365)).isoformat())
    go(".main-content button[type=submit].btn-primary")
    pg.goto(B + "/lifestyle/goals/new?name=Vacanza%20Giappone&target_amount=4500")
    go(".main-content button[type=submit].btn-primary")
    pg.fill(".goal-card >> nth=1 >> input[name=amount]", "300")
    go(".goal-card >> nth=1 >> text=Versa")
    check("contribution", "aggiunti € 300,00" in pg.content())

    # Documents
    pg.goto(B + "/documents/")
    pg.set_input_files(
        "#up-files",
        [
            {"name": "fattura_enel.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4\n%fake"},
            {"name": "scontrino.png", "mimeType": "image/png", "buffer": bytes.fromhex("89504e470d0a1a0a")},
        ],
    )
    check("drop zone text", "Pronti 2 file" in pg.inner_text("#drop-text"))
    pg.select_option("#up-type", "Fattura")
    go("button:has-text('Carica') >> nth=-1")
    check("documents uploaded", "2 documenti caricati" in pg.content())
    go("a[title='Modifica e collega'] >> nth=0")
    pg.select_option("#f-tx", index=1)
    go("button:has-text('Salva')")
    check("document linked", "aggiornato" in pg.content() and pg.locator("td a[href*='/transactions/']").count() >= 1)

    # Balance sheet + opening cash
    pg.goto(B + "/accounting/balance-sheet")
    pg.fill("input[name=opening_cash]", "3.500")
    go("form[action*=opening] button")
    check("opening cash", "Saldo iniziale dei conti aggiornato" in pg.content())
    with pg.expect_navigation():
        pg.select_option("select[name=date] ", index=3)
    check("past balance sheet", "Al " in pg.inner_text("select[name=date] option:checked"))

    # Snapshots
    pg.goto(B + "/snapshots/")
    pg.fill("input[name=label]", "Settembre")
    go("button:has-text('Crea Istantanea')")
    check("snapshot created", "Istantanea del" in pg.content())
    pg.goto(B + "/portfolio/prices")
    pg.fill("input[aria-label='Nuovo prezzo di Vanguard FTSE All-World']", "130")
    go("text=Salva prezzi")
    pg.goto(B + "/snapshots/")
    go("button:has-text('Crea Istantanea')")
    go("button:has-text('Confronta')")
    check("compare shows diff", "+€ 1.062,00" in pg.content())
    pg.goto(B + "/snapshots/")

    # Dashboard & accounting overview
    pg.goto(B + "/dashboard")
    pg.wait_for_timeout(300)
    kpi = pg.inner_text(".kpi-grid")
    inv = kpi.upper().split("INVESTIMENTI")[1].split("\n")[1]
    check("dashboard investments not zero", inv.strip() not in ("0,00 €", "€ 0,00"))
    pg.goto(B + "/accounting/")

    # Backup → change → restore
    pg.goto(B + "/export/")
    with pg.expect_download() as dl:
        pg.click("text=Scarica backup completo")
    path = dl.value.path()
    raw = open(path, "rb").read()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        data = json.loads(z.read("backup.json"))
        names = z.namelist()
    check(
        "backup has all tables",
        {k: len(v) for k, v in data["tables"].items()}["holdings"] == 5
        and sum(n.startswith("documents/") for n in names) == 2,
    )
    open(str(OUT / "backup.zip"), "wb").write(raw)
    pg.goto(B + "/debt/")
    go("button[title=Elimina] >> nth=0")
    pg.goto(B + "/export/")
    pg.set_input_files("#backup input[type=file]", str(OUT / "backup.zip"))
    pg.check("#backup input[name=confirm]")
    go("#backup button:has-text('Ripristina')")
    check("restored", "Backup ripristinato" in pg.content() and "3 debiti" in pg.content())
    check("safety copy listed", "Backup automatici (1)" in pg.content())
    check("no JavaScript errors", not errors, errors[:3])
    b.close()
sys.exit(summary("wealth"))
