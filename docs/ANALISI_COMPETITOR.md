# Analisi competitor vs MVP

> 1° ottobre 2026. Estende i due file in `docs/Strategy and Business/` (`Analisi Strategica.xlsx`,
> `Market_Mapping_Personal_Finance.xlsx`) scendendo al livello delle **funzionalità**, sezione per sezione
> dell'MVP. I dati completi sono in
> [`Analisi Funzionalita vs MVP.xlsx`](Strategy%20and%20Business/Analisi%20Funzionalita%20vs%20MVP.xlsx).
> Lo stato di MyFinancePlace è verificato sul codice di `origin/test-Cloud` (b30343e), non sulle intenzioni.

## 1. In sintesi

I due Excel dicono: *il mercato è diviso tra "contabilità profonda con UX datata" (GnuCash, Firefly III) e
"UX bella con contabilità superficiale" (Monarch, YNAB); lo spazio vuoto è la contabilità vera con UX moderna,
in locale e pensata per l'Italia*. L'analisi regge, con tre correzioni che la cambiano:

1. **La partita doppia non c'è ancora.** Nel codice ogni transazione è un movimento singolo, con tipo, categoria
   testuale, conto e controconto (quest'ultimo solo per i giroconti). SP, CE e CF sono calcolati dai movimenti.
   Il pilastro su cui poggia tutto il posizionamento ("double-entry vero", profondità 10/10) va **o costruito o
   ridimensionato**. È la prima decisione da prendere con il co-dev.
2. **Lo spazio non è scoperto.** Maybe è archiviato, ma il fork **Sure** è attivo: release il 3 agosto e il
   2 settembre 2026, con budget e riporto, obiettivi e AI. Va tra i competitor diretti.
3. **"Open source" richiede una licenza.** Il repository non ha un file `LICENSE`: il codice si può leggere
   ma non riutilizzare.

Gli altri dati da correggere (Moneyviz, piattaforma, formati di import, punteggi incoerenti tra i fogli) sono nel
foglio **Correzioni ai dati** (12 punti).

## 2. Punteggio delle funzionalità

Su 37 funzionalità raggruppate per sezione dell'MVP (✓ = 1, ◐ = 0,5, scala 0–10):

| Monarch | Banktivity 10 | **MyFinancePlace** | Actual | Firefly III | GnuCash | Sure | PocketSmith | Wallet | Copilot | YNAB | Sossoldi |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 6,6 | 6,2* | **6,1** | 5,7 | 5,7 | 5,4 | 5,3* | 5,0 | 4,9* | 4,7 | 4,3 | 2,3 |

\* Sure, Banktivity e Wallet hanno molte celle "?" (5–8): il loro punteggio è probabilmente più alto.

Il punteggio misura quante funzioni ci sono, non la loro qualità. Il messaggio è che **l'MVP è già al livello
dei migliori per ampiezza**: la differenza la faranno la profondità contabile e la UX.

## 3. Dove MyFinancePlace è già unico

| Funzionalità | Chi altro la fa |
|---|---|
| Estratti conto di banche italiane riconosciuti per layout (8 + generico) | Nessuno (Wallet si collega alle banche via cloud) |
| Lettura di PDF e scansioni con OCR/AI, sempre con conferma | Nessuno |
| Categorizzazione con AI **locale** e dallo storico | Copilot, Monarch e Sure lo fanno in cloud |
| SP + CE + CF insieme | Solo GnuCash (con una UX datata) |
| Previsione con 6 metodi confrontati sul passato | PocketSmith ha una previsione più lunga, ma a pagamento |
| Debiti con ammortamento, assicurazioni, archivio documenti | Nessuno così ampio |

## 4. Cosa manca rispetto ai competitor (in ordine di priorità)

**Alta**: poco lavoro, grande effetto.
- **Transazioni suddivise** su più categorie (standard in YNAB, Actual, Monarch, GnuCash).
- **Sankey** entrate → uscite → risparmio (Monarch, Sure, Actual sperimentale). Plotly lo supporta già.
- **Tabella Riepilogo** categoria × mese, cioè l'Excel dentro l'app (Lunch Money Query Tool, Tiller).
- **Tasso di risparmio mese per mese**: oggi c'è solo come KPI.
- **Licenza open source.**

**Media**
- **Riporto del budget** (rollover) al mese dopo: ormai lo fanno tutti tranne GnuCash e Sossoldi.
- **Spese fisse / non mensili / variabili** (Monarch Flex): basta un attributo sulla categoria.
- **Vista abbonamenti**: i ricorrenti sono già riconosciuti in Previsioni.
- **Import OFX / QIF / CAMT.053** (Actual, GnuCash, YNAB).
- **Inserimento da tastiera e annulla/ripeti** (Actual).

**Da non fare**: collegamento automatico alle banche (esclusa per scelta) e budget a buste o a base zero
(è un'altra filosofia).

## 5. Analisi da aggiungere a quelle dell'Excel

Il foglio `TEMPLATE - Portafolio.xlsx` è una matrice categoria × 12 mesi con netto mensile e totali annui,
già riprodotta dalla dashboard dell'MVP. Da aggiungere:

- **Subito**: tabella Riepilogo con heatmap, tasso di risparmio mensile, confronto con l'anno precedente, Sankey.
- **Fase 2**: spese fisse/non mensili/variabili, accantonamento per spese annuali, vista abbonamenti, stabilità
  delle entrate per fonte, mesi di autonomia (liquidità ÷ spesa media).
- **Dopo**: heatmap giornaliera a calendario, analisi libera per tag.

Il dettaglio (fonte, motivo, sforzo) è nel foglio **Analisi da aggiungere**.

## 6. Decisioni da prendere con il co-dev

1. **Partita doppia**: costruire il ledger (conti per categorie, movimenti con ≥ 2 righe bilanciate) oppure
   riposizionarsi come "conti + rendiconti derivati"? Tutto il resto del posizionamento dipende da questa scelta.
2. **Licenza**: MIT (come Actual) o AGPL (come Firefly III e Sure, che impedisce fork chiusi).
3. **Forma dell'app**: web self-hosted con login, com'è oggi, o desktop in un solo file, come dicono gli Excel?
4. **Pilastro fiscale IT**: oggi c'è solo l'export per anno. Moneyviz (Torino) copre già il fisco su trading
   e cripto: conviene puntarci o lasciarlo?

## Fonti

Elenco completo nel foglio **Fonti** del file Excel. Le principali:
[Sure v0.7.4](https://github.com/we-promise/sure/releases/tag/v0.7.4) ·
[Actual release notes](https://actualbudget.org/docs/releases/) ·
[Banktivity 10](https://www.banktivity.com/content/help/v10/getting_started/new_features.php) ·
[Monarch Cash Flow](https://help.monarch.com/hc/en-us/articles/20504904768020-Cash-Flow) ·
[PocketSmith forecasts](https://www.pocketsmith.com/tour/cash-flow-forecasts/) ·
[Sossoldi roadmap](https://rip-comm.github.io/sossoldi/roadmap.html) ·
[Moneyviz (CB Insights)](https://www.cbinsights.com/company/moneyviz) ·
[Firefly III releases](https://github.com/firefly-iii/firefly-iii/releases) ·
[YNAB Reflect](https://support.ynab.com/en_us/reflect-in-ynab-B1GJsrWkj) ·
[Lunch Money](https://lunchmoney.app/features/stats-trends/)
