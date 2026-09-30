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
| Categorie | 33 categorie di base (entrate e uscite) tutte modificabili, regole di categorizzazione scritte o imparate dalle correzioni |
| Dashboard | KPI, torte di entrate e uscite, linee mese per mese per categoria (entrate e uscite), istogramma mensile con le cumulate, per anno |
| Report | Spese, entrate, cash flow per periodo e conto, dettaglio per categoria, CSV |
| Import | Estratti conto di 8 banche + formato generico (Excel, CSV, PDF, Word, ODF, RTF), anteprima modificabile, lettura AI opzionale di scansioni con conferma |
| Patrimonio | Conti e carte, più valute, portafoglio, debiti, assicurazioni, documenti, obiettivi, snapshot, stato patrimoniale |
| Dati | Backup completo (.zip) e ripristino; dati di esempio in `samples/dati_fittizi` |
| Interfaccia | Italiano / inglese, tema chiaro / scuro, menu laterale comprimibile, uso da telefono |
| **Login** | Primo utente = amministratore creato al primo avvio; poi utenti aggiunti solo da un amministratore; dati condivisi da tutti; cambio password; comandi `flask users` per recuperare l'accesso |
| **Docker** | Dati nel volume `db` (sistemato il refuso `PGDARE`), immagine fissata a `postgres:16`, procedura per spostare i dati di un'installazione esistente in [DEPLOY.md](DEPLOY.md) |

## 🔜 Da fare

### 2. Saldi dei conti nella valuta del conto

Oggi il saldo di un conto somma gli importi originali delle transazioni: un pagamento in USD con una carta in EUR
conta in USD finché non si inserisce l'importo in EUR addebitato dalla banca. Serve:
- per ogni transazione in valuta diversa da quella del conto, l'importo nella valuta del conto (quello
  addebitato dalla banca, oppure calcolato con il cambio del giorno finché manca);
- saldi, riconciliazione e stato patrimoniale calcolati con quell'importo;
- nell'import da banca, leggere entrambi gli importi quando l'estratto li riporta.

## ❓ TBD

### 4. Import bancari su file reali + nome dell'esercente

Da definire quando saranno disponibili estratti conto **reali anonimizzati** delle banche supportate:
- verificare i layout (UniCredit, BPER, BancoPosta, ING, Revolut, N26, e i PDF in generale) su file veri: oggi
  seguono i nomi di colonna pubblicati, ma i campioni in `samples/bank_statements` sono generati;
- estrarre il nome dell'esercente (controparte) dalla causale, che diventa il primo tag della transazione.

## Dopo l'MVP

- Storico dei prezzi dei titoli (oggi gli stati patrimoniali passati usano l'ultimo prezzo).
