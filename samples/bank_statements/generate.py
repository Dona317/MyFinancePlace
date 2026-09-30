"""
Generate FAKE bank statements for trying out the bank import (Esporta → Importa Estratto Conto Bancario).

    python samples/bank_statements/generate.py

All names, IBANs and amounts are invented. The output is deterministic (fixed random seed),
so re-running the script produces the same movements.

Requires openpyxl and python-docx (in requirements.txt). Two samples need generation-only
libraries and are skipped when these are missing: the binary .xls needs `xlwt`, the PDFs need
`fpdf2` (pip install xlwt fpdf2).
"""
import csv
import random
import sys
import textwrap
from datetime import date, timedelta
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

OUT = Path(__file__).resolve().parent
HOLDER = "MARIO ROSSI"
ORIGIN = date(2026, 1, 1)

# Merchants per category: (description shown by the bank, min €, max €)
SHOPS = {
    "grocery":   [("ESSELUNGA MILANO", 25, 140), ("CONAD CITY", 10, 60), ("LIDL ITALIA", 15, 80), ("CARREFOUR EXPRESS", 8, 45)],
    "fuel":      [("ENI STATION 1043", 40, 75), ("Q8 VIA EMILIA", 35, 70)],
    "transport": [("TRENITALIA WEB", 12, 60), ("ATM MILANO", 2.2, 2.2), ("TELEPASS SPA", 15, 40)],
    "leisure":   [("RISTORANTE DA LUIGI", 30, 90), ("PIZZERIA NAPOLI", 18, 45), ("DELIVEROO ITALY", 15, 35),
                  ("CINEMA ANTEO", 9, 20), ("BAR CENTRALE", 1.5, 6)],
    "health":    [("FARMACIA COMUNALE 3", 6, 45)],
    "other":     [("AMAZON EU SARL", 10, 120), ("DECATHLON", 20, 90), ("LIBRERIA FELTRINELLI", 9, 35)],
}


def money(rng: random.Random, low: float, high: float) -> float:
    return round(rng.uniform(low, high), 2)


def movements(start: date, end: date, seed: int, salary: float, rent: float) -> list[dict]:
    """A realistic month-by-month list of movements between start and end (inclusive).

    Each movement: date, amount (signed), short (bank operation type), full (merchant/details), kind.
    """
    rng = random.Random(seed)
    items: list[dict] = []

    def add(day: date, amount: float, short: str, full: str, kind: str):
        if start <= day <= end:
            items.append({"date": day, "amount": round(amount, 2), "short": short, "full": full, "kind": kind})

    # Always generate from the same origin so files with the same seed contain identical
    # movements where their periods overlap (like two consecutive downloads from the same account)
    month = min(ORIGIN, date(start.year, start.month, 1))
    while month <= end:
        y, m = month.year, month.month
        add(date(y, m, 1), -rent, "Bonifico SEPA", f"Bonifico a IMMOBILIARE CASA BELLA SRL per AFFITTO {m:02d}/{y}", "rent")
        add(date(y, m, 5), -17.99, "Pagamento carta", "NETFLIX.COM AMSTERDAM", "subscription")
        add(date(y, m, 6), -10.99, "Pagamento carta", "SPOTIFY AB STOCKHOLM", "subscription")
        add(date(y, m, 12), -money(rng, 55, 95), "Addebito SDD", f"ENEL ENERGIA SPA bolletta luce {m:02d}/{y}", "utility")
        add(date(y, m, 14), -money(rng, 20, 60), "Addebito SDD", "A2A ENERGIA gas", "utility")
        add(date(y, m, 18), -9.99, "Addebito SDD", "ILIAD ITALIA SPA ricarica", "subscription")
        add(date(y, m, 20), -200.00, "Giroconto", "Giroconto verso conto deposito", "transfer")
        add(date(y, m, 27), salary, "Bonifico SEPA", f"Bonifico da ACME SPA per STIPENDIO {m:02d}/{y}", "salary")
        add(date(y, m, 28) if m != 2 else date(y, m, 27), -money(rng, 1.5, 4), "Commissioni", "COMMISSIONI BONIFICO", "fee")

        # Everyday card payments
        for _ in range(rng.randint(14, 20)):
            category = rng.choices(list(SHOPS), weights=[6, 2, 2, 4, 1, 2])[0]
            name, low, high = rng.choice(SHOPS[category])
            day = date(y, m, rng.randint(1, 28))
            add(day, -money(rng, low, high), "Pagamento carta", f"PAGAMENTO POS {name}", category)

        if rng.random() < 0.5:
            add(date(y, m, rng.randint(2, 25)), money(rng, 150, 600), "Bonifico SEPA",
                "Bonifico da STUDIO BIANCHI per FATTURA consulenza", "freelance")

        month = date(y + (m == 12), m % 12 + 1, 1)

    items.sort(key=lambda i: i["date"])
    return items


def autosize(sheet):
    for column in sheet.columns:
        width = max(len(str(c.value or "")) for c in column)
        sheet.column_dimensions[column[0].column_letter].width = min(max(width + 2, 10), 60)


# ── Fineco ─────────────────────────────────────────────────────────────────────

MONEYMAP = {
    "grocery": "Spesa", "fuel": "Carburante", "transport": "Trasporti", "leisure": "Ristoranti e bar",
    "health": "Salute", "other": "Shopping", "rent": "Affitto", "subscription": "Abbonamenti",
    "utility": "Utenze", "transfer": "Trasferimenti", "salary": "Stipendio", "fee": "Commissioni",
    "freelance": "Entrate varie",
}


def fineco(path: Path, start: date, end: date, seed: int, pending: int = 2):
    rows = movements(start, end, seed, salary=2450.00, rent=850.00)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Movimenti"
    ws.append(["Conto Corrente: 0012345678"])
    ws.append([f"Intestazione Conto Corrente: {HOLDER}"])
    ws.append([f"Periodo Dal: {start:%d/%m/%Y} Al: {end:%d/%m/%Y}"])
    ws.append(["Saldo Iniziale: 3.250,00"])
    ws.append([])
    ws.append(["Data_Operazione", "Data_Valuta", "Entrate", "Uscite", "Descrizione", "Descrizione_Completa", "Stato", "Moneymap"])
    for cell in ws[6]:
        cell.font = Font(bold=True)
    for index, r in enumerate(rows):
        status = "Autorizzato" if index >= len(rows) - pending else "Contabilizzato"
        day = f"{r['date']:%d/%m/%Y}"
        ws.append([
            day, day,
            r["amount"] if r["amount"] > 0 else None,
            r["amount"] if r["amount"] < 0 else None,  # Fineco shows Uscite as negative numbers
            r["short"], r["full"], status, MONEYMAP[r["kind"]],
        ])
    ws.append([])
    ws.append([f"Saldo Finale: {3250 + sum(r['amount'] for r in rows):.2f}".replace(".", ",")])
    autosize(ws)
    wb.save(path)
    return len(rows)


# ── Intesa Sanpaolo ────────────────────────────────────────────────────────────

INTESA_CATEGORIES = {
    "grocery": "Alimentari e supermercati", "fuel": "Carburanti", "transport": "Trasporti",
    "leisure": "Ristoranti e bar", "health": "Farmacie e salute", "other": "Shopping",
    "rent": "Affitto", "subscription": "Abbonamenti e servizi", "utility": "Utenze",
    "transfer": "Giroconti", "salary": "Stipendi e pensioni", "fee": "Commissioni e spese",
    "freelance": "Altre entrate",
}
INTESA_OPERATIONS = {
    "Pagamento carta": "Pagamento tramite POS", "Bonifico SEPA": "Bonifico", "Addebito SDD": "Addebito diretto",
    "Giroconto": "Giroconto", "Commissioni": "Commissioni",
}


def intesa(path: Path, start: date, end: date, seed: int):
    rows = movements(start, end, seed, salary=2180.00, rent=720.00)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Lista Movimenti"
    ws.append(["Lista Movimenti"])
    ws.append(["Intesa Sanpaolo - Conto corrente 1000/00098765"])
    ws.append([f"Intestatario: {HOLDER}"])
    ws.append([f"Periodo: dal {start:%d/%m/%Y} al {end:%d/%m/%Y}"])
    ws.append([])
    ws.append(["Data", "Operazione", "Dettagli", "Conto o carta", "Contabilizzazione", "Categoria ", "Valuta", "Importo"])
    for cell in ws[6]:
        cell.font = Font(bold=True)
    for index, r in enumerate(rows):
        card = r["short"] == "Pagamento carta"
        ws.append([
            r["date"],  # real Excel date cell
            INTESA_OPERATIONS[r["short"]],
            r["full"].replace("PAGAMENTO POS ", ""),
            "Carta XXXX 4321" if card else "Conto 1000/00098765",
            "Non contabilizzato" if index == len(rows) - 1 else "Contabilizzato",
            INTESA_CATEGORIES[r["kind"]],
            "EUR",
            r["amount"],
        ])
        ws.cell(row=ws.max_row, column=1).number_format = "DD/MM/YYYY"
    autosize(ws)
    wb.save(path)
    return len(rows)


def intesa_legacy_html(path: Path, start: date, end: date, seed: int):
    """Old Intesa export: an HTML table saved with the .xls extension, Accrediti/Addebiti columns."""
    rows = movements(start, end, seed, salary=2180.00, rent=720.00)

    def it(amount: float) -> str:
        return f"{abs(amount):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    lines = [
        "<html><head><meta charset='utf-8'></head><body><table border='1'>",
        "<tr><td colspan='6'>Intesa Sanpaolo - Movimenti conto corrente</td></tr>",
        f"<tr><td colspan='6'>Intestatario: {HOLDER}</td></tr>",
        "<tr><th>Data contabile</th><th>Data valuta</th><th>Descrizione</th><th>Accrediti</th><th>Addebiti</th><th>Descrizione estesa</th></tr>",
    ]
    for r in rows:
        credit = it(r["amount"]) if r["amount"] > 0 else ""
        debit = it(r["amount"]) if r["amount"] < 0 else ""
        lines.append(
            f"<tr><td>{r['date']:%d/%m/%Y}</td><td>{r['date']:%d/%m/%Y}</td><td>{INTESA_OPERATIONS[r['short']]}</td>"
            f"<td>{credit}</td><td>{debit}</td><td>{r['full']}</td></tr>"
        )
    lines.append("</table></body></html>")
    path.write_text("\n".join(lines), encoding="utf-8")
    return len(rows)


# ── Generic banks ──────────────────────────────────────────────────────────────

def unicredit_csv(path: Path, start: date, end: date, seed: int):
    """Generic Italian layout: semicolon separated, Italian number format, signed "Importo (EUR)"."""
    rows = movements(start, end, seed, salary=1980.00, rent=650.00)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Data Registrazione", "Data valuta", "Descrizione", "Importo (EUR)"])
        for r in rows:
            amount = f"{r['amount']:.2f}".replace(".", ",")
            writer.writerow([f"{r['date']:%d.%m.%Y}", f"{r['date']:%d.%m.%Y}", r["full"], amount])
    return len(rows)


REVOLUT_MERCHANTS = [("Uber", 8, 25), ("Starbucks", 3, 8), ("Ryanair", 30, 150), ("Booking.com", 60, 300),
                     ("Just Eat", 12, 30), ("Amazon", 10, 80), ("Netflix", 17.99, 17.99)]


def revolut_movements(start: date, end: date, seed: int) -> list[dict]:
    """Revolut account activity: card payments, monthly top-ups, an ATM withdrawal with a fee, a payment
    in USD, one PENDING and one REVERTED card payment (both excluded from the import)."""
    rng = random.Random(seed)
    rows, day = [], start
    while day <= end:
        if rng.random() < 0.35:
            name, low, high = rng.choice(REVOLUT_MERCHANTS)
            rows.append({"type": "CARD_PAYMENT", "date": day, "description": name, "amount": -money(rng, low, high),
                         "fee": 0.0, "currency": "EUR", "state": "COMPLETED"})
        if day.day == 1:
            rows.append({"type": "TOPUP", "date": day, "description": f"Payment from {HOLDER.title()}", "amount": 300.0,
                         "fee": 0.0, "currency": "EUR", "state": "COMPLETED"})
        if day.day == 10:
            rows.append({"type": "ATM", "date": day, "description": "Cash withdrawal at BANCOMAT ROMA", "amount": -100.0,
                         "fee": 1.99, "currency": "EUR", "state": "COMPLETED"})
        if day.day == 12:
            rows.append({"type": "CARD_PAYMENT", "date": day, "description": "Github", "amount": -4.0,
                         "fee": 0.0, "currency": "USD", "state": "COMPLETED"})
        day += timedelta(days=1)
    rows.append({"type": "CARD_PAYMENT", "date": end, "description": "Amazon", "amount": -24.99,
                 "fee": 0.0, "currency": "EUR", "state": "PENDING"})
    rows.append({"type": "CARD_PAYMENT", "date": end - timedelta(days=3), "description": "Zara", "amount": -59.9,
                 "fee": 0.0, "currency": "EUR", "state": "REVERTED"})
    rows.sort(key=lambda r: r["date"])
    return rows


def revolut_csv(path: Path, start: date, end: date, seed: int):
    """Revolut "Account statement" CSV export (English headers, signed Amount, separate Fee, State)."""
    rows = revolut_movements(start, end, seed)
    rng = random.Random(seed)
    balance = 500.0
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Type", "Product", "Started Date", "Completed Date", "Description", "Amount", "Fee",
                         "Currency", "State", "Balance"])
        for r in rows:
            started = f"{r['date']:%Y-%m-%d} 12:{rng.randint(10, 59)}:00"
            completed = started if r["state"] == "COMPLETED" else ""
            if r["state"] == "COMPLETED" and r["currency"] == "EUR":
                balance += r["amount"] - r["fee"]
            writer.writerow([r["type"], "Current", started, completed, r["description"], f"{r['amount']:.2f}",
                             f"{r['fee']:.2f}", r["currency"], r["state"],
                             f"{balance:.2f}" if r["state"] == "COMPLETED" else ""])
    return len(rows)


def n26_csv(path: Path, start: date, end: date, seed: int):
    """N26 CSV export (2023+ layout): Booking Date, Partner Name, Payment Reference, signed Amount (EUR)."""
    rows = movements(start, end, seed, salary=2200.00, rent=750.00)
    types = {"Pagamento carta": "Presentment", "Bonifico SEPA": "Outgoing Transfer", "Addebito SDD": "Direct Debit",
             "Giroconto": "Outgoing Transfer", "Commissioni": "Fee"}
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(["Booking Date", "Value Date", "Partner Name", "Partner Iban", "Type", "Payment Reference",
                         "Account Name", "Amount (EUR)", "Original Amount", "Original Currency", "Exchange Rate"])
        for r in rows:
            kind = "Income" if r["amount"] > 0 else types[r["short"]]
            partner = r["full"].replace("PAGAMENTO POS ", "")
            iban = "IT60X0542811101000000123456" if r["short"] != "Pagamento carta" else ""
            writer.writerow([f"{r['date']:%Y-%m-%d}", f"{r['date']:%Y-%m-%d}", partner, iban, kind,
                             r["short"] if r["short"] != "Pagamento carta" else "", "Main Account",
                             f"{r['amount']:.2f}", "", "", ""])
    return len(rows)


def bper_xlsx(path: Path, start: date, end: date, seed: int):
    """BPER Banca movements export: signed Importo with the ABI transaction code ("Causale ABI")."""
    rows = movements(start, end, seed, salary=2010.00, rent=630.00)
    abi = {"Pagamento carta": "43 - PAGAMENTO POS", "Bonifico SEPA": "48 - BONIFICO", "Addebito SDD": "50 - ADDEBITO SDD",
           "Giroconto": "34 - GIROCONTO", "Commissioni": "66 - COMMISSIONI"}
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Movimenti"
    ws.append(["BPER Banca - Movimenti conto corrente"])
    ws.append([f"Intestatario: {HOLDER}", "", "Conto: 000012345678"])
    ws.append([f"Periodo dal {start:%d/%m/%Y} al {end:%d/%m/%Y}"])
    ws.append([])
    ws.append(["Data contabile", "Data valuta", "Causale ABI", "Descrizione", "Importo", "Divisa"])
    for r in rows:
        ws.append([r["date"], r["date"], abi[r["short"]], r["full"], r["amount"], "EUR"])
        for col in (1, 2):
            ws.cell(row=ws.max_row, column=col).number_format = "DD/MM/YYYY"
    autosize(ws)
    wb.save(path)
    return len(rows)


def bancoposta_xlsx(path: Path, start: date, end: date, seed: int):
    """Poste Italiane BancoPosta "Lista movimenti": separate Addebiti/Accrediti (euro), "Descrizione operazioni"."""
    rows = movements(start, end, seed, salary=1820.00, rent=560.00)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Lista movimenti"
    ws.append(["Poste Italiane - BancoPosta"])
    ws.append([f"Conto BancoPosta n. 001234567890 intestato a {HOLDER}"])
    ws.append([f"Movimenti dal {start:%d/%m/%Y} al {end:%d/%m/%Y}"])
    ws.append([])
    ws.append(["Data Contabile", "Data Valuta", "Addebiti (euro)", "Accrediti (euro)", "Descrizione operazioni"])
    for r in rows:
        day = f"{r['date']:%d/%m/%Y}"
        debit = _it(r["amount"]) if r["amount"] < 0 else ""
        credit = _it(r["amount"]) if r["amount"] > 0 else ""
        ws.append([day, day, debit, credit, f"{r['short'].upper()} {r['full']}"])
    autosize(ws)
    wb.save(path)
    return len(rows)


def ing_xlsx(path: Path, start: date, end: date, seed: int):
    """ING (Conto Corrente Arancio) movements: unsigned Uscite/Entrate columns, Causale + Descrizione operazione."""
    rows = movements(start, end, seed, salary=2280.00, rent=690.00)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Movimenti"
    ws.append(["ING - Conto Corrente Arancio"])
    ws.append([f"Intestatario: {HOLDER}"])
    ws.append([])
    ws.append(["Data contabile", "Data valuta", "Uscite", "Entrate", "Causale", "Descrizione operazione"])
    for r in rows:
        day = f"{r['date']:%d/%m/%Y}"
        ws.append([day, day, -r["amount"] if r["amount"] < 0 else None, r["amount"] if r["amount"] > 0 else None,
                   r["short"].upper(), r["full"]])
    autosize(ws)
    wb.save(path)
    return len(rows)


def legacy_xls(path: Path, start: date, end: date, seed: int):
    """Binary .xls (Excel 97-2003) with a generic layout, as some smaller banks still export."""
    import xlwt
    rows = movements(start, end, seed, salary=2050.00, rent=600.00)
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Movimenti")
    date_style = xlwt.easyxf(num_format_str="DD/MM/YYYY")
    ws.write(0, 0, f"Estratto conto - {HOLDER}")
    for col, title in enumerate(["Data operazione", "Descrizione", "Dare", "Avere"]):
        ws.write(2, col, title)
    for index, r in enumerate(rows, start=3):
        ws.write(index, 0, r["date"], date_style)
        ws.write(index, 1, r["full"])
        if r["amount"] < 0:
            ws.write(index, 2, -r["amount"])
        else:
            ws.write(index, 3, r["amount"])
    wb.save(str(path))
    return len(rows)


def _it(amount: float) -> str:
    """Italian number format without sign: 1234.5 → '1.234,50'."""
    return f"{abs(amount):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ── PDF / TXT / Word ───────────────────────────────────────────────────────────

def fineco_pdf(path: Path, start: date, end: date, seed: int):
    """Text-layout PDF (no table borders) like Fineco's "Estratto conto": Entrate/Uscite columns,
    long descriptions wrapping onto a second line, header repeated on every page."""
    from fpdf import FPDF
    rows = movements(start, end, seed, salary=2450.00, rent=850.00)
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(False)
    columns = [("Data Operazione", 10, 26), ("Data Valuta", 37, 22), ("Descrizione", 62, 88),
               ("Entrate", 152, 22), ("Uscite", 176, 22)]

    def header():
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_xy(10, 12)
        pdf.cell(0, 6, "FinecoBank S.p.A. - Estratto conto corrente")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_xy(10, 19)
        pdf.cell(0, 5, f"Intestatario: {HOLDER}   Conto: 0012345678   Periodo: {start:%d/%m/%Y} - {end:%d/%m/%Y}")
        pdf.set_font("Helvetica", "B", 8)
        for title, x, width in columns:
            pdf.set_xy(x, 30)
            pdf.cell(width, 5, title, align="R" if title in ("Entrate", "Uscite") else "L")
        pdf.line(10, 36, 200, 36)
        pdf.set_font("Helvetica", "", 8)
        return 39

    y = header()
    for r in rows:
        description = f"{r['short']} - {r['full']}"
        lines = textwrap.wrap(description, 52)
        if y + 5 * len(lines) > 280:
            pdf.set_xy(10, 287)
            pdf.cell(0, 4, f"Pagina {pdf.page_no()}", align="C")
            y = header()
        pdf.set_xy(10, y)
        pdf.cell(26, 4, f"{r['date']:%d/%m/%Y}")
        pdf.set_xy(37, y)
        pdf.cell(22, 4, f"{r['date']:%d/%m/%Y}")
        pdf.set_xy(62, y)
        pdf.cell(88, 4, lines[0])
        amount_x = 152 if r["amount"] > 0 else 176
        pdf.set_xy(amount_x, y)
        pdf.cell(22, 4, _it(r["amount"]), align="R")
        for extra in lines[1:]:
            y += 4
            pdf.set_xy(62, y)
            pdf.cell(88, 4, extra)
        y += 6
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(62, y + 2)
    pdf.cell(88, 4, "SALDO FINALE")
    pdf.set_xy(152, y + 2)
    pdf.cell(22, 4, _it(3250 + sum(r["amount"] for r in rows)), align="R")
    pdf.output(str(path))
    return len(rows)


def intesa_pdf(path: Path, start: date, end: date, seed: int):
    """Bordered-table PDF like Intesa Sanpaolo's "Lista movimenti" (signed Importo column)."""
    from fpdf import FPDF
    rows = movements(start, end, seed, salary=2180.00, rent=720.00)
    pdf = FPDF(format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "Intesa Sanpaolo - Lista movimenti", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, f"Conto corrente 1000/00098765 - Intestatario: {HOLDER}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 8)
    with pdf.table(col_widths=(20, 32, 88, 25), text_align=("LEFT", "LEFT", "LEFT", "RIGHT")) as table:
        table.row(["Data", "Operazione", "Dettagli", "Importo"])
        for r in rows:
            sign = "-" if r["amount"] < 0 else ""
            table.row([f"{r['date']:%d/%m/%Y}", INTESA_OPERATIONS[r["short"]],
                       r["full"].replace("PAGAMENTO POS ", ""), f"{sign}{_it(r['amount'])}"])
    pdf.output(str(path))
    return len(rows)


def generic_txt(path: Path, start: date, end: date, seed: int):
    """Fixed-width plain-text statement (as printed by some home-banking "Stampa" functions)."""
    rows = movements(start, end, seed, salary=1890.00, rent=590.00)
    lines = [
        "BANCA POPOLARE DEMO - ESTRATTO CONTO",
        f"Intestatario: {HOLDER}",
        f"Periodo: {start:%d/%m/%Y} - {end:%d/%m/%Y}",
        "",
        f"{'Data':<12}{'Valuta':<12}{'Descrizione':<52}{'Dare':>12}{'Avere':>12}",
        "-" * 100,
    ]
    for r in rows:
        debit = _it(r["amount"]) if r["amount"] < 0 else ""
        credit = _it(r["amount"]) if r["amount"] > 0 else ""
        lines.append(f"{r['date']:%d/%m/%Y}  {r['date']:%d/%m/%Y}  {r['full'][:50]:<52}{debit:>12}{credit:>12}")
    lines += ["-" * 100, f"{'':<24}{'SALDO FINALE':<52}{'':>12}{_it(1000 + sum(r['amount'] for r in rows)):>12}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(rows)


def generic_docx(path: Path, start: date, end: date, seed: int):
    """Word document with a movements table (e.g. a statement pasted into Word by an accountant)."""
    import docx
    rows = movements(start, end, seed, salary=2300.00, rent=780.00)
    document = docx.Document()
    document.add_heading("Estratto conto - Banca Demo", level=1)
    document.add_paragraph(f"Intestatario: {HOLDER}")
    document.add_paragraph(f"Periodo: {start:%d/%m/%Y} - {end:%d/%m/%Y}")
    table = document.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    for cell, title in zip(table.rows[0].cells, ["Data", "Descrizione", "Categoria", "Importo"]):
        cell.text = title
    for r in rows:
        cells = table.add_row().cells
        cells[0].text = f"{r['date']:%d/%m/%Y}"
        cells[1].text = r["full"]
        cells[2].text = ""
        cells[3].text = ("-" if r["amount"] < 0 else "") + _it(r["amount"])
    document.add_paragraph("Documento generato per test - dati fittizi.")
    document.save(str(path))
    return len(rows)


def _cfb(streams: dict[str, bytes]) -> bytes:
    """Minimal OLE2 compound file (version 3, 512-byte sectors, one FAT sector) holding a few streams.
    Streams are padded to 4096 bytes so they live in regular sectors (no mini stream needed)."""
    import struct
    free, end, fat_sector = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD
    names = list(streams)
    data = {n: streams[n].ljust(max(4096, -(-len(streams[n]) // 512) * 512), b"\0") for n in names}
    fat = [fat_sector, end]                      # sector 0: FAT, sector 1: directory
    starts = {}
    for name in names:
        starts[name] = len(fat)
        count = len(data[name]) // 512
        fat += [len(fat) + i + 1 for i in range(count - 1)] + [end]
    assert len(fat) <= 128
    fat += [free] * (128 - len(fat))

    def entry(name: str, kind: int, left: int, right: int, child: int, start: int, size: int) -> bytes:
        encoded = (name + "\0").encode("utf-16-le")
        return (encoded.ljust(64, b"\0") + struct.pack("<HBB3I", len(encoded), kind, 1, left, right, child)
                + b"\0" * 36 + struct.pack("<IQ", start, size))

    # Directory tree ordered by (name length, name): the root points to the largest name, each entry's
    # left sibling is the next smaller one (a valid, if unbalanced, binary search tree)
    ordered = sorted(names, key=lambda n: (len(n), n.upper()))
    ids = {name: index + 1 for index, name in enumerate(names)}
    directory = entry("Root Entry", 5, free, free, ids[ordered[-1]], end, 0)
    for name in names:
        position = ordered.index(name)
        left = ids[ordered[position - 1]] if position > 0 else free
        directory += entry(name, 2, left, free, free, starts[name], len(data[name]))
    assert len(directory) <= 512
    directory = directory.ljust(512, b"\0")

    header = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 16
              + struct.pack("<HHHHH", 0x3E, 3, 0xFFFE, 9, 6) + b"\0" * 6
              + struct.pack("<IIIIIIIII", 0, 1, 1, 0, 4096, end, 0, end, 0)
              + struct.pack("<I", 0) + struct.pack("<I", free) * 108)
    return header + struct.pack("<128I", *fat) + directory + b"".join(data[n] for n in names)


def generic_doc(path: Path, start: date, end: date, seed: int):
    """Word 97-2003 binary (.doc) with a movements table, written by hand: an OLE2 container with the
    "WordDocument" stream (FIB + text) and the "1Table" stream (piece table). The preamble is stored as
    8-bit text and the table as UTF-16, the two encodings Word uses."""
    import struct
    rows = movements(start, end, seed, salary=2150.00, rent=670.00)
    preamble = f"Estratto conto - Banca Demo\rIntestatario: {HOLDER}\rPeriodo: {start:%d/%m/%Y} - {end:%d/%m/%Y}\r"
    cells = ["Data", "Descrizione", "Importo"]
    table = "".join(c + "\x07" for c in cells) + "\x07"
    for r in rows:
        cells = [f"{r['date']:%d/%m/%Y}", r["full"], ("-" if r["amount"] < 0 else "") + _it(r["amount"])]
        table += "".join(c + "\x07" for c in cells) + "\x07"
    table += "Documento generato per test - dati fittizi.\r"

    first = preamble.encode("cp1252")
    second = table.encode("utf-16-le")
    ccp = len(preamble) + len(table)
    text_at = 0x800
    fib = bytearray(text_at)
    struct.pack_into("<HHH", fib, 0, 0xA5EC, 0x00C1, 0x0409)       # wIdent, nFib (Word 97), lid
    struct.pack_into("<H", fib, 0x0A, 0x0200)                       # fWhichTblStm: the table stream is "1Table"
    struct.pack_into("<H", fib, 0x20, 14)                           # csw
    struct.pack_into("<H", fib, 0x3E, 22)                           # cslw
    struct.pack_into("<i", fib, 0x4C, ccp)                          # ccpText
    struct.pack_into("<H", fib, 0x98, 0x5D)                         # cbRgFcLcb (Word 97)
    second_at = text_at + len(first)
    second_at += second_at % 2
    word = bytearray(fib) + first + b"\0" * (second_at - text_at - len(first)) + second

    cps = struct.pack("<3I", 0, len(preamble), ccp)
    pieces = (struct.pack("<HIH", 0, (text_at * 2) | 0x40000000, 0)  # compressed: fc is doubled
              + struct.pack("<HIH", 0, second_at, 0))
    plc = cps + pieces
    clx = b"\x02" + struct.pack("<I", len(plc)) + plc
    struct.pack_into("<II", word, 0x9A + 33 * 8, 0, len(clx))      # fcClx, lcbClx
    path.write_bytes(_cfb({"WordDocument": bytes(word), "1Table": clx}))
    return len(rows)


def generic_ods(path: Path, start: date, end: date, seed: int):
    """LibreOffice Calc spreadsheet (.ods), written by hand: an .ods is a zip with an XML sheet."""
    import zipfile
    from xml.sax.saxutils import escape
    rows = movements(start, end, seed, salary=2100.00, rent=700.00)

    def text_cell(value: str) -> str:
        return f'<table:table-cell office:value-type="string"><text:p>{escape(value)}</text:p></table:table-cell>'

    xml_rows = [
        f"<table:table-row>{text_cell('Estratto conto ' + HOLDER)}</table:table-row>",
        "<table:table-row>" + "".join(text_cell(h) for h in ["Data", "Descrizione", "Entrate", "Uscite"]) + "</table:table-row>",
    ]
    for r in rows:
        amount = f'<table:table-cell office:value-type="float" office:value="{abs(r["amount"]):.2f}"><text:p>{_it(r["amount"])}</text:p></table:table-cell>'
        empty = "<table:table-cell/>"
        xml_rows.append(
            "<table:table-row>"
            f'<table:table-cell office:value-type="date" office:date-value="{r["date"].isoformat()}"><text:p>{r["date"]:%d/%m/%Y}</text:p></table:table-cell>'
            + text_cell(r["full"])
            + (amount + empty if r["amount"] > 0 else empty + amount)
            + "</table:table-row>"
        )
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2">'
        '<office:body><office:spreadsheet><table:table table:name="Movimenti">'
        + "".join(xml_rows)
        + "</table:table></office:spreadsheet></office:body></office:document-content>"
    )
    manifest = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">'
        '<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.spreadsheet"/>'
        '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
        "</manifest:manifest>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.spreadsheet")
        archive.writestr("META-INF/manifest.xml", manifest, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("content.xml", content, compress_type=zipfile.ZIP_DEFLATED)
    return len(rows)


def generic_rtf(path: Path, start: date, end: date, seed: int):
    """Rich Text Format document with tab-separated columns (e.g. saved from WordPad)."""
    rows = movements(start, end, seed, salary=1950.00, rent=620.00)

    def rtf(text: str) -> str:
        return "".join(c if ord(c) < 128 else f"\\'{ord(c):02x}" for c in text)

    body = [r"{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}\f0\fs20",
            rf"\b Estratto conto - Banca Demo\b0\par Intestatario: {HOLDER}\par\par",
            r"Data\tab Descrizione\tab Importo\par"]
    for r in rows:
        sign = "-" if r["amount"] < 0 else ""
        body.append(rf"{r['date']:%d/%m/%Y}\tab {rtf(r['full'])}\tab {sign}{_it(r['amount'])}\par")
    body.append("}")
    path.write_text("\n".join(body), encoding="ascii")
    return len(rows)


# ── Scans and photos (for the AI reader) ────────────────────────────────────────

def _render_pages(pdf_path: Path, dpi: int):
    import pdfplumber
    with pdfplumber.open(str(pdf_path)) as pdf:
        return [page.to_image(resolution=dpi).original.convert("L") for page in pdf.pages]


def scanned_pdf(path: Path, source: Path):
    """Image-only PDF (no text layer), slightly rotated and grey like a real scan."""
    from PIL import ImageFilter
    pages = [
        img.rotate(0.6, expand=True, fillcolor=255).filter(ImageFilter.GaussianBlur(0.4))
        for img in _render_pages(source, dpi=110)
    ]
    pages[0].save(str(path), "PDF", resolution=110, save_all=True, append_images=pages[1:])
    return len(pages)


def statement_photo(path: Path, source: Path):
    """JPEG "phone photo" of the first page of a statement."""
    page = _render_pages(source, dpi=100)[0].rotate(-1.5, expand=True, fillcolor=235)
    page.convert("RGB").save(str(path), "JPEG", quality=70)
    return 1


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    files = [
        ("fineco_2026-06_2026-07.xlsx", fineco, (date(2026, 6, 1), date(2026, 7, 31), 11)),
        # Overlaps July with the file above → demonstrates duplicate detection
        ("fineco_2026-07_2026-09.xlsx", fineco, (date(2026, 7, 1), date(2026, 9, 24), 11)),
        ("intesa_sanpaolo_2026-04_2026-09.xlsx", intesa, (date(2026, 4, 1), date(2026, 9, 24), 22)),
        ("intesa_sanpaolo_legacy_2026-03.xls", intesa_legacy_html, (date(2026, 3, 1), date(2026, 3, 31), 33)),
        ("unicredit_2026-08_2026-09.csv", unicredit_csv, (date(2026, 8, 1), date(2026, 9, 24), 44)),
        ("revolut_2026-09.csv", revolut_csv, (date(2026, 9, 1), date(2026, 9, 24), 55)),
        ("n26_2026-08.csv", n26_csv, (date(2026, 8, 1), date(2026, 8, 31), 144)),
        ("bper_2026-07.xlsx", bper_xlsx, (date(2026, 7, 1), date(2026, 7, 31), 155)),
        ("bancoposta_2026-06.xlsx", bancoposta_xlsx, (date(2026, 6, 1), date(2026, 6, 30), 166)),
        ("ing_2026-05.xlsx", ing_xlsx, (date(2026, 5, 1), date(2026, 5, 31), 177)),
        ("banca_generica_2026-02.xls", legacy_xls, (date(2026, 2, 1), date(2026, 2, 28), 66)),
        ("fineco_estratto_conto_2026-07_2026-08.pdf", fineco_pdf, (date(2026, 7, 1), date(2026, 8, 31), 77)),
        ("intesa_sanpaolo_lista_movimenti_2026-09.pdf", intesa_pdf, (date(2026, 9, 1), date(2026, 9, 24), 88)),
        ("banca_popolare_2026-05.txt", generic_txt, (date(2026, 5, 1), date(2026, 5, 31), 99)),
        ("estratto_conto_word_2026-01.docx", generic_docx, (date(2026, 1, 1), date(2026, 1, 31), 111)),
        ("estratto_conto_word97_2025-10.doc", generic_doc, (date(2025, 10, 1), date(2025, 10, 31), 188)),
        ("estratto_conto_libreoffice_2025-12.ods", generic_ods, (date(2025, 12, 1), date(2025, 12, 31), 122)),
        ("estratto_conto_2025-11.rtf", generic_rtf, (date(2025, 11, 1), date(2025, 11, 30), 133)),
    ]
    files += [
        # Built from the PDFs above: need fpdf2 only through them
        ("SCANSIONE_fineco_2026-07_2026-08.pdf", lambda p, *_: scanned_pdf(p, OUT / "fineco_estratto_conto_2026-07_2026-08.pdf"), (None, None, None)),
        ("FOTO_estratto_conto_intesa_2026-09.jpg", lambda p, *_: statement_photo(p, OUT / "intesa_sanpaolo_lista_movimenti_2026-09.pdf"), (None, None, None)),
    ]
    only = sys.argv[1:]  # optional filenames: regenerate just these
    for name, builder, (start, end, seed) in files:
        if only and name not in only:
            continue
        # The Fineco files share a seed so the overlapping July movements are identical
        try:
            count = builder(OUT / name, start, end, seed)
        except ImportError as exc:
            print(f"skip  {name}: {exc}")
            continue
        unit = "pagine" if name.startswith(("SCANSIONE", "FOTO")) else "movimenti"
        print(f"wrote {name} ({count} {unit})")


if __name__ == "__main__":
    main()
