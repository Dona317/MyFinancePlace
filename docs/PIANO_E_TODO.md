# Piano e TODO — MyFinancePlace

Unico punto di controllo di cosa fare dopo. Complementa (non sostituisce) [ROADMAP](../ROADMAP.md) (stato
delle sezioni), [NEXT_STEPS](NEXT_STEPS.md) (cronologia tecnica) e [ANALISI_COMPETITOR](ANALISI_COMPETITOR.md).

**Ultimo aggiornamento**: 8 ottobre 2026 · **Ramo**: `test-Cloud` (PR #8, in bozza) ·
**MVP**: completo · **Test**: 643, copertura 95,6% · **Migrazioni**: 20

| Stato | Significato |
|---|---|
| ⬜ | da fare |
| 🔄 | in corso |
| ✅ | fatto |
| ⏸ | in attesa di una decisione |
| ❌ | scartato |

---

## 1. Scansione dello stato (7 ott 2026)

- `test-Cloud` ha tutto l'MVP: dati reali, report, import 8 banche + generico, AI locale/Claude, conti e valute,
  budget, obiettivi, portafoglio, debiti, assicurazioni, backup, login, IT/EN, Docker, CI. 17 migrazioni.
- `main` è ancora lo scheletro con numeri finti: **finché la PR #8 non è unita, `main` non rappresenta l'app**.
- `origin/Mapping-Excel` non ha commit che `test-Cloud` non abbia già (0 avanti) → le "misure più compatte"
  vanno recuperate a mano, se servono (vedi D2).
- Nessun file `LICENSE` nel repo.
- I dati sono condivisi tra utenti (nessun `user_id` nei modelli).
- Scoperti documenti disallineati, da correggere (vedi sezione 4):
  - `ANALISI_COMPETITOR.md` mette il Sankey tra le cose mancanti: **è già fatto**; la decisione 1 (partita
    doppia) è **già presa** (scartata).
  - `MVP.md` / `NEXT_STEPS.md`: coerenti con il codice, ma "Da fare: niente" non cita i punti di questo file.

---

## 2. Decisioni aperte (servono a te)

| # | Decisione | Stato | Perché blocca |
|---|---|---|---|
| D1 | Unire la PR [#8](https://github.com/Dona317/MyFinancePlace/pull/8) su `main` (verde, senza conflitti; è in bozza) | ⏸ | `main` resta finto finché non si unisce; ogni nuovo ramo parte da qui |
| D2 | Applicare le misure compatte di `Mapping-Excel`? (ramo senza commit propri: da rifare a mano) | ⏸ | solo estetica, non blocca |
| D3 | ✅ Forma dell'app: **eseguibile desktop** (deciso il 7 ott 2026) | ✅ | apre F16 (confezionamento); F12 (PWA) cade; F11 (dati per utente) poco utile su un PC personale |
| D4 | Licenza: MIT **o** AGPL | ⏸ | serve prima di rendere pubblico; AGPL impedisce fork chiusi |
| D5 | Fisco italiano (730, capital gain): puntarci o lasciare ad altri? | ⏸ | decide se il lavoro F-fisco entra nel piano |
| D7 | Database dell'eseguibile: PostgreSQL incorporato (nessuna modifica al codice, installer più pesante) **o** SQLite (installer leggero, da riscrivere le parti solo Postgres) | ⏸ | decide il lavoro di F16 |
| D6 | ❌ Partita doppia | ❌ | già scartata (ROADMAP → Scartato) |

Suggerimento di ordine: D1 e D4 sono rapide. D3 è decisa (desktop): F16 parte dalla scelta del database (D7).

---

## 3. Backlog funzionalità

Priorità: **A** = alta (poco lavoro, grande effetto, ce l'hanno tutti i concorrenti) · **M** = media · **B** = bassa/dopo.
Sforzo: S (≤ 1 giorno) · M (2–4 giorni) · L (oltre).

### Prossimo giro (candidati naturali)

| ID | Pri | Sforzo | Stato | Funzione | Note |
|---|---|---|---|---|---|
| F1 | A | L | ✅ | **Transazioni suddivise** su più categorie | «Suddividi» nel modulo; tabella `transaction_splits`; ogni somma per categoria conta le parti; API, export e backup inclusi |
| F2 | A | M | ✅ | **Tabella Riepilogo** categoria × mese con heatmap | Report → Riepilogo: sottocategorie, totale, media, Δ% sull'anno prima, netto e tasso di risparmio; ogni cella apre le transazioni; CSV |
| F3 | A | S | ✅ | **Tasso di risparmio** mese per mese + confronto anno precedente | Dashboard: card «Tasso di risparmio mese per mese» con tutti gli anni, l'utente sceglie quali confrontare (interruttore in Impostazioni); riga nel Riepilogo con F2 |

### Dati e qualità

| ID | Pri | Sforzo | Stato | Funzione | Note |
|---|---|---|---|---|---|
| F4 | A | M | ⬜ | **Prova con estratti conto reali anonimizzati** (8 banche) | Campioni oggi generati; PDF a maggior rischio. Serve che tu fornisca i file |
| F5 | M | M | ✅ | **Storico prezzi investimenti** (+ prezzi automatici ETF/cripto) | `holding_prices`: Portafoglio → Storico prezzi (uno o più prezzi incollati, grafico), «Aggiorna prezzi» con data; stati patrimoniali, andamento e istantanee usano il prezzo di allora. Prezzi automatici rimandati a F16 (serve una fonte esterna) |
| F6 | M | M | ✅ | **Import OFX / QIF / CAMT.053** | `structured_statements.py` (solo libreria standard): OFX 1 SGML e 2 XML, QIF con categorie e giroconti, CAMT.053/052 con quadratura dei saldi e movimenti in attesa esclusi; stessa anteprima, categorie e duplicati degli altri estratti; 4 campioni |

### Budget e analisi

| ID | Pri | Sforzo | Stato | Funzione | Note |
|---|---|---|---|---|---|
| F7 | M | M | ✅ | **Riporto del budget** al mese dopo + accantonamento per spese annuali | Budget → «Riporta»: avanzo o sforamento passano al mese dopo, dal mese in cui lo accendi; «Da accantonare»: per le categorie non mensili (F8) 1/12 degli ultimi 12 mesi, un clic lo imposta come budget con riporto |
| F8 | M | S | ✅ | **Categorie fisse / non mensili / variabili** | Natura in Impostazioni → Categorie (le sottocategorie ereditano); Spese e tendenze: barra fisse/non mensili/variabili e quota comprimibile; pallino nel Riepilogo |
| F9 | M | S | ✅ | **Pagina Abbonamenti** | Previsioni → Abbonamenti: confermati e rilevati, costo mensile/annuo, prossimo addebito, aumenti di prezzo; Conferma, «Non più attivo» / Riattiva; scheda entrate ricorrenti |
| F10a | M | S | ✅ | **Mesi di autonomia** (liquidità ÷ spesa media) | Dashboard → Salute finanziaria: media degli ultimi 12 mesi completi (almeno 3), anche solo spese fisse e non mensili (F8); obiettivo 3/6/9/12 mesi in Impostazioni |
| F10b | B | S | ✅ | **Stabilità delle entrate per fonte** | Previsioni → pannello «Stabilità delle entrate»: per fonte mesi presenti su 12, media, variazione, quota; stabile / variabile / occasionale e quota delle entrate stabili |
| F10c | B | M | ⬜ | Heatmap giornaliera a calendario; analisi libera per tag | |

### Piattaforma e usabilità

| ID | Pri | Sforzo | Stato | Funzione | Note |
|---|---|---|---|---|---|
| F11 | B | L | ⏸ | **Dati separati per utente** | Con D3 = desktop serve solo per più persone sullo stesso PC: per ora no |
| F12 | — | — | ❌ | PWA installabile sul telefono | Scartata con D3 = desktop |
| F16 | A | L | ⬜ | **Eseguibile desktop** (D3) | Finestra nativa (pywebview) sul server locale, PyInstaller per Windows/macOS/Linux; il nodo è il database: PostgreSQL incorporato (binari portabili avviati dall'app) **oppure** passaggio a SQLite (da togliere gli `ARRAY`/funzioni solo Postgres). Login facoltativo, dati e documenti nella cartella utente, aggiornamenti |
| F13 | B | M | ✅ | Inserimento rapido da tastiera, annulla/ripeti | Transazioni: riga d'inserimento rapido («n» per andarci, Invio per salvare; categoria e controparte indovinate); barra Annulla/Ripeti (Ctrl+Z / Ctrl+Y) per l'ultima aggiunta o eliminazione, anche multipla, per 30 minuti |
| F14 | B | M | ⬜ | Notifiche email (scadenze, budget superati) | Serve SMTP configurabile |
| F15 | B | L | ⏸ (D5) | Fisco italiano (730, capital gain) | Solo se D5 = sì |

Esclusi per scelta: collegamento automatico alle banche, budget "a buste", partita doppia.

---

## 4. Manutenzione documenti e igiene

| ID | Stato | Cosa |
|---|---|---|
| M1 | ✅ | Aggiornare `ANALISI_COMPETITOR.md`: Sankey fatto; decisione 1 chiusa (scartata) — aggiornato l'8 ott 2026 con tutte le F fatte |
| M2 | ⬜ | Aggiungere un `LICENSE` appena presa D4 |
| M3 | ✅ | Rimandare da `MVP.md` ("Dopo l'MVP") e `NEXT_STEPS.md` ("To do") a questo file, per non avere tre liste |
| M4 | ⬜ | Rendere `.claude/` e `.vscode/` ignorati o committati (oggi non tracciati) |
| M5 | ⬜ | Ripetere la prova di test e copertura in locale (nel venv del progetto; l'interprete usato in questa scansione non ha pytest) |

---

## 5. Come tenerlo in check

1. **Una voce = un ID** (D*, F*, M*). Nei commit e nelle PR si cita l'ID (`F2: tabella Riepilogo`).
2. **Quando una voce cambia stato**, si aggiorna qui **nello stesso commit** del codice, e si aggiunge la riga
   in [NEXT_STEPS.md](NEXT_STEPS.md) → ✅ Done e, se è una sezione dell'app, in [ROADMAP.md](../ROADMAP.md).
3. **Definition of Done** di una funzione: migrazione (se serve) + test + traduzione EN (`scripts/translations.py`)
   + `scripts/untested_functions.py` pulito + CI verde.
4. **Una decisione presa** si sposta da §2 a ROADMAP → Scartato / NEXT_STEPS, con la data.
5. **Revisione**: a ogni merge su `test-Cloud` si rilegge §2 e §3; si cambia la data in testa.
6. Max 1–2 voci 🔄 alla volta.

## 6. Proposta di ordine

1. D1 (unire PR #8) e D4 (licenza) → M2.
2. D3 (forma dell'app).
3. F3 → F2 (riusano gli stessi dati: tasso di risparmio dentro il Riepilogo) → F1 (il più grosso, da solo).
4. F4 non appena hai i file reali; F6 e F5 dopo.
5. F7–F10 a blocchi piccoli; F11/F12/F14/F15 solo dopo D3/D5.
