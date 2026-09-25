"""Builders for realistic bank-statement files used by the import tests."""
import io
from datetime import datetime

import openpyxl


def xlsx(rows: list[list]) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def fineco_xlsx() -> bytes:
    """Fineco "Movimenti" export: preamble, then Entrate/Uscite columns (uscite negative), Moneymap category."""
    return xlsx([
        ["Conto Corrente: 1234567"],
        ["Intestazione Conto Corrente: MARIO ROSSI"],
        ["Periodo Dal: 01/06/2026 Al: 30/06/2026"],
        ["Saldo Iniziale: 1.000,00"],
        [],
        ["Data_Operazione", "Data_Valuta", "Entrate", "Uscite", "Descrizione", "Descrizione_Completa", "Stato", "Moneymap"],
        ["27/06/2026", "27/06/2026", 2800, None, "Bonifico SEPA Italia", "Bonifico da ACME SPA per STIPENDIO GIUGNO", "Contabilizzato", "Stipendio"],
        ["03/06/2026", "03/06/2026", None, -87.5, "Pagamento Visa Debit", "Pagamento Visa Debit presso ESSELUNGA MILANO", "Contabilizzato", "Spesa"],
        ["05/06/2026", "05/06/2026", None, -17.99, "Pagamento Visa Debit", "NETFLIX.COM Amsterdam", "Contabilizzato", "Intrattenimento"],
        ["05/06/2026", "05/06/2026", None, -17.99, "Pagamento Visa Debit", "NETFLIX.COM Amsterdam", "Contabilizzato", "Intrattenimento"],
        ["10/06/2026", "10/06/2026", None, -40, "Giroconto", "Giroconto verso conto deposito", "Contabilizzato", "Trasferimenti"],
        ["12/06/2026", "12/06/2026", None, -12, "Pagamento Visa Debit", "PALESTRA FIT", "Contabilizzato", "Sport"],
        ["30/06/2026", "30/06/2026", None, -25, "Pagamento Visa Debit", "AMAZON EU", "Autorizzato", "Shopping"],
        [],
        ["Saldo Finale: 3.599,52"],
    ])


def intesa_xlsx() -> bytes:
    """Intesa Sanpaolo "Lista movimenti" export: signed Importo, own Categoria, Contabilizzazione status."""
    return xlsx([
        ["Lista Movimenti"],
        ["Intesa Sanpaolo - Conto corrente 1000/00012345"],
        ["Periodo: dal 01/07/2026 al 31/07/2026"],
        [],
        ["Data", "Operazione", "Dettagli", "Conto o carta", "Contabilizzazione", "Categoria ", "Valuta", "Importo"],
        [datetime(2026, 7, 1), "Accredito stipendio", "ACME SPA emolumenti luglio", "Conto 12345", "Contabilizzato", "Stipendi e pensioni", "EUR", 2900.0],
        [datetime(2026, 7, 2), "Pagamento POS", "CONAD CITY ROMA", "Carta 4321", "Contabilizzato", "Alimentari e supermercati", "EUR", -54.3],
        [datetime(2026, 7, 4), "Addebito diretto", "ENEL ENERGIA bolletta luce", "Conto 12345", "Contabilizzato", "Utenze", "EUR", -71.2],
        [datetime(2026, 7, 8), "Pagamento POS", "LIBRERIA FELTRINELLI", "Carta 4321", "Contabilizzato", "Tempo libero", "EUR", -23.0],
        [datetime(2026, 7, 9), "Pagamento POS", "BAR CENTRALE", "Carta 4321", "Non contabilizzato", "Ristoranti e bar", "EUR", -3.5],
    ])


def intesa_legacy_html() -> bytes:
    """Older Intesa export: an HTML table saved with an .xls extension, Accrediti/Addebiti columns."""
    return """<html><body><table>
      <tr><td>Intesa Sanpaolo</td></tr>
      <tr><th>Data contabile</th><th>Data valuta</th><th>Descrizione</th><th>Accrediti</th><th>Addebiti</th><th>Descrizione estesa</th></tr>
      <tr><td>15/05/2026</td><td>15/05/2026</td><td>Pagamento POS</td><td></td><td>32,40</td><td>FARMACIA COMUNALE</td></tr>
      <tr><td>20/05/2026</td><td>20/05/2026</td><td>Bonifico ricevuto</td><td>1.250,00</td><td></td><td>RIMBORSO SPESE</td></tr>
    </table></body></html>""".encode("utf-8")


def generic_csv() -> bytes:
    """Revolut-style CSV (English headers, signed Amount)."""
    return (
        "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
        "CARD_PAYMENT,Current,2026-08-01 10:00:00,2026-08-02 09:00:00,Uber,-14.20,0.00,EUR,COMPLETED,985.80\n"
        "TOPUP,Current,2026-08-03 11:00:00,2026-08-03 11:00:00,Payment from Mario Rossi,200.00,0.00,EUR,COMPLETED,1185.80\n"
    ).encode()
