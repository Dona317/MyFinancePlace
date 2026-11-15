# Catalogo dei grafici di investimento, patrimonio e pianificazione da riportare in MyFinancePlace (ricerca al 9 nov 2026)

Ambito: solo i **grafici**, più in largo e più a fondo delle note già fatte. Non ripeto quello che c'è in
`../Grafici dati e piano Portafoglio/` (budget, kit standard dei portfolio tracker, matrice grafici × app di budgeting,
inventario MFP). Riassunto di cosa MFP **disegna già** (da `myfinanceplace_inventario.md`):
- **Chart.js 4.4.3 locale**: linea, barre (anche impilate, orizzontali e miste), ciambella e torta.
- **Disegnati dal server**: Sankey SVG e calendario-heatmap.
- **Tabelle**: tabella-heatmap categoria × mese.
- **Portafoglio**: TWR cumulato vs benchmark, rendite mensili impilate, ciambelle di composizione.
- **Pianificazione**: Monte Carlo pensione su 3 linee percentili (10°/50°/90°), piano di ammortamento in linea.
- **Patrimonio**: barre impilate liquidità/investimenti/beni/debiti + linea patrimonio netto, "crescita del patrimonio"
  impilata, linea delle Istantanee.

Metodo e fonti:
- **Codice letto** dai cloni locali, con commit e data:
  - Portfolio Performance (PP) `5b7f79d`, 7 nov 2026
  - Wealthfolio `ea92ff8`, 8 nov 2026
  - Ghostfolio `7bf71c6`, 9 nov 2026
  - Sure `4f2970b`, 9 nov 2026
  - Fava ed ezBookkeeping dai cloni in `scratchpad/repos`
- **Reazioni** dall'API di ricerca GitHub (`gh api search/issues`, 9 nov 2026).
- **Siti bloccati dalla rete della sessione (ENOTFOUND)**: projectionlab.com (anche cdn.), parqet.com. Per i prodotti
  commerciali ho quindi usato solo i **frammenti di WebSearch**, che lo dico ogni volta ("snippet"). Reddit non è
  consultato, tranne un mirror nei risultati di ricerca.

---

## 1. Grafici di investimento: quali esistono, chi li usa, cosa rispondono, dati e interazione

### Takeaway
Oltre al kit già annotato (valore vs investito, cumulato vs benchmark, heatmap mensile, drawdown, torte e treemap), i
tool più maturi aggiungono quattro famiglie di grafici:
- **Scomposizione del rendimento**: per fonte (capitale/dividendi/valuta in Sharesight) o per "driver" (versamenti vs
  mercato in Wealthfolio).
- **Prezzo del titolo con indicatori e marcatori**: acquisti, vendite, dividendi e prezzo medio di carico, molto ricco
  in PP, richiesto in Wealthfolio.
- **Rischio/rendimento**: lo scatter di PP; frontiera efficiente e matrice di correlazione solo in strumenti di analisi
  come Portfolio Visualizer.
- **Barre attuale vs target**: con bande di tolleranza (PP, Wealthfolio).

Per MFP i più utili e fattibili con Chart.js sono:
- heatmap mensile (anche "excess return" sul benchmark);
- underwater drawdown;
- prezzo del titolo con marcatori delle operazioni e linea del prezzo medio;
- waterfall della variazione;
- barre drift vs target.

### Cited Findings

**A. Valore vs capitale investito e serie configurabili (PP "Statement of Assets")**
- **Serie disponibili**: PP permette di sovrapporre su un unico grafico storico qualunque combinazione di queste
  serie: totale, versamenti/prelievi (anche cumulati), capitale investito e capitale investito assoluto, delta, delta
  assoluto, dividendi, interessi, interessi passivi, earnings, commissioni e tasse, ognuna per periodo e cumulata. —
  [DataSeries.java](https://github.com/portfolio-performance/portfolio/blob/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/dataseries/DataSeries.java),
  [ClientDataSeriesChartWidget.java](https://github.com/portfolio-performance/portfolio/blob/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/dashboard/charts/ClientDataSeriesChartWidget.java)
- **A che livello**: le serie si possono tracciare per cliente, conto, deposito, titolo, titolo come benchmark,
  "deposito + conto" e serie derivate, anche in versione "PreTax" (al lordo delle tasse). Usi: `STATEMENT_OF_ASSETS`,
  `PERFORMANCE`, `RETURN_VOLATILITY`. — stessa fonte (`DataSeries.java`, enum `Type` e `UseCase`)
- **Sure, richiesta aperta**: la #4008 (6 ott 2026, 1 👍) chiede per il conto di investimento di "plot net contributions
  beside total value, so the gap shows performance". Lo stesso grafico che PP offre da anni. —
  [we-promise/sure#4008](https://github.com/we-promise/sure/issues/4008)

**B. Heatmap dei rendimenti mensili e annuali, con "excess return"**
- **Widget di PP**: `PerformanceHeatmapWidget` (mesi × anni), `YearlyPerformanceHeatmapWidget`,
  `InvestmentHeatmapWidget` (versamenti per mese), `CostHeatmapWidget` (commissioni e tasse per mese). —
  [cartella heatmap](https://github.com/portfolio-performance/portfolio/tree/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/dashboard/heatmap)
- **Ornamenti e confronti di PP**: per riga e colonna si sceglie un ornamento tra somma, media geometrica e deviazione
  standard (`HeatmapOrnament`). Il confronto con un benchmark ha due operatori (`ExcessReturnOperator`):
  - ALPHA, cioè x − y;
  - RELATIVE, cioè (1+x)/(1+y) − 1.

  Ci sono anche uno schema colori configurabile (`ColorSchemaConfig`) e una media (`AverageConfig`). — stessa cartella
- **Problemi segnalati in PP**:
  - #1790 "Heatmaps are empty on Linux" (18 👍, chiusa);
  - #5752 "Wrong Heatmap Values for Monthly Excess Returns (Baseline)" (30 mag 2026, chiusa);
  - #5248 "Monatsrenditen Heatmap zeigt NaN" (aperta).

  Sul forum un utente chiede di poter usare l'IRR (money-weighted) nelle heatmap, che oggi usano solo il TWR. —
  [#1790](https://github.com/portfolio-performance/portfolio/issues/1790),
  [#5752](https://github.com/portfolio-performance/portfolio/issues/5752),
  [#5248](https://github.com/portfolio-performance/portfolio/issues/5248),
  [forum PP IRR heatmap](https://forum.portfolio-performance.info/t/feature-anfrage-irr-money-weighted-return-fur-monatliche-und-jahrliche-heatmaps/38516)
- **Wealthfolio**: la #1366 "Additional performance view - Monthly return by calendar year" (28 lug 2026, 6 👍, aperta)
  è la richiesta di grafico più votata del repo. — [wealthfolio#1366](https://github.com/wealthfolio/wealthfolio/issues/1366)
- **Parqet** (snippet di ricerca): una heatmap dei rendimenti per mese o trimestre, a livello di titolo per tutti.
  La vista dell'intero portafoglio (Analisi → "Returns") è riservata agli abbonati. Solo web app. —
  [Parqet blog performance-heatmap](https://parqet.com/en/blog/performance-heatmap) (pagina non apribile, solo snippet)

**C. Drawdown (underwater) e durata**
- **PP**:
  - `DrawdownChartWidget` (grafico del drawdown nel tempo);
  - `MaxDrawdownDurationWidget`;
  - indicatori "Current Drawdown", "Distance from ATH", "All Time High".

  Sul forum c'è la richiesta di un widget "Current Drawdown Duration". —
  [DrawdownChartWidget.java](https://github.com/portfolio-performance/portfolio/blob/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/dashboard/charts/DrawdownChartWidget.java),
  [forum PP](https://forum.portfolio-performance.info/t/request-current-drawdown-duration-metric/38284)
- **Parqet** ha un articolo dedicato al "Drawdown Chart" (snippet, non aperto). —
  [parqet drawdown-chart](https://parqet.com/en/blog/drawdown-chart)
- **Portfolio Visualizer** calcola i drawdown sui rendimenti mensili, secondo un report di backtest archiviato del
  2018 (fonte indiretta). — [robberger Portfolio Visualizer](https://robberger.com/tools/portfolio-visualizer/),
  [algotrading101](https://algotrading101.com/learn/portfolio-visualizer-guide/)

**D. Rischio/rendimento (scatter)**
- **PP** ha una vista dedicata, `ReturnsVolatilityChartView`:
  - un punto per serie (portafoglio, conti, titoli, benchmark);
  - rendimento in TTWROR o IRR (`KEY_USE_IRR`);
  - rischio come volatilità o semivolatilità (`RiskMetric`).

  — [ReturnsVolatilityChartView.java](https://github.com/portfolio-performance/portfolio/blob/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/ReturnsVolatilityChartView.java)
- **Portfolio Visualizer**: frontiera efficiente, ottimizzazione (media-varianza, CVaR, drawdown), Black-Litterman,
  correlazioni tra asset a coppie e a matrice, correlazione mobile (ad es. 60 giorni), backtest contro portafogli
  "lazy" (snippet di guide di terzi, sito ufficiale non consultato). —
  [algotrading101](https://algotrading101.com/learn/portfolio-visualizer-guide/),
  [dev.to review](https://dev.to/pickuma/portfolio-visualizer-review-backtesting-that-goes-beyond-the-equity-curve-28n2)

**E. Prezzo del titolo con marcatori delle operazioni e indicatori**
- **PP, `SecuritiesChart`**. Elementi attivabili:
  - marcatori di investimento (acquisti e vendite), dividendi ed eventi (split);
  - massimi e minimi;
  - prezzo d'acquisto FIFO e "prezzo medio mobile" di carico come linea;
  - bande di Bollinger e MACD;
  - medie mobili SMA ed EMA a 5, 20, 30, 38, 50, 90, 100 e 200 giorni;
  - linee verticali dei marcatori ed etichette dei valori.

  Default: `INVESTMENT`, `EVENTS`, ecc. Esiste anche una serie "azioni possedute" (`SharesHeldChartSeries`). —
  [SecuritiesChart.java](https://github.com/portfolio-performance/portfolio/blob/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/SecuritiesChart.java),
  [SharesHeldChartSeries.java](https://github.com/portfolio-performance/portfolio/blob/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/securitychart/SharesHeldChartSeries.java)
- **Wealthfolio**:
  - Il componente `history-chart-marker.tsx` definisce i marcatori `snapshot | buy | sell | split | activity` e
    colora la linea in rosso sotto zero.
  - Richieste aperte: #982 "Buy & Sell activities on stock history graph" (16 mag 2026, 5 👍) e #468 "Show positions
    on security detail screen" (2 👍).
  - La #2478 (4 nov 2026) contesta la scala dell'asse Y, che "makes portfolio history charts misleading": è un
    problema di asse che non parte da zero.

  — [history-chart-marker.tsx](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/components/history-chart-marker.tsx),
  [#982](https://github.com/wealthfolio/wealthfolio/issues/982), [#468](https://github.com/wealthfolio/wealthfolio/issues/468),
  [#2478](https://github.com/wealthfolio/wealthfolio/issues/2478)

**F. Scomposizione del rendimento e della variazione (contribution/attribution, "waterfall")**
- **Sharesight, "Contribution Analysis Report"**:
  - divide il rendimento totale di ogni titolo in capital gain, dividendi e guadagno di cambio, in valuta e in %;
  - raggruppa per mercato, valuta, settore, industria, tipo, paese o gruppo personalizzato;
  - export in Excel, PDF e Google Sheets.

  Il piano in cui è incluso è in conflitto tra le fonti ("Expert e Pro" nell'help, "standard e premium" nel blog). —
  [help.sharesight contribution-analysis-report](https://help.sharesight.com/contribution-analysis-report),
  [blog sharesight](https://www.sharesight.com/blog/explore-your-portfolio-performance-with-the-contribution-analysis-report/)
- **Wealthfolio, "Drivers of change"**: il patrimonio netto ha un pannello "Drivers of change" con voci investment
  gains/losses, other assets, contributions, withdrawals, debt paid down, new debt. Ha anche "Monthly pace" con
  multiplo della media a 12 mesi e "Momentum" vs periodo precedente. È di fatto una cascata dei fattori di variazione. —
  [insights.json (networth.velocity)](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/i18n/locales/en/insights.json)
- **Ghostfolio**: scompone la performance tra asset e valuta ("Asset Performance vs Currency Performance"), già
  annotato in `portfolio_tracker_prodotto.md`.
- **PP**:
  - Top Contributors per valore e Top Performers;
  - heatmap commissioni/tasse;
  - widget "tasso di commissioni e tasse del portafoglio".

  Non ho trovato un grafico waterfall nativo. — [cartella dashboard](https://github.com/portfolio-performance/portfolio/tree/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/dashboard)

**G. Dividendi: calendario, barre, previsione, crescita**
- **Snowball Analytics** (snippet):
  - calendario con dividendi ricevuti, dichiarati e stimati;
  - grafico "Reaching the target", che stima quando si raggiunge un obiettivo di rendita con versamenti, senza
    versamenti o solo reinvestendo i dividendi;
  - crescita dei dividendi sugli ultimi 3 anni.

  Non ho trovato un grafico chiamato "payback". — [snowball overview](https://snowball-analytics.com/blog/snowball-analytics-overview),
  [help snowball](https://help.snowball-analytics.com/mobile-app-review/)
- **Parqet** (snippet): calendario dei dividendi su oltre 35.000 titoli, dividendi annunciati e attesi fino a 24 mesi,
  vista mensile; filtrabile per portafoglio o watchlist solo per gli abbonati. **Getquin**: calendario che somma
  ricevuti e annunciati. — [parqet dividend-calendar](https://parqet.com/blog/dividend-calendar),
  [getquin help 7836515](https://help.getquin.com/en/articles/7836515-dividend-calendar-estimation)
- **PP**: `EarningsChartWidget` e `EarningsByTaxonomyChartWidget` (earnings per mese, trimestre o anno, anche per
  tassonomia), "Upcoming dividends" (`DividendListWidget`), pagamenti cumulati (`PaymentsAccumulatedChartBuilder`). —
  [cartella earnings](https://github.com/portfolio-performance/portfolio/tree/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/dashboard/earnings),
  [payments](https://github.com/portfolio-performance/portfolio/tree/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/payments)
- **Richieste**: Wealthfolio #1420 "add more dividend stats and info" (3 👍); Ghostfolio #7468 Total Return con
  dividendi (6 👍). — [wealthfolio#1420](https://github.com/wealthfolio/wealthfolio/issues/1420),
  [ghostfolio#7468](https://github.com/ghostfolio/ghostfolio/issues/7468)

**H. Allocazione: treemap, sunburst/icicle, mappa del mondo, style box, attuale vs target**
- **PP, viste di tassonomia**:
  - torta, ciambella, treemap, area impilata (valori effettivi o %);
  - `RebalancingChartWidget`: barre "attuale", "target" e "delta" per categoria;
  - `RebalancingTargetChartWidget`.

  — [RebalancingChartWidget.java](https://github.com/portfolio-performance/portfolio/blob/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/dashboard/charts/RebalancingChartWidget.java)
- **Wealthfolio, "Allocation vs target"**:
  - colonne Current / Target / Drift;
  - "Largest gaps" con importo sopra o sotto il target;
  - ciambella con ▲▼ rispetto al target;
  - bande di tolleranza "hybrid" (proporzionale al peso, con minimo assoluto) o "absolute".

  — [allocation.json](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/i18n/locales/en/allocation.json),
  [insights.json (rails)](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/i18n/locales/en/insights.json)
- **Ghostfolio**:
  - componente `world-map-chart`, una mappa coropletica dei paesi;
  - pagina "X-ray" con regole di rischio: cluster per conto, classe, valuta, mercato economico e regione, fondo di
    emergenza, commissioni, liquidità.

  — [world-map-chart](https://github.com/ghostfolio/ghostfolio/tree/main/libs/ui/src/lib/world-map-chart),
  [rules](https://github.com/ghostfolio/ghostfolio/tree/main/apps/api/src/models/rules)
- **Fava**: Treemap, Sunburst e ora **Icicle** (`Icicle.svelte`, ultimo commit 3 nov 2026), su gerarchia di conti. —
  [Icicle.svelte](https://github.com/beancount/fava/blob/main/frontend/src/charts/Icicle.svelte)
- **Morningstar X-Ray** (snippet):
  - style box 3×3 (small/mid/large × value/blend/growth);
  - settori azionari e obbligazionari;
  - regioni (Americas, Greater Europe, Greater Asia, secondo Morningstar);
  - "Stock stats" (P/E, P/CF, P/B) confrontati con un benchmark.

  — [Morningstar Style Box (wikipedia)](https://en.wikipedia.org/wiki/Morningstar_Style_Box),
  [morningstar.co.uk reading the x-ray](https://morningstar.co.uk/uk/news/131918/reading-the-x-ray-tool.aspx),
  [datadef](https://portfolio.morningstar.com/instantxray/datadef.html)
- **Finary** (snippet): "score de diversification" geografica e settoriale da 1 a 10 (introdotto ad aprile 2023, solo
  settoriale), basato sull'X-Ray degli ETF. Gli utenti chiedono trasparenza sul calcolo e una torta per famiglie di
  asset. — [finary avril 2023](https://finary.com/fr/actualites-produit/avril-2023),
  [community finary](https://community.finary.com/t/importance-de-la-diversification-geographique/16087)

**I. Costi e commissioni nel tempo**
- **Empower, "Fee Analyzer"** (snippet di recensioni): confronta i costi annui con un riferimento dello 0,50% e mostra in
  rosso, su un grafico, quanto si perde in commissioni negli anni. Stima anche gli anni di pensione persi. —
  [mybanktracker](https://www.mybanktracker.com/blog/investing/personal-capital-review-310564),
  [choosefi](https://www.choosefi.com/empower-review)
- **Finary, "fee scanner"**: già annotato. PP ha la serie cumulata `FEES_ACCUMULATED` e la heatmap dei costi (vedi A e B).

**J. PAC e investimenti per mese**
- **PP**: `InvestmentHeatmapWidget`, una heatmap dei versamenti per mese. —
  [cartella heatmap](https://github.com/portfolio-performance/portfolio/tree/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/dashboard/heatmap)
- **Ghostfolio**: "Investment Timeline", già annotato. Non ho trovato un grafico PAC dedicato con prezzo medio di
  carico che scende, a parte la linea "purchase price/moving average" del grafico titolo di PP (punto E).

### Inferences
Tabella di sintesi per MFP. "MFP oggi" dice se MFP ce l'ha già. "Valore IT" è il valore per un utente italiano:
- ★★★ alto;
- ★★ medio;
- ★ basso, nicchia o gimmick.

| Grafico | Domanda a cui risponde | Dati che servono (in MFP) | Interazione consigliata | MFP oggi | Valore IT | Fattibilità Chart.js |
|---|---|---|---|---|---|---|
| Valore vs versato netto (area + linea) | "Quanto ho messo e quanto vale?" (il PAC) | serie giornaliera o mensile di quantità × prezzo (`HoldingPrice`) + somma dei versamenti; oggi c'è solo da Istantanee | tooltip con differenza € e %; filtro per conto e titolo | parziale (linea da Istantanee) | ★★★ | linea con `fill` |
| Heatmap mensile mesi × anni (+ colonna anno, + excess return vs benchmark) | "Quali mesi e anni sono andati bene? Ho battuto l'indice?" | TWR mensile (c'è già in `performance.py`) | clic sulla cella → movimenti e prezzi del mese; riga totale = rendimento composto | assente (c'è la heatmap delle spese in tabella CSS, riusabile) | ★★★ | tabella CSS come `summary.html`, oppure `chartjs-chart-matrix` |
| Underwater drawdown | "Quanto sono sotto il massimo, e da quanto?" | indice TWR giornaliero o mensile | area rossa sotto lo zero; etichetta del max DD con date di picco, minimo e recupero | assente (c'è solo il numero) | ★★★ (educativo, rassicura nei cali) | linea con `fill` sotto lo 0 |
| Prezzo del titolo con marcatori acquisto, vendita, dividendo e linea del prezzo medio di carico | "Ho comprato bene? Dov'è il mio prezzo medio?" | `HoldingPrice` + operazioni (`units`, `unit_price`) + prezzo medio ricalcolato nel tempo | punti triangolari ▲▼ e tooltip dell'operazione; zoom per periodo | linea del prezzo senza marcatori | ★★★ | scatter sovrapposto a line, `pointStyle: 'triangle'` |
| Waterfall della variazione (inizio → versamenti → rendite → plus/minus → cambi → commissioni → tasse/bollo → fine) | "Perché il patrimonio è cambiato?" | flussi già classificati (buy/sell/fee/dividend/coupon/tax), bollo e IVAFE calcolati, effetto cambio (oggi non separato) | clic sulla barra → movimenti di quella voce | assente ("Crescita del patrimonio" è impilata, non a cascata) | ★★★ (il bollo 2‰ e il 26% diventano visibili) | barre fluttuanti `[start,end]` |
| Attuale vs target (barre o bullet con banda di tolleranza) | "Cosa devo comprare?" | `PortfolioTemplate` con tolleranza (già c'è) | clic → proposta di ribilanciamento o PAC | barre HTML di scostamento (`highlights.html`) | ★★★ | barre orizzontali + `chartjs-plugin-annotation` per le bande |
| Treemap e sunburst di allocazione (classe → titolo, o area → paese) | "Dove è concentrato?" | tassonomie con pesi (già c'è) | clic per scendere di livello | solo ciambelle | ★★ | `chartjs-chart-treemap` |
| Mappa del mondo coropletica | "In che paesi sono esposto?" | pesi per paese (look-through ETF, oggi assente) | tooltip % | assente | ★ (senza look-through è inutile; con 1–3 ETF globali dice poco) | `chartjs-chart-geo` + TopoJSON locale |
| Style box 3×3 | "Sono growth o value, large o small?" | dati di capitalizzazione e stile per titolo (fonte Morningstar a pagamento) | – | assente | ★ (dati non disponibili gratis) | griglia CSS |
| Scatter rischio/rendimento | "Quale titolo rende di più per il rischio?" | volatilità e rendimento per titolo e benchmark (calcolabili) | clic sul punto → titolo | assente | ★★ (utente evoluto) | scatter nativo |
| Frontiera efficiente | "Che mix sarebbe ottimale?" | covarianze storiche, ottimizzazione | – | assente | ★ (gimmick per il retail: dipende dai dati passati) | scatter + linea |
| Matrice di correlazione | "Le mie posizioni si muovono insieme?" | rendimenti mensili per titolo | – | assente | ★ (1–4 ETF: matrice banale) | `chartjs-chart-matrix` o tabella CSS |
| Rendimenti mobili (1/3/5 anni) | "Quanto è stabile il rendimento?" | TWR mensile | – | finestre come numeri, non come grafico | ★★ | linea |
| Rendite: barre mensili + calendario + previsione 12 mesi + crescita YoY | "Quanto incasso e quando?" | dividendi e cedole storici; cedole BTP programmate (scadenza e cedola mancano nel modello) | clic sul mese → incassi | barre impilate per tipo + stima a 12 mesi | ★★ (★★★ per chi ha BTP) | barre esistenti + calendario server-side già scritto per Ritmo |
| Costi cumulati e "costo dei costi" (TER + commissioni + bollo nel tempo vs scenario senza costi) | "Quanto mi costano davvero?" | commissioni registrate, TER del fondo (da aggiungere), bollo calcolato | toggle "con o senza costi" | assente | ★★★ (fondi bancari e polizze cari sono il tema italiano) | due linee con area in mezzo |
| Heatmap dei versamenti (PAC per mese) | "Ho rispettato il PAC?" | buy per mese | clic → operazioni | assente | ★★ | tabella CSS |

- **La heatmap esiste già**: la heatmap mensile, la più richiesta in Wealthfolio (#1366) e presente in PP e Parqet,
  si può costruire con lo stesso meccanismo CSS di `reports/summary.html`, senza librerie nuove.
- **Il waterfall manca ovunque come grafico**. Sharesight lo fa in tabella, Wealthfolio con "Drivers of change", PP con
  serie cumulate. Un waterfall che mette in fila bollo, IVAFE e capital gain tax, già calcolati da MFP, sarebbe un
  differenziante specifico per l'Italia.
- **Il grafico del titolo arricchito** costa poco perché i dati ci sono già (operazioni + storico prezzi), ed è
  richiesto in Wealthfolio (#982).
- **Da evitare**: bande di Bollinger, MACD e medie mobili alla PP. Sono roba da trader, fuori target per un'app di
  finanza personale.

### Gaps
- **Pagine bloccate o non aperte**: Parqet (bloccato) e Getquin: nessuna descrizione dettagliata dei grafici di
  performance oltre agli snippet. Sito ufficiale di Portfolio Visualizer non consultato: frontiera e rolling solo da
  guide di terzi.
- **Rotki non analizzato** (nessun clone disponibile): ignoro i suoi grafici.
- **Koyfin non analizzato**: fuori target retail.
- **Grafico "yield on cost" nel tempo**: non ho trovato un grafico dedicato documentato. Getquin lo ha come metrica
  (note precedenti).
- **PP**: non ho verificato se il `DrawdownChartWidget` mostri le date di recupero.

---

## 2. Patrimonio netto: area impilata, attività vs passività, proiezione, debiti e mutuo

### Takeaway
Sul patrimonio il pattern che emerge nel 2026 è barre attività/passività con linea del netto (richiesto in Wealthfolio
#2231, quello che MFP fa già in dashboard), più tre aggiunte:
- **pannello "driver" della variazione** (Wealthfolio);
- **grafico del debito** con piano contrattuale, saldo reale, proiezione ed effetto dei pagamenti extra (Sure);
- **proiezione del patrimonio** con regole (Kubera Fast Forward, ProjectionLab, Finary).

MFP ha già quasi tutto il primo pezzo. Il guadagno maggiore sta nel grafico del debito/mutuo "contratto vs reale vs
extra" e nella vista per singolo conto.

### Cited Findings
- **Wealthfolio**:
  - #2231 "Net worth chart: show assets and liabilities as bars with net worth as a line" (22 ott 2026, 3 👍, aperta);
  - #2228 chiede importi completi invece di quelli compatti ("5.8K").

  La pagina Net Worth ha `net-worth-chart.tsx`, `category-trend-chart.tsx`, `composition-bar.tsx`, `momentum-card.tsx`
  e una "breakdown table". — [#2231](https://github.com/wealthfolio/wealthfolio/issues/2231),
  [#2228](https://github.com/wealthfolio/wealthfolio/issues/2228),
  [pages/net-worth](https://github.com/wealthfolio/wealthfolio/tree/main/apps/frontend/src/pages/net-worth)
- **Sure, `loan_payoff_chart_controller.js`**: il grafico del saldo del prestito ha quattro serie:
  - "actual", il saldo registrato, solido;
  - "scheduled", il contratto originale fino a scadenza, tratteggiato;
  - "projected", dove porta il saldo di oggi con la rata del contratto;
  - "extra", la proiezione con un importo extra a ogni rata, attiva dalla scheda "Extra repayments".

  La issue collegata #3332 "Track actual vs. scheduled loan payoff" è chiusa (set 2026). —
  [loan_payoff_chart_controller.js](https://github.com/we-promise/sure/blob/main/app/javascript/controllers/loan_payoff_chart_controller.js),
  [#3332](https://github.com/we-promise/sure/issues/3332)
- **Sure, `goal_projection_chart_controller.js`**: per l'obiettivo, area del risparmiato fino a oggi, linea
  tratteggiata di proiezione fino alla data obiettivo (gialla se in ritardo, verde se in linea), linea orizzontale del
  target e marcatore "oggi". — [goal_projection_chart_controller.js](https://github.com/we-promise/sure/blob/main/app/javascript/controllers/goal_projection_chart_controller.js)
- **Monarch** (snippet):
  - la pagina ufficiale parla di report su assets, liabilities e net worth filtrabili e di snapshot giornalieri dei
    saldi;
  - un post Reddit (mar 2026, mirror) lamenta la scomparsa dei grafici "Assets only / Liabilities only" e per gruppi
    di conti (Cash, Credit Cards, Vehicles), sostituiti da "net worth breakdown" e "net worth performance".

  Il secondo è un singolo utente, non un annuncio ufficiale. —
  [monarch net-worth](https://www.monarch.com/landing/net-worth),
  [mirror reddit MonarchMoney](https://reddit.sentinel-team.org/subreddits/MonarchMoney/snapshots/2026-03-25T18%3A59%3A48.582722Z)
- **Kubera, "Fast Forward"** (help ufficiale, snippet):
  - proiezione del patrimonio con regole modificabili;
  - clic su un punto del grafico per vedere come è calcolato;
  - solo nel piano Black, in conflitto con una recensione che lo dà nel piano Essentials;
  - una recensione dice che i calcoli degli scenari non sono corretti.

  — [help.kubera Fast Forward](https://help.kubera.com/article/110-what-is-the-fast-forward-feature),
  [jeangalea review](https://jeangalea.com/kubera-review)
- **ezBookkeeping**:
  - andamento dei saldi del conto come area, area smussata, colonne, **boxplot** o **candlestick**;
  - dati "Account Total Assets/Liabilities", "Total Assets/Liabilities By Currency", "Net Worth";
  - aggregazione giornaliera, mensile, trimestrale, annuale o per anno fiscale.

  — [statistics.ts](https://github.com/mayswind/ezbookkeeping/blob/main/src/core/statistics.ts)
- **Finary** (snippet): grafico del patrimonio settimanale, mensile o globale con plusvalenze latenti e prestiti;
  simulazione "votre patrimoine dans 30 ans". — [sinvestir test-finary](https://sinvestir.fr/test-finary),
  [finary simulation](https://finary.com/simulation)

### Inferences
- **Barre attività/passività + linea del netto**: MFP le ha già in dashboard ("Andamento del patrimonio"). Wealthfolio
  #2231 conferma che è il formato giusto, niente da cambiare.
- **Debiti e mutuo**: MFP ha oggi solo una linea del piano di ammortamento. Va portato lo schema di Sure:
  - contratto (tratteggiato), saldo reale e proiezione con estinzione anticipata;
  - più, per il mutuo italiano, barre impilate quota capitale/quota interessi per anno.

  È ★★★: estinzione anticipata e surroga sono decisioni comuni, e gli interessi passivi del mutuo prima casa
  sono detraibili al 19% (dato non verificato in questa sessione, da confermare con la parte Fisco).
- **Proiezione dell'obiettivo**: va portato lo schema di Sure (passato solido, futuro tratteggiato colorato per stato,
  linea target). MFP oggi ha solo barre di avanzamento.
- **Vista per singolo conto**: oggi manca un grafico del saldo per conto (inventario). Area semplice, ★★.
- **Boxplot e candlestick dei saldi** (ezBookkeeping): gimmick ★, poco leggibili per l'utente medio.
- **Grafici del patrimonio di Monarch**: la rimozione delle viste per gruppo di conti, se confermata, suggerisce di
  tenere in MFP un filtro "solo attività / solo passività / per tipo di conto".

### Gaps
- Kubera e Monarch: nessuna pagina ufficiale aperta sui tipi di grafico (siti non consultabili o solo snippet).
- Copilot: nessun dato nuovo su "net worth stacked by account type" oltre alle note precedenti.
- Detraibilità degli interessi del mutuo: non verificata qui.

---

## 3. Pianificazione: FIRE, Monte Carlo, probabilità di successo, eventi di vita, crossover

### Takeaway
I planner maturi (Wealthfolio v3, ProjectionLab, Boldin) affiancano al ventaglio Monte Carlo grafici più eloquenti:
- **traiettoria "proiettato vs necessario"**;
- **area impilata della copertura della spesa** (rendite, prelievi dal portafoglio, non coperto);
- **traguardi Lean/FI/Fat/Coast FIRE**;
- **stress test e tempi del crollo** (rischio di sequenza);
- **Sankey del flusso di cassa per anno futuro** (ProjectionLab).

MFP ha già 3 linee percentili. Il salto di qualità sta in quattro cose:
- banda 10–90 riempita;
- linea "necessario";
- area di copertura (pensione INPS + prelievo + scoperto);
- tabella o grafico "cosa sposta il piano".

### Cited Findings
- **Wealthfolio v3, Retirement planner**. Testi in `goals.json`:
  - **"Portfolio trajectory"**: linea solida "Projected" e tratteggiata "Required", cioè il minimo necessario a ogni
    età per finanziare la spesa; marcatore dell'età di pensione o della prima età FI sostenibile; obiettivi di
    risparmio come marcatori alla loro data.
  - **"Retirement spending coverage"**: area impilata per fonte (rendite, "Portfolio withdrawal", "Withdrawal taxes",
    "Unfunded"), con la spesa pianificata tratteggiata; vista "At retirement" e "Over time"; tasso di prelievo per anno.
  - **Milestone**: Coast FIRE, Lean FIRE (70% della spesa), FI, Fat FIRE (150%).
  - **Scheda "What If"**:
    - "Market paths": ombreggiatura 10°–90° percentile e mediana;
    - "Stress tests": rendimenti più bassi, inflazione più alta, spesa maggiore, pensione anticipata, meno
      risparmio, crollo vicino alla pensione;
    - "What moves the plan?": verde/ambra/rosso rispetto al piano base;
    - "Early market crash paths": un crollo nel primo anno di pensione pesa più dello stesso crollo dopo.
  - **Interruttore "Today's value"**: valori reali o nominali.

  — [goals.json](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/i18n/locales/en/goals.json),
  [retirement-planner/components](https://github.com/wealthfolio/wealthfolio/tree/main/apps/frontend/src/features/goals/retirement-planner/components)
- **Ghostfolio, FIRE calculator**: barre impilate per anno "Deposit", "Savings", "Interest" fino alla data obiettivo,
  e un testo "If you retire today, you would be able to withdraw … per year/month" con safe withdrawal rate
  selezionabile. Bug segnalato: #3091 "[BUG] FIRE calculation" (3 👍, chiusa). —
  [fire-calculator.component.ts](https://github.com/ghostfolio/ghostfolio/blob/main/libs/ui/src/lib/fire-calculator/fire-calculator.component.ts),
  [fire-page html](https://github.com/ghostfolio/ghostfolio/tree/main/apps/client/src/app/pages/portfolio/fire),
  [#3091](https://github.com/ghostfolio/ghostfolio/issues/3091)
- **PP, `FIREWidget`**: widget testuale e numerico, senza grafico, con FIRE number (default 1.500.000), risparmio
  mensile, TTWROR (default 7%), tempo al FIRE (limite 50 anni) e data obiettivo. —
  [FIREWidget.java](https://github.com/portfolio-performance/portfolio/blob/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/dashboard/FIREWidget.java)
- **ProjectionLab** (snippet, sito bloccato):
  - Sankey del flusso di cassa che si estende agli anni futuri della simulazione, in cui si sceglie l'anno;
  - Monte Carlo e "Chance of Success" nel piano gratuito, mentre le proiezioni di cash flow e le tasse stanno nel
    Premium (le recensioni sono in conflitto su prezzi e piani);
  - una help page dedicata a "Actual vs Today's currency" e Chance of Success.

  — [projectionlab sankey-visualization](https://projectionlab.com/blog/sankey-visualization),
  [projectionlab inflation-in-chance-of-success](https://projectionlab.com/help/inflation-in-chance-of-success),
  [financialsamurai review](https://www.financialsamurai.com/?p=295100)
- **Boldin** (fonti ufficiali, snippet):
  - grafico con proiezione lineare e Monte Carlo insieme, dove il Monte Carlo fa da vista prudente e segnala l'anno
    in cui i risparmi finirebbero;
  - grafico "lifetime income" con i prelievi netti (2021);
  - circa 1.000 simulazioni; "82%" significa 820 scenari su 1.000 con soldi rimasti;
  - Safe Spending Target all'80% di successo, con guardrail 95% e 70% per i pensionati;
  - nuovo modello Monte Carlo correlato tra conti, che può abbassare il punteggio.

  — [boldin monte-carlo](https://www.boldin.com/retirement/monte-carlo-simulations-predict-your-chance-of-financial-success/),
  [boldin understanding MC](https://www.boldin.com/retirement/understanding-boldins-monte-carlo-simulation-what-it-is-why-it-matters-and-whats-new/),
  [robberger Boldin review](https://robberger.com/?p=5431)
- **Kitces**: un 80% di successo Monte Carlo su 30 anni per una coppia di 65enni corrisponde a oltre il 96% di
  probabilità complessiva, se si considera la longevità. La percentuale "nuda" va quindi spiegata. —
  [kitces](https://kitces.com/?p=285)
- **Empower** (recensioni): Retirement Planner con Monte Carlo; Investment Checkup che confronta l'allocazione attuale
  con quella raccomandata (storico, risparmio pensionistico proiettato, rischio). —
  [mybanktracker](https://www.mybanktracker.com/blog/investing/personal-capital-review-310564),
  [roboadvisorpros](https://www.roboadvisorpros.com/a-review-of-empowers-free-tools/)
- **Snowball, "Reaching the target"**: curva dell'obiettivo di rendita con tre scenari (con versamenti, senza, solo
  reinvestimento). È una forma di "crossover" della rendita passiva (vedi sez. 1G). —
  [snowball overview](https://snowball-analytics.com/blog/snowball-analytics-overview)
- **Actual**: ha report "Crossover" e Monte Carlo (FIRE), già annotati in `concorrenti_grafici_sezioni.md`.

### Inferences
| Grafico | Domanda | Dati MFP | MFP oggi | Valore IT | Nota |
|---|---|---|---|---|---|
| Ventaglio Monte Carlo con banda riempita 10–90 (e 25–75) + mediana | "Quanto è incerto il futuro?" | c'è già in `forecast/retirement.html` | 3 linee | ★★★ | basta `fill: '-1'` tra le linee: il cambio è minimo |
| Linea "necessario" sovrapposta alla traiettoria | "Sono in anticipo o in ritardo?" | spesa pianificata, orizzonte | assente | ★★★ | concetto di Wealthfolio, molto chiaro |
| Area impilata della copertura della spesa in pensione (pensione INPS, fondo pensione, affitti, prelievo, scoperto) | "Chi paga le mie spese a 70 anni?" | serve la stima della pensione pubblica (oggi assente) | assente | ★★★ | per l'Italia la pensione INPS è la fonte principale: grafico molto utile |
| Probabilità di successo (numero e gauge) | "Ce la faccio?" | dal Monte Carlo | da verificare | ★★ | meglio numero + frase che un gauge; spiegare cosa significa (Kitces) |
| Traguardi Lean/Coast/FI/Fat FIRE sulla traiettoria | "A che punto sono?" | patrimonio, spesa | assente | ★★ | nicchia FIRE, ma costa poco (linee orizzontali con annotazioni) |
| Stress test e "cosa sposta il piano" (barre ± rispetto al base, tipo tornado) | "Quale ipotesi conta di più?" | rilanciare il modello con ipotesi variate | assente | ★★ | più utile del ventaglio per decidere |
| Rischio di sequenza (crollo in anno 1 vs 10) | "E se crolla appena vado in pensione?" | simulazione deterministica | assente | ★ (educativo) | da mettere in "What If", non in prima pagina |
| Sankey del flusso di cassa per anno futuro | "Come si muove il denaro nel 2040?" | previsioni + Sankey server-side esistente | Sankey solo storico | ★★ | riusa `sankey.py` con l'anno scelto |
| Crossover rendita passiva vs spese | "Quando le rendite coprono le spese?" | rendite 12 mesi, spese medie, crescita | assente | ★★ | due linee che si incrociano, facile |
| Timeline degli eventi di vita sulla proiezione | "Cosa succede se compro casa nel 2029?" | `SpendingEvent` già esistente | assente sul grafico | ★★★ | marcatori verticali (`chartjs-plugin-annotation`) sulla previsione |
| Trend del tasso di risparmio | "Risparmio di più nel tempo?" | c'è già | presente (dashboard) | – | già coperto |

- **Il gauge di probabilità è il più "gimmick"**: un numero nudo crea falsa precisione (Kitces, e Boldin che cambia
  modello e abbassa i punteggi). Una frase con banda e scenario prudente comunica meglio.

### Gaps
- ProjectionLab: grafici della "life events timeline" e del net worth projection non verificati sul sito (bloccato).
- Boldin: nessuna descrizione verificata dei singoli grafici oltre agli snippet.
- Empower: nessun dettaglio grafico verificato dell'Investment Checkup.
- Pensione INPS: non ho cercato fonti dati o simulatori (fuori ambito grafici).

---

## 4. Cosa apprezzano davvero gli utenti, e cosa è gimmick

### Takeaway
Le reazioni GitHub sui grafici sono poche in assoluto. La maggior parte dei 👍 va a bug di calcolo o rendering e alla
fiducia nei numeri, non a nuovi tipi di grafico. Le richieste di grafici con segnale vero sono:
- heatmap mensile per anno;
- operazioni sul grafico del titolo;
- barre attività/passività + linea del netto;
- capitale versato accanto al valore;
- look-through dell'allocazione.

Gli strumenti da analista (frontiera, correlazioni, indicatori tecnici, style box) non hanno richieste negli OSS.

### Cited Findings
- **Wealthfolio**, issue di grafico più votate (9 nov 2026):
  - #1366 heatmap mensile per anno (6 👍);
  - #982 buy/sell sul grafico del titolo (5 👍);
  - #2231 attività/passività a barre con linea del netto (3 👍);
  - #1420 statistiche dividendi (3 👍);
  - #1318 e #1319 più conti nello stesso grafico (1 👍 ciascuna).

  — [ricerca issue wealthfolio "chart"](https://github.com/wealthfolio/wealthfolio/issues?q=is%3Aissue+chart+sort%3Areactions-%2B1-desc)
- **PP**, issue "chart":
  - #1921 nuovo design UI (22 👍);
  - #1665 look-through ETF (14 👍);
  - #2193 il grafico "Holdings" non si disegna (14 👍);
  - #1790 heatmap vuote su Linux (18 👍);
  - #1544 "Allow other performance indicators" nei grafici (5 👍, chiusa);
  - #4279 MWRR (3 👍);
  - #1238 "Rebalancing durch Zukauf" (4 👍).

  — [ricerca issue PP](https://github.com/portfolio-performance/portfolio/issues?q=is%3Aissue+chart+sort%3Areactions-%2B1-desc),
  [#1544](https://github.com/portfolio-performance/portfolio/issues/1544),
  [#1238](https://github.com/portfolio-performance/portfolio/issues/1238)
- **Ghostfolio**: le issue "chart" più votate sono bug (dati mancanti, cambi, grafico della home sbagliato #3072); come
  richiesta c'è #1447 "month to month performances" (1 👍). —
  [#3072](https://github.com/ghostfolio/ghostfolio/issues/3072), [#1447](https://github.com/ghostfolio/ghostfolio/issues/1447)
- **Sure**: la #1313 "Treat investment contributions as transfers instead of expenses in Reports" (3 👍) mostra che i
  versamenti negli investimenti che sporcano i grafici delle spese sono un problema sentito. Lo conferma Wealthfolio
  #2257 (chiusa). — [sure#1313](https://github.com/we-promise/sure/issues/1313),
  [wealthfolio#2257](https://github.com/wealthfolio/wealthfolio/issues/2257)
- **Leggibilità**: Wealthfolio #2478 (asse Y fuorviante) e Monarch (metà del grafico vuota, snippet). —
  [#2478](https://github.com/wealthfolio/wealthfolio/issues/2478)

### Inferences
**Priorità per MFP**, in ordine di rapporto valore/costo:
1. Heatmap mensile del rendimento (CSS esistente).
2. Grafico del titolo con marcatori delle operazioni e prezzo medio di carico.
3. Valore vs versato ricostruito da prezzi × quantità, non più solo da Istantanee.
4. Underwater drawdown.
5. Waterfall della variazione con tasse e bollo italiani.
6. Barre attuale vs target con bande.
7. Ventaglio Monte Carlo riempito + linea "necessario" + copertura con la pensione pubblica.
8. Debito/mutuo contratto vs reale vs estinzione anticipata, con capitale/interessi.
9. Eventi di vita come marcatori sulla previsione.
10. Treemap.

**Gimmick o bassa priorità**:
- indicatori tecnici (SMA, EMA, Bollinger, MACD);
- frontiera efficiente;
- matrice di correlazione per 2–4 ETF;
- style box senza dati;
- mappa del mondo senza look-through;
- gauge di probabilità;
- boxplot e candlestick dei saldi;
- radar.

**Fattibilità tecnica**: le estensioni Chart.js necessarie esistono tutte, con licenza MIT, e si possono includere in
locale come l'attuale `chart.umd.min.js`. Versioni dal registro npm, 9 nov 2026:

| Estensione | Versione | Data | Richiede chart.js |
|---|---|---|---|
| `chartjs-chart-treemap` | 4.2.2 | 6 set 2026 | >=3 |
| `chartjs-chart-matrix` | 3.1.0 | 12 set 2026 | – |
| `chartjs-chart-sankey` | 0.19.1 | – | – |
| `chartjs-chart-geo` | 4.3.6 | ott 2025 | ^4.1 |
| `chartjs-plugin-annotation` | 3.1.0 | – | >=4 |
| `chartjs-chart-financial` | 0.2.1 | mar 2024 | – |

Fonte: [registry.npmjs.org](https://registry.npmjs.org/chartjs-chart-treemap). Waterfall e marcatori non richiedono
plugin: bastano barre fluttuanti e uno scatter sovrapposto.

### Gaps
- Nessun voto dai prodotti SaaS (bacheche Parqet canny, ProjectionLab e Monarch non consultabili). Il "cosa amano gli
  utenti" sui commerciali resta senza numeri.
- Reddit e forum italiani (es. Finanza Online) non consultati per motivi di rete.
- I conteggi 👍 sono bassi (≤ 22): sono un segnale debole, non una classifica robusta.
