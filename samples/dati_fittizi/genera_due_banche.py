"""
Two FAKE bank statements of the same household, from January 2022 to September 2026, that exchange transfers:
every giroconto is in both files, on the same day, for the same amount (out of one account, into the other).

    python samples/dati_fittizi/genera_due_banche.py      # writes samples/dati_fittizi/due_banche/

- UniCredit (CSV): the everyday account of a couple. Both salaries, rent then mortgage, bills, groceries, fuel, restaurants,
  Christmas presents, random purchases, the broken washing machine, the wedding gifts, the 730 refunds.
- Fineco (Excel): the savings and travel account. The monthly saving from UniCredit, summer and winter trips,
  the wedding, online subscriptions, quarterly interest and stamp duty; it sends money back for the house deposit,
  the furniture, the dentist.

No database, no app: plain files to load from Esporta → Importa estratto conto. The output is deterministic
(fixed random seed): running it again gives the same movements. Everything is invented.
"""
from __future__ import annotations

import calendar
import csv
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

OUT = Path(__file__).resolve().parent / "due_banche"
START, END = date(2022, 1, 1), date(2026, 9, 30)
SEED = 2022
HOLDER = "MARIO ROSSI"
OPENING = {"unicredit": Decimal("4200.00"), "fineco": Decimal("22000.00")}
UNICREDIT_FILE = "unicredit_conto_corrente_2022-01_2026-09.csv"
FINECO_FILE = "fineco_conto_risparmio_2022-01_2026-09.xlsx"
CENT = Decimal("0.01")


@dataclass
class Move:
    account: str          # "unicredit" | "fineco"
    day: date
    amount: Decimal       # signed: negative goes out of the account
    short: str            # the bank's kind of operation (Fineco "Descrizione", UniCredit "Causale")
    full: str             # what the operation was (merchant, payee, reason)
    kind: str             # for Fineco's Moneymap column and the README's summary
    transfer: bool = False


def euro(value: float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, ROUND_HALF_EVEN)


def months():
    year, month = START.year, START.month
    while date(year, month, 1) <= END:
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def day_in(year: int, month: int, day: int) -> date:
    """The day of the month, or the last one when the month is shorter."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


class Household:
    def __init__(self, seed: int = SEED):
        self.rng = random.Random(seed)
        self.moves: list[Move] = []

    # ── helpers ────────────────────────────────────────────────────────────────

    def add(self, account: str, day: date, amount, short: str, full: str, kind: str, transfer: bool = False):
        if START <= day <= END:
            self.moves.append(Move(account, day, euro(amount), short, full, kind, transfer))

    def spend(self, account: str, day: date, low: float, high: float, short: str, full: str, kind: str):
        self.add(account, day, -self.rng.uniform(low, high), short, full, kind)

    def transfer(self, day: date, amount, source: str, reason: str = ""):
        """A giroconto: the same day and amount, out of `source` and into the other account."""
        target = "fineco" if source == "unicredit" else "unicredit"
        names = {"unicredit": "UniCredit c/c 000102345678", "fineco": "Fineco c/c 0012345678"}
        suffix = f" - {reason}" if reason else ""
        self.add(source, day, -amount, "Giroconto", f"Giroconto verso {names[target]}{suffix}", "transfer", True)
        self.add(target, day, amount, "Giroconto", f"Giroconto da {names[source]}{suffix}", "transfer", True)

    def random_day(self, year: int, month: int, first: int = 1, last: int = 31) -> date:
        last = min(last, calendar.monthrange(year, month)[1])
        return date(year, month, self.rng.randint(first, last))

    # ── income ─────────────────────────────────────────────────────────────────

    SALARY = {2022: 2050, 2023: 2150, 2024: 2260, 2025: 2380, 2026: 2450}
    PARTNER = {2022: 1150, 2023: 1180, 2024: 1240, 2025: 1280, 2026: 1320}  # part-time

    def income(self, year: int, month: int):
        salary = self.SALARY[year]
        self.add("unicredit", day_in(year, month, 27), salary, "Accredito stipendio",
                 f"Stipendio {month:02d}/{year} ACME S.p.A.", "salary")
        partner = self.PARTNER[year]
        self.add("unicredit", day_in(year, month, 10), partner, "Accredito stipendio",
                 f"Stipendio {month:02d}/{year} STUDIO MEDICO SALUS - Laura Bianchi", "salary")
        if month == 12:
            self.add("unicredit", date(year, 12, 15), partner, "Accredito stipendio",
                     f"Tredicesima {year} STUDIO MEDICO SALUS - Laura Bianchi", "salary")
            self.add("unicredit", date(year, 12, 18), salary * 0.92, "Accredito stipendio",
                     f"Tredicesima {year} ACME S.p.A.", "salary")
        if month == 7 and year >= 2024:
            self.add("unicredit", date(year, 7, 27), self.rng.choice([800, 950, 1100]), "Accredito stipendio",
                     f"Premio di produzione {year} ACME S.p.A.", "salary")
        if month == 7:  # the 730 refund comes with July's salary
            self.add("unicredit", date(year, 7, 27), self.rng.uniform(140, 780), "Accredito stipendio",
                     f"Rimborso 730/{year} ACME S.p.A.", "tax")
        if self.rng.random() < 0.18:
            self.add("unicredit", self.random_day(year, month), self.rng.choice([25, 40, 60, 80, 120, 180, 250]),
                     "Bonifico in entrata", "Bonifico da privato - vendita usato Subito.it", "other_income")
        if self.rng.random() < 0.07:
            self.add("unicredit", self.random_day(year, month, 10, 25), self.rng.choice([350, 600, 900]),
                     "Bonifico in entrata", "Bonifico da STUDIO BIANCHI SRL - consulenza occasionale", "other_income")
        if month in (3, 6, 9, 12):  # the savings account pays interest and the stamp duty every quarter
            last = day_in(year, month, 31)
            rate = {2022: 0.0005, 2023: 0.012, 2024: 0.02, 2025: 0.015, 2026: 0.012}[year]
            balance = float(self.balance("fineco", last))
            if balance > 0:
                self.add("fineco", last, balance * rate / 4 * 0.74, "Interessi", "Interessi creditori netti trimestre",
                         "interest")
            self.add("fineco", last, -min(max(balance * 0.002 / 4, 8.5), 1250), "Imposta di bollo",
                     "Imposta di bollo conto deposito", "tax")

    # ── fixed: home, bills, subscriptions ──────────────────────────────────────

    def home(self, year: int, month: int):
        if (year, month) < (2023, 7):
            rent = 650 if year == 2022 else 680  # ISTAT increase from January 2023
            self.add("unicredit", date(year, month, 1), -rent, "Bonifico SEPA",
                     f"Bonifico a IMMOBILIARE CASA BELLA SRL per AFFITTO {month:02d}/{year}", "rent")
        else:
            self.add("unicredit", date(year, month, 5), -784.32, "Addebito SDD",
                     "Rata mutuo prima casa n. 7788123 UniCredit", "mortgage")
            if month in (1, 4, 7, 10):
                self.add("unicredit", date(year, month, 10), -self.rng.choice([230, 245, 260]), "Bonifico SEPA",
                         f"Bonifico a CONDOMINIO VIA VERDI 12 rata {(month - 1) // 3 + 1}/{year}", "condo")

    def bills(self, year: int, month: int):
        winter = month in (11, 12, 1, 2, 3)
        energy = self.rng.uniform(55, 80) + (self.rng.uniform(70, 140) if winter else 0)
        if year == 2022 and month >= 9 or year == 2023 and month <= 3:
            energy *= 1.6  # the 2022 energy crisis
        self.add("unicredit", day_in(year, month, 12), -energy, "Addebito SDD",
                 "Enel Energia bolletta luce e gas", "utilities")
        if month % 2 == 0:
            self.spend("unicredit", day_in(year, month, 20), 32, 58, "Addebito SDD", "Acquedotto MM SpA bolletta acqua",
                       "utilities")
        self.add("unicredit", day_in(year, month, 8), -(29.90 if year < 2024 else 32.90), "Addebito SDD",
                 "TIM fibra casa", "utilities")
        self.add("unicredit", day_in(year, month, 18), -9.99, "Addebito SDD", "Iliad ricarica mobile", "utilities")
        self.add("unicredit", day_in(year, month, 6), -(12.99 if year < 2024 else 15.99), "Pagamento carta",
                 "NETFLIX.COM AMSTERDAM", "subscription")
        self.add("fineco", day_in(year, month, 14), -(10.99 if year < 2025 else 11.99), "Pagamento carta",
                 "SPOTIFY AB STOCKHOLM", "subscription")
        if month != 8:
            self.add("unicredit", day_in(year, month, 3), -(39.90 if year < 2025 else 44.90), "Addebito SDD",
                     "Palestra FitActive abbonamento", "sport")
        # yearly and half-yearly: car insurance, car tax, waste tax, tyres
        if month == 3:
            self.add("unicredit", date(year, 3, 15), -(520 + 30 * (year - 2022)), "Addebito SDD",
                     "UnipolSai polizza RC auto annuale", "insurance")
        if month == 5:
            self.add("unicredit", date(year, 5, 20), -231.40, "Pagamento PagoPA", "Bollo auto Regione Lombardia", "tax")
        if month in (5, 11):
            self.add("unicredit", day_in(year, month, 30), -self.rng.choice([138, 142, 151]), "Pagamento F24",
                     "F24 TARI Comune di Milano", "tax")
        if month in (4, 11):
            self.spend("unicredit", self.random_day(year, month, 5, 25), 55, 85, "Pagamento POS",
                       "PAGAMENTO POS GOMMISTA FERRARI cambio gomme", "car")

    # ── semi-fixed: groceries, fuel, eating out ────────────────────────────────

    GROCERIES = [("ESSELUNGA MILANO", 35, 140), ("COOP LOMBARDIA", 25, 110), ("LIDL ITALIA", 18, 80),
                 ("CONAD CITY", 8, 45)]
    FUEL = [("ENI STATION 1043", 45, 75), ("Q8 VIA EMILIA", 40, 70), ("IP VIALE FORLANINI", 40, 72)]
    LEISURE = [("RISTORANTE DA LUIGI", 35, 95), ("PIZZERIA NAPOLI", 20, 48), ("BAR CENTRALE", 2, 9),
               ("DELIVEROO ITALY", 18, 40), ("CINEMA ANTEO", 9, 22), ("SUSHI KO", 30, 70)]

    def everyday(self, year: int, month: int):
        away = {7: range(10, 25), 8: range(5, 22)}.get(month, ())  # on holiday: no groceries at home
        for _ in range(self.rng.randint(6, 9)):
            day = self.random_day(year, month)
            if day.day in away:
                continue
            name, low, high = self.rng.choice(self.GROCERIES)
            self.spend("unicredit", day, low, high, "Pagamento POS", f"PAGAMENTO POS {name}", "groceries")
        for _ in range(self.rng.randint(2, 3)):
            name, low, high = self.rng.choice(self.FUEL)
            self.spend("unicredit", self.random_day(year, month), low, high, "Pagamento POS",
                       f"PAGAMENTO POS {name}", "fuel")
        for _ in range(self.rng.randint(3, 7)):
            name, low, high = self.rng.choice(self.LEISURE)
            self.spend("unicredit", self.random_day(year, month), low, high, "Pagamento POS",
                       f"PAGAMENTO POS {name}", "leisure")
        if self.rng.random() < 0.5:
            self.spend("unicredit", self.random_day(year, month), 6, 48, "Pagamento POS",
                       "PAGAMENTO POS FARMACIA COMUNALE 3", "health")

    # ── random purchases ───────────────────────────────────────────────────────

    SHOPS = [("unicredit", "AMAZON EU SARL", 9, 120), ("unicredit", "DECATHLON", 20, 90),
             ("unicredit", "LIBRERIA FELTRINELLI", 9, 35), ("fineco", "AMAZON EU SARL", 15, 160),
             ("fineco", "ZALANDO SE", 30, 140), ("unicredit", "IKEA CORSICO", 15, 180),
             ("unicredit", "MEDIAWORLD", 25, 220)]

    def shopping(self, year: int, month: int):
        for _ in range(self.rng.randint(1, 4)):
            account, name, low, high = self.rng.choice(self.SHOPS)
            self.spend(account, self.random_day(year, month), low, high, "Pagamento carta", name, "shopping")
        if month in (1, 7):  # the sales
            self.spend("fineco", self.random_day(year, month, 3, 20), 60, 190, "Pagamento carta", "ZALANDO SE saldi",
                       "shopping")
        if month == 12:  # Christmas presents
            for name in ("AMAZON EU SARL", "LA RINASCENTE MILANO", "FELTRINELLI", "PROFUMERIA DOUGLAS", "LEGO STORE"):
                self.spend("unicredit", self.random_day(year, 12, 1, 23), 25, 150, "Pagamento POS",
                           f"PAGAMENTO POS {name} regali di Natale", "gifts")

    # ── seasonal: summer and winter trips (from the savings account) ───────────

    SUMMER = {2022: ("Puglia", "Salento"), 2023: ("Grecia", "Creta"), 2024: ("Giappone", "Tokyo e Kyoto"),
              2025: ("Sardegna", "Costa Smeralda"), 2026: ("Portogallo", "Lisbona e Algarve")}

    def trips(self, year: int, month: int):
        if month == 3 and year != 2024:  # booked in spring
            country, place = self.SUMMER[year]
            flight = "RYANAIR" if year not in (2024,) else "ITA AIRWAYS"
            self.spend("fineco", date(year, 3, self.rng.randint(5, 25)), 180, 420, "Pagamento carta",
                       f"{flight} volo {country}", "travel")
            self.spend("fineco", date(year, 4, self.rng.randint(2, 20)), 550, 1100, "Pagamento carta",
                       f"BOOKING.COM hotel {place}", "travel")
        if month in (7, 8) and (year, month) != (2024, 7):
            first, last = (10, 24) if month == 7 else (5, 21)
            if (month == 7) == (year % 2 == 0):  # July on even years, August on odd ones
                _, place = self.SUMMER[year]
                for _ in range(self.rng.randint(5, 8)):
                    self.spend("fineco", self.random_day(year, month, first, last), 25, 120, "Pagamento carta",
                               f"Ristorante / bar in vacanza - {place}", "travel")
                self.spend("fineco", self.random_day(year, month, first, last), 60, 180, "Pagamento carta",
                           f"Escursioni e musei - {place}", "travel")
                self.spend("fineco", self.random_day(year, month, first, last), 80, 220, "Pagamento carta",
                           "Noleggio auto Hertz", "travel")
        if month == 2:  # skiing
            first = self.rng.randint(5, 16)
            self.spend("fineco", date(year, 1, self.rng.randint(8, 20)), 380, 620, "Pagamento carta",
                       "BOOKING.COM hotel Madonna di Campiglio", "travel")
            self.spend("fineco", date(year, 2, first), 180, 260, "Pagamento carta", "Skipass Dolomiti Superski",
                       "travel")
            self.spend("fineco", date(year, 2, first + 1), 60, 140, "Pagamento carta", "Noleggio sci Sport Check",
                       "travel")
            self.spend("fineco", date(year, 2, first + 2), 70, 160, "Pagamento carta",
                       "Rifugio Graffer pranzo", "travel")

    # ── extraordinary ──────────────────────────────────────────────────────────

    def extraordinary(self):
        u, f = "unicredit", "fineco"
        self.add(u, date(2022, 9, 21), -780, "Bonifico SEPA", "Bonifico a CARROZZERIA LUCCHINI riparazione auto",
                 "car")
        self.add(u, date(2022, 11, 4), -165, "Pagamento POS", "PAGAMENTO POS DENTISTA DR. VERDI pulizia", "health")
        # March 2023: the washing machine breaks
        self.add(u, date(2023, 3, 10), -80, "Pagamento POS", "PAGAMENTO POS ASSISTENZA TECNICA ELETTRODOMESTICI",
                 "home")
        self.add(u, date(2023, 3, 14), -549, "Pagamento POS", "PAGAMENTO POS UNIEURO lavatrice Samsung 9 kg", "home")
        # June–July 2023: buying the house, the savings pay the deposit and the furniture
        self.transfer(date(2023, 6, 20), 15000, "fineco", "anticipo acquisto casa")
        self.add(u, date(2023, 6, 28), -14500, "Bonifico SEPA",
                 "Bonifico a STUDIO NOTARILE ROSSI - anticipo e spese rogito", "home")
        self.add(u, date(2023, 6, 29), -1850, "Bonifico SEPA", "Bonifico a TECNOCASA - provvigione agenzia", "home")
        self.transfer(date(2023, 7, 10), 3500, "fineco", "mobili casa nuova")
        self.add(u, date(2023, 7, 12), -2280, "Pagamento POS", "PAGAMENTO POS IKEA CORSICO arredamento", "home")
        self.add(u, date(2023, 7, 19), -1090, "Bonifico SEPA", "Bonifico a MONDO CONVENIENZA divano", "home")
        self.add(u, date(2023, 7, 25), -320, "Bonifico SEPA", "Bonifico a TRASLOCHI VELOCI SNC", "home")
        # 15 June 2024: the wedding, mostly from the savings account
        self.add(f, date(2023, 10, 16), -3000, "Bonifico SEPA", "Bonifico a VILLA DEI CEDRI - acconto ricevimento",
                 "wedding")
        self.add(f, date(2024, 2, 9), -1200, "Bonifico SEPA", "Bonifico a GIOIELLERIA PISA - fedi nuziali", "wedding")
        self.add(f, date(2024, 3, 22), -1550, "Bonifico SEPA", "Bonifico a ATELIER SPOSA ELISA - abito", "wedding")
        self.add(f, date(2024, 4, 30), -900, "Bonifico SEPA", "Bonifico a FIORERIA MAZZINI - allestimento", "wedding")
        self.add(f, date(2024, 5, 20), -1800, "Bonifico SEPA", "Bonifico a FOTOSTUDIO LUCE - servizio fotografico",
                 "wedding")
        self.add(f, date(2024, 6, 17), -9500, "Bonifico SEPA", "Bonifico a VILLA DEI CEDRI - saldo ricevimento",
                 "wedding")
        self.add(f, date(2024, 6, 21), -4800, "Pagamento carta", "ITA AIRWAYS / JTB viaggio di nozze Giappone",
                 "wedding")
        for i, (name, amount) in enumerate([("ZIA CARLA", 500), ("FAM. BIANCHI", 300), ("LUCA E SARA", 250),
                                            ("NONNI ROSSI", 1500), ("COLLEGHI ACME", 420), ("MARCO VERDI", 200),
                                            ("FAM. ESPOSITO", 350), ("GIULIA NERI", 150), ("ZIO PAOLO", 400),
                                            ("AMICI CALCETTO", 380)]):
            self.add(u, date(2024, 6, 3 + i * 2), amount, "Bonifico in entrata",
                     f"Bonifico da {name} - regalo di nozze", "gift_income")
        self.transfer(date(2024, 7, 5), 4000, "unicredit", "regali di nozze sul risparmio")
        # later surprises
        self.transfer(date(2025, 2, 10), 1000, "fineco", "dentista")
        self.add(u, date(2025, 2, 14), -1400, "Bonifico SEPA", "Bonifico a STUDIO DENTISTICO DR. VERDI - impianto",
                 "health")
        self.add(u, date(2025, 9, 8), -460, "Pagamento POS", "PAGAMENTO POS OFFICINA BOSCH CAR SERVICE tagliando",
                 "car")
        self.add(u, date(2026, 1, 19), -699, "Pagamento POS", "PAGAMENTO POS EURONICS frigorifero combinato", "home")
        self.add(u, date(2026, 4, 7), -320, "Pagamento POS", "PAGAMENTO POS CLINICA VETERINARIA SAN SIRO", "pets")
        self.add(f, date(2026, 5, 12), -1450, "Pagamento carta", "APPLE STORE nuovo portatile MacBook", "shopping")

    # ── the monthly saving ─────────────────────────────────────────────────────

    def saving(self, year: int, month: int):
        amount = {2022: 1500, 2023: 1500, 2024: 1700, 2025: 1850, 2026: 1900}[year]
        if (year, month) in ((2023, 6), (2023, 7)):  # the house: no saving that month
            return
        self.transfer(day_in(year, month, 28), amount, "unicredit", "risparmio mensile")
        if month == 12:  # part of the thirteenth month's pay goes to the savings too
            self.transfer(date(year, 12, 20), 1000, "unicredit", "tredicesima")

    # ── all together ───────────────────────────────────────────────────────────

    def balance(self, account: str, until: date) -> Decimal:
        return OPENING[account] + sum((m.amount for m in self.moves if m.account == account and m.day <= until),
                                      Decimal(0))

    def build(self) -> list[Move]:
        self.extraordinary()
        for year, month in months():
            self.home(year, month)
            self.bills(year, month)
            self.everyday(year, month)
            self.shopping(year, month)
            self.trips(year, month)
            self.saving(year, month)
            self.income(year, month)  # last: the quarterly interest needs the month's movements
        self.moves.sort(key=lambda m: (m.day, m.account, -m.amount))
        return self.moves


def build(seed: int = SEED) -> list[Move]:
    return Household(seed).build()


# ── files ──────────────────────────────────────────────────────────────────────

def _it(value: Decimal) -> str:
    """1234.5 → 1.234,50 (how Italian banks print amounts)."""
    text = f"{value:,.2f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def write_unicredit(moves: list[Move], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        out = csv.writer(handle, delimiter=";")
        out.writerow(["Data Registrazione", "Data valuta", "Descrizione", "Causale", "Importo (EUR)"])
        for m in moves:
            if m.account == "unicredit":
                valuta = m.day + timedelta(days=1 if m.amount > 0 else 0)
                out.writerow([f"{m.day:%d.%m.%Y}", f"{valuta:%d.%m.%Y}", m.full, m.short, _it(m.amount)])


MONEYMAP = {
    "groceries": "Spesa", "fuel": "Carburante", "leisure": "Ristoranti e bar", "health": "Salute",
    "shopping": "Shopping", "rent": "Affitto", "mortgage": "Mutuo", "condo": "Casa", "utilities": "Utenze",
    "subscription": "Abbonamenti", "sport": "Sport", "insurance": "Assicurazioni", "tax": "Tasse",
    "car": "Auto", "gifts": "Regali", "travel": "Viaggi", "home": "Casa", "wedding": "Matrimonio",
    "pets": "Animali", "transfer": "Giroconto", "salary": "Stipendio", "interest": "Interessi",
    "other_income": "Entrate varie", "gift_income": "Entrate varie",
}


def write_fineco(moves: list[Move], path: Path) -> None:
    rows = [m for m in moves if m.account == "fineco"]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Movimenti"
    ws.append(["Conto Corrente: 0012345678"])
    ws.append([f"Intestazione Conto Corrente: {HOLDER}"])
    ws.append([f"Periodo Dal: {START:%d/%m/%Y} Al: {END:%d/%m/%Y}"])
    ws.append([f"Saldo Iniziale: {_it(OPENING['fineco'])}"])
    ws.append([])
    ws.append(["Data_Operazione", "Data_Valuta", "Entrate", "Uscite", "Descrizione", "Descrizione_Completa", "Stato",
               "Moneymap"])
    for cell in ws[6]:
        cell.font = Font(bold=True)
    for m in rows:
        day = f"{m.day:%d/%m/%Y}"
        ws.append([day, day, float(m.amount) if m.amount > 0 else None, float(m.amount) if m.amount < 0 else None,
                   m.short, m.full, "Contabilizzato", MONEYMAP[m.kind]])
    ws.append([])
    ws.append([f"Saldo Finale: {_it(OPENING['fineco'] + sum((m.amount for m in rows), Decimal(0)))}"])
    for column, width in zip("ABCDEFGH", (16, 14, 12, 12, 20, 70, 16, 18)):
        ws.column_dimensions[column].width = width
    wb.save(path)


def summary(moves: list[Move]) -> dict:
    out = {}
    for account in OPENING:
        mine = [m for m in moves if m.account == account]
        out[account] = {
            "rows": len(mine),
            "transfers": sum(m.transfer for m in mine),
            "income": sum((m.amount for m in mine if m.amount > 0 and not m.transfer), Decimal(0)),
            "expenses": sum((m.amount for m in mine if m.amount < 0 and not m.transfer), Decimal(0)),
            "opening": OPENING[account],
            "closing": OPENING[account] + sum((m.amount for m in mine), Decimal(0)),
            "lowest": min(OPENING[account] + sum((x.amount for x in mine if x.day <= m.day), Decimal(0))
                          for m in mine),
        }
    return out


def main() -> None:
    moves = build()
    OUT.mkdir(exist_ok=True)
    write_unicredit(moves, OUT / UNICREDIT_FILE)
    write_fineco(moves, OUT / FINECO_FILE)
    for account, data in summary(moves).items():
        print(f"{account:10} {data['rows']:5} movimenti, {data['transfers']} giroconti, "
              f"saldo {data['opening']} → {data['closing']} (minimo {data['lowest']})")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
