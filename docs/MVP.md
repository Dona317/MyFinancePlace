# MVP — MyFinancePlace

What the first complete version must do, and where each item stands. Details and the longer roadmap are in
[NEXT_STEPS.md](NEXT_STEPS.md).

| Stato | Legenda |
|---|---|
| ✅ | fatto |
| 🔜 | da fare, deciso |
| ❓ | TBD: da definire quando ci sono i dati per farlo |

## ✅ Fatto

| Area | Cosa |
|---|---|
| Transazioni | Inserimento con importo con segno (il segno dà entrata/uscita, giroconti a parte), controparte come primo tag, selettore dei tag già usati, tag «da confermare (AI)» confermabile con un clic, ricerca e filtri, duplicati, API REST |
| Categorie | 33 categorie di base (entrate e uscite) tutte modificabili, con **sottocategorie** (es. Bollette › Luce); regole scritte o imparate dalle correzioni; suggerimenti dal tuo storico prima dell'AI |
| Dashboard | KPI, torte di entrate e uscite, linee mese per mese per categoria (entrate e uscite), istogramma mensile con le cumulate, per anno |
| Report | Spese, entrate, cash flow per periodo e conto, dettaglio per categoria, CSV |
| Import | Estratti conto di 8 banche + formato generico (Excel, CSV, PDF, Word, ODF, RTF), anteprima modificabile; scansioni e foto lette da un **OCR leggero** con l'AI come riserva |
| Patrimonio | Conti e carte, più valute, portafoglio, debiti, assicurazioni, documenti, obiettivi, snapshot, stato patrimoniale |
| Dati | Backup completo (.zip) e ripristino; dati di esempio in `samples/dati_fittizi` |
| Interfaccia | Italiano / inglese, tema chiaro / scuro, menu laterale comprimibile, uso da telefono |
| **Login** | Primo utente = amministratore creato al primo avvio; poi utenti aggiunti solo da un amministratore; dati condivisi da tutti; cambio password; comandi `flask users` per recuperare l'accesso |
| **Saldi in valuta** | Ogni conto somma nella propria valuta: per i movimenti in un'altra valuta vale l'importo addebitato dalla banca (campo nel modulo, anche per il conto d'arrivo dei giroconti) oppure, finché manca, il cambio del giorno, con un avviso nel dettaglio del conto; totali dei conti e saldi iniziali convertiti nella valuta base |
| **Qualità** | Ogni funzione dell'app è eseguita da almeno un test (controllo in CI con `scripts/untested_functions.py`, copertura ≥ 94%) |
| **Docker** | Dati nel volume `db` (sistemato il refuso `PGDARE`), immagine fissata a `postgres:16`, procedura per spostare i dati di un'installazione esistente in [DEPLOY.md](DEPLOY.md) |

## 🔜 Da fare

Niente: tutti i punti decisi sono fatti. Resta il punto 4, da definire.

## ❓ TBD

### 4. Import bancari su file reali + nome dell'esercente

Da definire quando saranno disponibili estratti conto **reali anonimizzati** delle banche supportate:
- verificare i layout (UniCredit, BPER, BancoPosta, ING, Revolut, N26, e i PDF in generale) su file veri: oggi
  seguono i nomi di colonna pubblicati, ma i campioni in `samples/bank_statements` sono generati;
- estrarre il nome dell'esercente (controparte) dalla causale, che diventa il primo tag della transazione.

## Dopo l'MVP

- Storico dei prezzi dei titoli (oggi gli stati patrimoniali passati usano l'ultimo prezzo).
