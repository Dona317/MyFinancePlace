# Fonti di prezzi di fine giornata (EOD): ultimo prezzo e storico giornaliero

Ricerca del 9 novembre 2026, per F43, F47 e D10. Le domande sono due: da dove MyFinancePlace (app desktop
Python/Flask, senza un server proprio, per utenti italiani) può prendere **chiusura e storico giornaliero** di ETF e
azioni (Borsa Italiana, XETRA, Euronext), BTP e obbligazioni del MOT e fondi comuni per ISIN; e cosa offrono davvero
**Morningstar** e **investing.com**.

**Limite di metodo.** Dalla sandbox **nessuno di questi siti è raggiungibile**: Yahoo, Stooq, Morningstar,
investing.com, FT, justETF, BCE, EODHD e Twelve Data hanno tutti rifiutato la connessione (proxy, 9 nov 2026), e
manca perfino la risoluzione DNS. Quindi nulla di quello che segue è stato provato da me dal vivo. I fatti vengono
dal **codice sorgente** e dalle **issue GitHub** di progetti attivi in ottobre e novembre 2026, ognuno con la sua
data. Dove riporto un ricordo non verificato (termini d'uso, prezzi dei piani) lo scrivo.

---

## 0. Cosa fa oggi l'app (letto in `test-Cloud`, senza modificarlo)

- `app/services/price_feed.py`
  - Yahoo: `query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=…&interval=…`. Prezzo da
    `meta.regularMarketPrice`; con meno di 5 punti salvati (`HISTORY_POINTS`) chiede **1 anno di chiusure
    settimanali** (`range=1y&interval=1wk`). Il benchmark (F20) legge 10 anni di chiusure mensili. User-Agent fisso
    `Mozilla/5.0 MyFinancePlace`.
  - Stooq: solo l'ultima quotazione, `stooq.com/q/l/?s=…&f=sd2t2ohlcv&h&e=csv`, e solo per le borse US/DE/UK/JP/HK
    (Stooq non ha Milano).
  - CoinGecko: `simple/price` in euro.
  - Ogni prezzo viene convertito **subito in euro** con i cambi salvati (`_to_euro`). Se il cambio manca, il punto
    di storico viene saltato.
- `app/services/instrument_sources/`: un modulo per sito, con `find(isin)` e `quote(isin) -> Quote(price, on,
  currency)`. Le richieste sono distanziate di almeno 1 secondo per sito; quando una pagina cambia, l'errore è
  `Broken`.
  - `morningstar.py`: `www.morningstar.it/it/util/SecuritySearch.ashx?q={isin}` per l'id, poi la pagina
    `funds/snapshot/snapshot.aspx?id=…`, da cui una regex prende **solo l'ultimo NAV** e la sua data.
  - `justetf.py`: `api/etfs/{isin}/quote` (ultimo prezzo in EUR).
  - `borsaitaliana.py`: la pagina della ricerca, poi la scheda; si legge «Prezzo ultimo contratto». Per le
    obbligazioni il prezzo è diviso per 100.
  - `openfigi.py`: da ISIN a ticker con suffisso Yahoo.
  - `custom.py`: fonte definita dall'utente (JSON, HTML o CSV); prende solo l'ultimo valore.
- `HoldingPrice` (`holding_prices`): `holding_id`, `on`, `price` (in euro), `note`, `estimated`, con unicità su
  (holding, on). Non ci sono colonne per **fonte, valuta d'origine, cambio o rettifica**. Le aggiunge F43 (prezzo in
  valuta, valuta, cambio).
- I cambi BCE (`currency.py`) si scaricano da `eurofxref-daily.xml` o `eurofxref-hist-90d.xml`, quindi coprono **solo
  90 giorni**. Con l'architettura di oggi, uno storico in USD o GBP più vecchio di 90 giorni verrebbe scartato.
- D10 (proposta): Yahoo per uso personale, Stooq, CSV e prezzi a mano, chiave dell'utente facoltativa, nessuno
  scraping nuovo senza aver letto ToS e robots.txt.

**Tre segnali d'allarme sul codice di oggi** (vanno provati sul PC dell'utente):
1. **Morningstar**: `SecuritySearch.ashx` di morningstar.fr risponde con un redirect 301/302 a
   `global.morningstar.com/fr/`, e le pagine di global.morningstar.com sono dietro una sfida AWS WAF (HTTP 202,
   `x-amzn-waf-action: challenge`). Lo riporta fonrex #39 del 28 ott 2026. È molto probabile che `morningstar.it`
   abbia seguito la stessa migrazione, e allora `morningstar.py` sarebbe **già rotto**.
2. **Stooq**: secondo segnalazioni del 13 e 24 ott 2026, `/q/l/` dà **404** per ogni simbolo e `/q/d/l/` mostra una
   pagina di verifica JavaScript. Da marzo 2026 serve anche una **chiave API** (vedi §3.2). La riserva Stooq di
   `price_feed` quasi certamente non risponde più.
3. **Yahoo**: dal 2025 Yahoo limita i client senza l'impronta TLS di un browser (yfinance è passato a `curl_cffi`).
   Con `urllib` funziona ancora per pochi titoli al giorno? Va verificato.

---

## 1. Morningstar: storico dei NAV

### 1.1 L'endpoint «classico» `timeseries_price` (senza autenticazione)

È lo stesso che PP documenta per il suo feed JSON generico e che usano decine di progetti:

```
https://<host>/api/rest.svc/timeseries_price/<token>
    ?id=<SecId>]2]0]            (oppure ]2]1], vedi sotto)
    &idtype=Morningstar
    &frequency=daily            (daily | weekly | monthly)
    &startDate=YYYY-MM-DD       (facoltativi: endDate, currencyId=EUR)
    &outputType=COMPACTJSON     (oppure JSON)
```

- **Formato.** `COMPACTJSON` restituisce `[[epoch_ms, valore], …]`. `JSON` restituisce
  `TimeSeries.Security[*].HistoryDetail[*].{EndDate, Value}`: sono i JSONPath della guida PP. Gli errori arrivano in
  XML.
  ([guida PP «morningstar»](https://github.com/portfolio-performance/portfolio-help/blob/main/docs/en/how-to/downloading-historical-prices/morningstar.md),
  lastUpdate 2023-09-13; [pofo morningstar.go](https://github.com/bpineau/pofo/blob/main/pkg/marketdata/morningstar.go), 8 nov 2026)
- **Host, al 2026.** I vecchi `tools.morningstar.<paese>` stanno sparendo:
  - `tools.morningstar.co.uk` non ha più record A/AAAA dal **21–22 ago 2026**: i NAV di beancounter sono fermi da
    allora. La sostituzione verificata è **`lt.morningstar.com`**, con lo stesso path, lo stesso token e la stessa
    forma JSON.
    ([beancounter #1097](https://github.com/monowai/beancounter/issues/1097), 29 ago 2026;
    [MorningstarConfig.kt](https://github.com/monowai/beancounter/blob/main/svc-data/src/main/kotlin/com/beancounter/marketdata/providers/morningstar/MorningstarConfig.kt), 7 nov 2026)
  - Anche `tools.morningstar.fr` «had lost its DNS A record»; pofo l'ha riparato il 22 ago 2026 passando a
    `lt.morningstar.com`. ([pofo trend-reconstruction-design.md](https://github.com/bpineau/pofo/blob/main/docs/specs/trend-reconstruction-design.md))
  - Per `tools.morningstar.it` (token `jbyiq3rhyf`, usato da AlexanderItaly/inflation_analysis) non ho prove né in
    un senso né nell'altro: è **da provare**, ma conviene puntare subito su `lt.morningstar.com`.
- **Token.** Sono «view id» pubblici incorporati nelle pagine grafico di Morningstar, non chiavi personali. Nel
  codice ho trovato: `t92wz0sj7c` (UK, usato da beancounter su lt.), `ok91jeenoo` (pofo: «stable for years»),
  `hvqzxf7smz`, `swfjds4ofs`, `2nhcdckzon` (ES), `n4omw1k3rh` (SE), `dr6pz9spfi` (NO), `jbyiq3rhyf` (IT). Possono
  essere revocati senza preavviso: il token va tenuto in configurazione, non scritto nel codice.
- **Suffisso dell'id.** Per un id di ETF o di titolo quotato (`0P…`), senza i due campi finali la risposta è un
  **array vuoto con HTTP 200**. Con `]2]1]` arriva lo storico completo; per un fondo (`F0…`) il suffisso non dà
  fastidio. ([pofo morningstar.go](https://github.com/bpineau/pofo/blob/main/pkg/marketdata/morningstar.go))
- **Cosa contiene la serie.** È un rendimento di **prezzo**: la classe a distribuzione non include i dividendi
  pagati. Esiste anche `timeseries_cumulativereturn`, che dà il rendimento totale (pofo l'ha misurato ma non lo usa).
  La **valuta non è indicata** nella risposta. Su un fondo, i livelli di Morningstar e di FT divergevano fino al 13 %:
  pofo usa FT come riferimento per quel fondo. (pofo, documento citato sopra)
- **Da ISIN a SecId.** Il vecchio `www.morningstar.<paese>/<lang>/util/SecuritySearch.ashx?q=` (il formato
  `nome|{json}|…` letto da `morningstar.py`) per morningstar.fr ora **reindirizza** a global.morningstar.com
  ([fonrex #39](https://github.com/fonrex/fonrex/issues/39), 28 ott 2026). Al suo posto si usa lo screener sullo
  stesso host:
  ```
  https://lt.morningstar.com/api/rest.svc/klr5zyak8x/security/screener
      ?page=1&pageSize=10&outputType=json
      &universeIds=FOALL$$ALL|ETALL$$ALL
      &securityDataPoints=SecId|Name|isin|currencyId
      &term=<ISIN>
  ```
  Risponde con `rows[]` che contengono `SecId`, `Name`, `isin` e `currencyId` (nella forma `CU$$$$$EUR`). La riga in
  cui `isin` coincide esattamente va scelta prima delle altre. È ricerca «senza autenticazione, su HTTP semplice»,
  verificata da pofo il 22 ago 2026. fonrex vede la stessa ricerca servita con il token `9vehuxllxs`.
  Un'alternativa sono gli id `0P…` della ricerca di Boursorama (pofo `boursorama.go`).

### 1.2 Le API «nuove» (global.morningstar.com, api-global, us-api): non adatte

- **mstarpy** (Mael Pochet), versione 11.1.2 del 7 nov 2026, **ora dipende da Selenium**. Apre
  `global.morningstar.com` in un browser vero per avere i cookie AWS WAF, poi ricava un **bearer token** (JWT
  `eyJ…`, il «maasToken») dalla pagina `www.morningstar.com/funds/xnas/afozx/chart` e chiama
  `www.us-api.morningstar.com/QS-markets/chartservice/v2/timeseries?query=<SecId>:nav,totalReturn&frequency=d&startDate=…`.
  I dati anagrafici passano da `api-global.morningstar.com/sal-service/v1/…` con un'`apikey` statica.
  ([mstarpy security.py e search.py](https://github.com/Mael-J/mstarpy), commit 6978ec5 del 7 nov 2026)
- **Quanto si rompe** (issue di mstarpy, 2026):
  - #39 (13 mar): errore 202 «Accepted», cioè la sfida WAF.
  - #43 (10 apr): 403 sullo storico dei prezzi.
  - #44 (13 apr): «Mstarpy no longer working».
  - #45 (5 giu): lo screener chiede il **login** (401).
  - #46 (20 giu): cambia il formato delle risposte.
  - #49 (27 lug): 403 se il browser è headless.
  - #50 (15 ott): token non valido dal 7 ott.
  - #52 (7 nov): token non più trovato nell'HTML dal 5 nov.

  Sono **25 rilasci tra ott 2024 e nov 2026** (PyPI), molti di adattamento.
- **Conclusione.** Per un'app desktop vorrebbe dire includere un browser o uno Chrome headless e inseguire una rottura
  al mese. Da escludere.

### 1.3 Termini d'uso Morningstar

Non ho potuto leggere i termini dal vivo. Da ricordo, non verificato: i termini dei siti Morningstar vietano la
raccolta automatizzata e la ridistribuzione dei dati, e `timeseries_price` non è un'API pubblicata. Nessun progetto
tra quelli letti cita un permesso. PP non ha un feed Morningstar integrato: offre solo la **ricetta** per il feed
JSON generico, che configura l'utente. Ha soltanto un segnalibro `morningstar.de` in `ClientSettings.java`. È il
modello da imitare: fonte **scelta e attivata dall'utente**, per uso personale.

**Giudizio su Morningstar.** Per lo storico dei NAV dei fondi per ISIN è la fonte migliore che esista senza chiave,
**a condizione** di usare `lt.morningstar.com` (screener + `timeseries_price`), di tenere token e host in
configurazione e di avere una riserva (FT, §3.5). Il rischio di rottura è medio-alto (due host spenti in agosto
2026), il rischio sui termini d'uso è medio.

---

## 2. investing.com

- **investpy è abbandonato**: ultimo rilascio 1.0.8 del 24 gen 2022. Il README stesso dice che «is not working fine
  currently… use investiny». Le issue restano aperte senza risposta: #644 (gen 2026), #646 (lug 2026). Anche
  **investiny** è fermo alla 0.7.2 del 18 ott 2022 (PyPI).
- **Endpoint usati nel 2026:**
  - storico: `https://api.investing.com/api/financialdata/historical/<pair_id>?start-date=YYYY-MM-DD&end-date=…&time-frame=Daily&add-missing-rows=false`,
    con l'header obbligatorio **`domain-id: www`** (o `it`). Risponde con `data[]` che contiene `rowDateTimestamp`
    e `last_closeRaw`. Al massimo **circa 5000 righe** per richiesta, quindi lo storico va scaricato a finestre.
    ([au-econ investing.py](https://github.com/bpalmer4/au-econ/blob/main/src/au_econ/sources/investing.py), 9 nov 2026)
  - da ISIN, nome o ticker a `pair_id` («cid»): la vecchia `api.investing.com/api/search/v2/search?q=` «still
    answers 200 but its `quotes` array is permanently empty». Quella nuova è
    `https://endpoints.investing.com/pd-instruments/v1/instruments/search?query=<q>&domain_id=1`, il catalogo
    internazionale, che «already covers Italian bonds and funds».
    ([FinanceCopilot web_market_data_service.dart](https://github.com/marcobazzani/FinanceCopilot), 31 ott 2026)
- **Cloudflare.** Tutto è dietro la protezione bot di Cloudflare. I progetti che funzionano oggi usano:
  - `curl_cffi` che imita l'impronta TLS di Chrome (au-econ, nov 2026);
  - una **WebView headless** che risolve la sfida e aspetta il cookie `cf_clearance` (FinanceCopilot, app desktop
    Flutter di uno sviluppatore italiano);
  - Playwright (lo script di FinanceCopilot).

  `cloudscraper` non compare nei progetti recenti che ho letto. Con il semplice `urllib` dell'app non funzionerebbe.
- **Termini d'uso.** Non ho potuto leggerli dal vivo. Da ricordo, non verificato: vietano scraping e accesso
  automatizzato e riservano i dati, che in parte arrivano da terzi. È significativo che FinanceCopilot **nasconda il
  nome** del fornitore nel codice (`kProviderHost`, «the market data provider») pur usando investing.com.
- **Giudizio onesto.** La copertura è eccellente (BTP, fondi italiani, ETF su tutte le borse) e lo storico è lungo,
  ma per un'app desktop distribuita è **la fonte meno affidabile e più rischiosa**. Serve aggirare Cloudflare (nuova
  dipendenza binaria, `curl_cffi`, o un browser incorporato). La ricerca è già cambiata senza preavviso nel 2026, e
  l'uso automatizzato è con ogni probabilità vietato. **Sconsigliato come fonte integrata.** Se proprio serve, solo
  come fonte personalizzata (F22) che l'utente configura da sé, sapendo che è fragile.

---

## 3. Alternative per lo storico europeo

### 3.1 Yahoo Finance (chart v8): resta la fonte principale per i titoli quotati

- **Endpoint**: `query1.finance.yahoo.com/v8/finance/chart/<TICKER>?range=<r>&interval=1d`, oppure con `period1` e
  `period2` in epoch. PP sceglie `range` in base ai giorni mancanti: 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, 20y, 30y. Il
  commento dice **«"max" only returns a sample of quotes»**. User-Agent casuale `Mozilla/5.0 (<6 cifre>)`, senza
  crumb. ([YahooFinanceQuoteFeed.java](https://github.com/portfolio-performance/portfolio/blob/master/name.abuchen.portfolio/src/name/abuchen/portfolio/online/impl/YahooFinanceQuoteFeed.java), clone del 7 nov 2026)
- **Suffissi**: `.MI` (Borsa Italiana, ETFplus), `.DE` (XETRA), `.F` (Francoforte), `.PA`, `.AS`, `.BR`, `.LS`
  (Euronext), `.L` (Londra, spesso in GBp), `.SW`. I fondi comuni europei hanno spesso simboli `0P0000XXXX.F` (id
  Morningstar). I BTP del MOT di solito **non ci sono**.
- **Chiusura rettificata**: `indicators.adjclose`, rettificata per split e dividendi. PP ha un feed a parte
  `YahooFinanceAdjustedCloseQuoteFeed`. Per valorizzare le quantità reali va usato `close`; `adjclose` serve solo
  per confronti di rendimento totale.
- **Date**: i timestamp delle barre giornaliere sono l'apertura della seduta. Per la data di borsa conviene usare
  `meta.exchangeTimezoneName` o `gmtoffset`, non l'UTC: per l'Europa coincidono, per altri fusi no.
- **Limiti e blocchi**: Yahoo non pubblica limiti. Nel 2025 ci sono stati gli errori `YFRateLimitError('Too Many
  Requests')` ([yfinance #2422](https://github.com/ranaroussi/yfinance/issues/2422), apr 2025, 141 commenti) e la
  risposta è stata passare a `curl_cffi` (PR #2430, mag 2025). yfinance 1.8.0 (3 nov 2026) dipende da `curl_cffi>=0.17`.
  pofo usa ancora cookie e crumb per le quote, ma non per il chart.
- **Termini d'uso**: «personal use only» (README di yfinance, già nelle note precedenti). Il rischio è basso se ogni
  utente scarica dal proprio PC i dati dei propri titoli.

### 3.2 Stooq: non più utilizzabile senza intervento dell'utente

- Da **marzo 2026** i download CSV (`/q/d/l/?s=…&i=d&d1=…&d2=…`) rispondono con una pagina che chiede una **chiave
  API** (`stooq.com/q/d/?s=spy.us&get_apikey`).
  ([pandas-datareader #1012](https://github.com/pydata/pandas-datareader/issues/1012), 13 apr 2026)
- Da agosto 2026, dalle macchine server arriva una pagina di verifica JavaScript («This site requires JavaScript to
  verify your browser»), anche con User-Agent da browser (SCOUT #106, 10 ago 2026). Il 13 e 24 ott 2026 `/q/l/` dava
  **404** su ogni simbolo (day-trader-skill #3). Il metodo `get_apikey` non mostra più il captcha (qf-localc #3, 5 ago
  2026); un'issue giapponese del 25 set 2026 dice che Stooq non rilascia più chiavi.
- Stooq non ha mai avuto Milano, e le chiusure sono rettificate per gli split ma non per i dividendi (pofo).
- **Proposta**: togliere Stooq dalla catena automatica, o lasciarlo spento con la possibilità di inserire una chiave
  dell'utente. Va provato sul PC dell'utente, dove la verifica JavaScript potrebbe non scattare.

### 3.3 Borsa Italiana: l'unica fonte buona per lo storico dei BTP e del MOT

- **API dei grafici**: `https://grafici.borsaitaliana.it/api/instruments/{ISIN},{MIC},ISIN/history/period?period=1M|3M|6M|1Y|3Y|5Y|MAX`,
  con i parametri facoltativi `adjustment=true` e `add-last-price=true`. I MIC sono `MOTX` (MOT), `ETFP` (ETFplus) e
  `XMIL` (azioni). La risposta ha `history.historyDt[]` con `dt` (YYYYMMDD), `openPx`, `highPx`, `lowPx`, `closePx`,
  `lastPx`, `qty`, oltre a `history.currency` e `transco`.
- **Accesso**: serve un **JWT Bearer** preso dalla pagina `grafici.borsaitaliana.it/interactive-chart/<ISIN>-XMIL?lang=it`
  (`token="…"`; secondo la libreria è anonimo, «sub=-1», con scadenza di circa 100 anni e uguale per ogni ISIN), più
  i cookie del WAF **Imperva**. Ricerca JSON:
  `www.borsaitaliana.it/borsa/searchengine/all/json/search.html?q=…&lang=it`.
  ([Librefolio/borsaItaliana-scraping](https://github.com/Librefolio/borsaItaliana-scraping), storico.py e sessione.py, 30 set 2026;
  stesso schema in [YATP](https://github.com/giacomoaccursi/YATP), mag 2026, con `-MOTX`)
- **Fondi comuni**: non sono coperti dall'API dei grafici. C'è solo la pagina `/borsa/fondi/dettaglio/{codice}.html`
  (codice interno, diverso dall'ISIN) con l'ultimo NAV.
- **Obbligazioni**: il prezzo del MOT è in % del nominale, corso secco. La divisione per 100 c'è già in
  `borsaitaliana.py`; il rateo non è incluso.
- **Termini d'uso**: endpoint non documentato, protetto da WAF. Un altro progetto italiano lo definisce «fragile e in
  zona grigia sui termini d'uso: solo uso personale» (YonderUrik/buddy-budget). Rischio medio.

### 3.4 justETF: buona riserva per lo storico degli ETF per ISIN

- **Endpoint**: `https://www.justetf.com/api/etfs/{ISIN}/performance-chart?locale=it&currency=EUR&valuesType=MARKET_VALUE&reduceData=false&includeDividends=false&dateFrom=YYYY-MM-DD&dateTo=YYYY-MM-DD`
  (oppure `period=M1…MAX`). La risposta ha `series[]` con `date` e `value.raw`, più `latestQuote`. Valute disponibili:
  EUR, USD, GBP, CHF. Un giorno senza scambi **ripete l'ultima quotazione** (commento di fundarr), quindi i giorni
  «piatti» vanno filtrati.
  ([druzsan/justetf-scraping charts.py](https://github.com/druzsan/justetf-scraping), 26 ott 2026; usato da più di 40 progetti)
- **Accesso**: basta un User-Agent da browser. Un progetto prende prima i cookie e l'`XSRF-TOKEN` dalla pagina
  profilo (Frisk-12/TradeRepublicAnalytics). È segnalato un 403 diffuso il 30 ago 2025 (justetf-scraping #27).
- È una serie in euro calcolata da justETF, non la chiusura di una borsa precisa. Copre anche alcune azioni.
- **Termini d'uso**: non letti dal vivo; endpoint non documentato. Rischio medio.

### 3.5 Financial Times (markets.ft.com): riserva per i NAV dei fondi

- Ricerca: `markets.ft.com/data/searchapi/searchsecurities?query=<ISIN>`, che restituisce un `xid`. Poi
  `POST markets.ft.com/data/chartapi/series` con
  `{"days":N,"dataPeriod":"Day","dataInterval":1,"timeServiceFormat":"JSON","returnDateType":"ISO8601","elements":[{"Type":"price","Symbol":"<xid>"}]}`;
  nella risposta ci sono `Dates[]` e `Elements[0].ComponentSeries[Type=Close].Values[]`, e la valuta è indicata.
- finador lo usa come «provider clé» per i fondi FR/LU, «vérifié live», e pofo lo prende come riferimento per i
  livelli. ([pofo ft.go](https://github.com/bpineau/pofo/blob/main/pkg/marketdata/ft.go), finador DECISIONS.md, nov 2026)
- Termini d'uso non letti; endpoint non documentato.

### 3.6 Börse Frankfurt (Deutsche Börse): XETRA per ISIN, senza chiave

Wealthfolio ha un provider con `api.live.deutsche-boerse.com/v1/tradingview/search|symbols|history?symbol=…&resolution=1D&from=…&to=…`
e `data/price_information/single?isin=…&mic=XETR`. Il commento del codice dice «No API key required — only a browser
User-Agent header». Copre azioni, ETF e obbligazioni di XETR e XFRA.
([wealthfolio boerse_frankfurt/mod.rs](https://github.com/wealthfolio/wealthfolio/tree/main/crates/market-data/src/provider/boerse_frankfurt), 8 nov 2026)
Utile come riserva per gli ETF `.DE`.

### 3.7 File degli emittenti

- iShares: `www.ishares.com/<paese>/…/products/<id>/<slug>/1506575576011.ajax?fileType=xls&dataType=fund`. È il file
  «dati del fondo», con un foglio di NAV storici (più di 20 progetti usano lo stesso endpoint per le partecipazioni
  in CSV). Serve id e slug del prodotto, non l'ISIN.
- Amundi, Xtrackers e Vanguard pubblicano storici NAV scaricabili dalle schede prodotto. Non ho trovato endpoint
  stabili per ISIN usati nel codice e non ho potuto verificarli.
- PP ha un feed per gli storici NAV di Credit Suisse (`CSQuoteFeed`, `am.credit-suisse.com/…/NAVHistory_<isin>…`).
- **Uso consigliato**: **import di un file di prezzi** (CSV/XLSX) scaricato dall'utente, non scaricamento automatico.
  PP ha `CSVSecurityPriceExtractor`.

### 3.8 I feed di Portfolio Performance (sorgente al 7 nov 2026, `online/impl/`)

| Feed | Host | Storico | Europa | Chiave |
|---|---|---|---|---|
| YahooFinanceQuoteFeed e AdjustedClose | query1.finance.yahoo.com v8 chart | sì, da 1mo a 30y | sì (suffissi) | no |
| PortfolioPerformanceFeed | api.portfolio-performance.info `/v1/quote`, `/v1/candle` | sì | sì: elenco `EU_EXCHANGES` (MI, DE, F, PA, AS, L…) | OAuth, **piano «premium»**; 10 simboli di prova senza login |
| AlphavantageQuoteFeed | alphavantage.co `TIME_SERIES_DAILY` | sì | parziale (`.DEX`, `.MIL` nella mappa di Wealthfolio) | sì |
| EODHistoricalDataQuoteFeed | eodhistoricaldata.com `/api/eod/<sym>` | sì | sì | sì |
| FinnhubQuoteFeed | finnhub.io `/stock/candle` | sì | (piano gratuito solo USA, secondo Wealthfolio) | sì |
| TwelveDataQuoteFeed | api.twelvedata.com `/time_series`, `/price` | sì | via `mic_code` | sì («800 API/day, 8/minute») |
| LeewayQuoteFeed | api.leeway.tech | sì | sì (tedesco) | sì («50 API/day») |
| SiftingQuoteFeed | api.sifting.io `/v1/hist/…/bars` | sì | ? | sì (5 req/s gratis) |
| PortfolioReportQuoteFeed | api.portfolio-report.net | sì | sì | no |
| CoinGecko, Binance (anche futures), Kraken, Bitfinex, MEXC | – | sì | cripto | no |
| ECBDataPortalQuoteFeed | data-api.ecb.europa.eu `/service/data/` | sì | cambi, €STR | no |
| EurostatHICPQuoteFeed | Eurostat | sì | inflazione | no |
| QuandlQuoteFeed | Quandl/Nasdaq Data Link | sì | – | sì |
| AMFIIndia, MFAPI | India | sì | no | no |
| CSQuoteFeed | Credit Suisse NAV | sì | fondi CS | no |
| GenericJSONQuoteFeed | qualunque URL + JSONPath | sì | (es. ricetta Morningstar) | – |
| HTMLTableQuoteFeed | tabella HTML di qualunque pagina | sì | – | – |
| ManualQuoteFeed | – | – | – | – |

PP **non ha** né Morningstar né investing.com tra i feed integrati.

### 3.9 API a pagamento o con chiave (piani 2026: non ho potuto aprire i siti)

Da commenti nel codice di concorrenti attivi nel novembre 2026, più ricordi segnati come tali:
- **EODHD**: copre Milano (`.MI`), XETRA, Euronext e fondi (`EUFUND`, da ricordo). Il piano gratuito ha circa **20
  chiamate al giorno e 1 anno di storico** (Sure `eodhd.rb`: «free/basic plans are very restrictive»). Il piano EOD
  costa intorno ai 20 $ al mese (da ricordo, da verificare). È il miglior candidato **a pagamento** con la chiave
  dell'utente.
- **Twelve Data**: 800 chiamate al giorno, 8 al minuto (PP). La copertura europea nel piano gratuito non è verificata.
- **Alpha Vantage**: **25 chiamate al giorno** (Wealthfolio, Sure); `compact` dà circa 100 giorni.
- **Financial Modeling Prep**, **Marketstack**, **Tiingo**: Tiingo è soprattutto USA e Cina; per FMP e Marketstack
  non ho trovato fonti verificabili sulla copertura europea gratuita nel 2026. Basso interesse.
- **Finnhub**: piano gratuito solo USA e senza candele storiche (Wealthfolio).

### 3.10 Cambi BCE per lo storico

- Lo storico completo dal 1999 è in un solo file: `www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip` (CSV).
  Si può anche interrogare per serie: `data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?startPeriod=…&format=csvdata`
  (stesso host del feed di PP e di jal).
- L'app oggi scarica solo 90 giorni, quindi per il backfill di uno storico in valuta serve scaricare lo storico
  completo una volta sola, poi solo i giorni nuovi.

---

## 4. Raccomandazione

### 4.1 Catena delle fonti per tipo di strumento (prima fonte, poi le riserve)

| Strumento | Ultimo prezzo | Storico | Riserva |
|---|---|---|---|
| ETF/ETC su Milano, XETRA, Euronext | Yahoo (`.MI`, `.DE`…) | Yahoo, giornaliero | justETF performance-chart (per ISIN, EUR) → Börse Frankfurt (solo `.DE`) → Borsa Italiana `ETFP` |
| Azioni | Yahoo | Yahoo | Borsa Italiana `XMIL` (Milano) → Börse Frankfurt |
| BTP e obbligazioni del MOT | Borsa Italiana (scheda o API dei grafici `MOTX`) | **Borsa Italiana `MOTX`** | prezzo a mano / import CSV |
| Fondi comuni (ISIN) | Morningstar `lt.` (ultimo punto della serie) | **Morningstar `lt.` timeseries_price** | FT chartapi → Yahoo `0P….F` → import CSV dell'emittente |
| Cripto | CoinGecko | CoinGecko `market_chart` | – |
| Cambi | BCE | BCE storico completo (zip) | – |
| Chiave dell'utente (facoltativa) | EODHD | EODHD | – |

Stooq e investing.com **non** entrano nella catena automatica. Restano possibili come fonte personalizzata (F22)
dell'utente, con l'avviso sui termini d'uso.

### 4.2 Come si inserisce nell'architettura

- In `instrument_sources/base.py` aggiungere un tipo per lo storico:
  ```python
  @dataclass
  class History:
      currency: str                      # ISO code, or "GBp"; the API may not say it (Morningstar): from find()
      points: list[tuple[date, Decimal]] # ascending, one per trading day, native currency, unadjusted close
      source: str                        # "yahoo", "morningstar", "justetf", "borsaitaliana", …
      adjusted: bool = False             # True only for total-return / adjusted-close series
  ```
- In ogni modulo: `def history(isin: str, start: date, end: date | None = None) -> History`. Per Yahoo, nella stessa
  forma ma per ticker. Si registra in `HISTORIES = {"morningstar": …, "justetf": …, "borsaitaliana": …}` accanto a
  `QUOTES`. Le eccezioni restano `NotFound` e `Broken`; `quote()` può diventare l'ultimo punto di `history(isin,
  today - 10 giorni)`, così ogni fonte ha **un solo parser**.
- La catena per storico (`_history_order`) segue `_price_order` ma in modo separato, come `feed` e `latestFeed` di PP:
  per lo stesso titolo la fonte dell'ultimo prezzo può differire da quella dello storico.
- Host e token di Morningstar (`lt.morningstar.com`, `klr5zyak8x`, `ok91jeenoo`/`t92wz0sj7c`) vanno in costanti
  sovrascrivibili da Impostazioni o da un file, perché nel 2026 sono già cambiati due volte.
- Per Yahoo, Borsa Italiana e investing.com valutare `curl_cffi` (dipendenza binaria, wheel per Windows, macOS e
  Linux): la scelta va fatta dopo le prove sul PC dell'utente, non prima.

### 4.3 Dove salvare (estende F43)

`holding_prices`:
- `on`
- `close` (valuta d'origine)
- `currency`
- `price` (euro, come oggi)
- `fx_rate`
- `source` (yahoo, morningstar, justetf, borsaitaliana, ft, manual, import, custom:…)
- `adjusted` (bool)
- `estimated` (esiste già)

Si salva la **chiusura non rettificata**: dividendi e cedole sono già operazioni (F19b) e il TWR di F47 li tratta come
flussi. Una serie rettificata, se serve per i benchmark, va tenuta a parte, mai mescolata. Un prezzo inserito a mano
non viene mai sovrascritto da una fonte automatica.

Una tabella piccola `price_sync_state` per titolo, come Wealthfolio `quote_sync_state` e Sure `failed_fetch_count`:
- `history_source`
- `first_date`
- `last_date`
- `last_attempt_at`
- `failures`
- `last_error`

Il giorno riportato in avanti (carried forward) **non si salva** in tabella: lo calcola F47 con il suo flag, come
`isCarriedForward` di Ghostfolio.

### 4.4 Backfill, aggiornamento giornaliero, festivi

- **Quando si aggiunge un titolo**: storico giornaliero dalla **prima operazione meno 10 giorni**, e almeno 5 anni se
  si vuole il grafico pieno (scelta da decidere in D10). Con Yahoo il `range` si sceglie come fa PP, mai `max`;
  investing.com e Morningstar vanno a finestre. Si scarica in background, una richiesta al secondo per sito (c'è già).
- **Ogni giorno**: dall'ultima data salvata **meno 7 giorni** fino a oggi, perché i NAV dei fondi arrivano con 1–2
  giorni di ritardo e a volte vengono corretti. Le borse si leggono dopo le 18:00 ora di Roma; un prezzo del giorno
  stesso letto prima è provvisorio (Sure `provisional`). Il «una volta al giorno» di oggi resta.
- **Festivi e buchi**: non si inventano righe. In valutazione si riporta l'ultimo prezzo noto con un flag, e se l'ultimo
  punto ha più di 5 giorni lavorativi si mostra «prezzo vecchio». Le ripetizioni di justETF vanno scartate (stesso
  valore e nessun volume). Un calendario delle borse (TARGET2, Borsa Italiana) non serve all'inizio.
- **Cache**: la ricerca ISIN→id è già in cache per 30 giorni (`LOOKUP_CACHE`). Il SecId Morningstar, il cid
  investing.com e il MIC di Borsa Italiana vanno salvati **sul titolo**, non solo nella cache.
- **Controllo di plausibilità** quando lo storico arriva da una fonte diversa da quella abituale: un salto superiore
  al 30 % in un giorno, o un rapporto di livello diverso da 1 rispetto alla fonte precedente nei giorni in comune,
  diventa un avviso (pofo ha trovato divergenze del 13 % tra Morningstar e FT).

### 4.5 Rischio legale e di rottura per fonte

| Fonte | Tipo | Termini d'uso | Rottura 2025–26 | Verdetto |
|---|---|---|---|---|
| Yahoo chart | non documentata | «personal use only» | limiti 429 nel 2025 | principale, uso personale |
| Borsa Italiana grafici | non documentata, WAF + JWT | zona grigia | media | principale per il MOT |
| Morningstar `lt.` | non documentata, token pubblico | probabile divieto di automazione (non verificato) | host spenti ago 2026 | principale per i fondi, attivabile |
| justETF | non documentata | non letti | 403 ago 2025 | riserva ETF |
| FT markets | non documentata | non letti | – | riserva fondi |
| Börse Frankfurt | non documentata | non letti | – | riserva `.DE` |
| Stooq | ora con chiave e verifica JS | – | rotta mar–ott 2026 | togliere dalla catena |
| investing.com | non documentata, Cloudflare | probabile divieto esplicito (non verificato) | ricerca cambiata nel 2026 | no (solo F22 a rischio dell'utente) |
| mstarpy / API nuove Morningstar | WAF + login + JWT | – | rotture mensili | no |
| EODHD, Twelve Data | API ufficiali con chiave | licenza chiara | – | opzione con chiave dell'utente |
| BCE | ufficiale | libero riuso | – | sì |

### 4.6 Cosa provare sul PC dell'utente (la sandbox blocca tutto)

1. `morningstar.py` di oggi: `www.morningstar.it/it/util/SecuritySearch.ashx?q=<ISIN>` risponde ancora o
   reindirizza? E la pagina `snapshot.aspx`?
2. `lt.morningstar.com/api/rest.svc/klr5zyak8x/security/screener?…&term=<ISIN>` con 3 fondi e 2 ETF italiani: SecId,
   valuta, risposta senza cookie.
3. `lt.morningstar.com/api/rest.svc/timeseries_price/ok91jeenoo?id=<SecId>]2]1]&idtype=Morningstar&frequency=daily&startDate=2021-01-01&outputType=COMPACTJSON`,
   poi lo stesso con `t92wz0sj7c`, e `tools.morningstar.it/…/jbyiq3rhyf`. Confrontare l'ultimo NAV con la scheda
   del fondo.
4. Yahoo chart con `urllib` e il nostro User-Agent: 30 ticker di fila `.MI`/`.DE`, `range=5y&interval=1d`. Contare i
   429 e vedere se un User-Agent alla PP cambia qualcosa.
5. Stooq `/q/l/` e `/q/d/l/` da una rete domestica: CSV, 404 o verifica JS?
6. Borsa Italiana: il JWT dalla pagina interactive-chart, poi `…/{ISIN},MOTX,ISIN/history/period?period=5Y` per 2 BTP;
   e se senza cookie Imperva risponde 403.
7. justETF performance-chart per 3 ISIN, con e senza i cookie della pagina profilo.
8. FT searchsecurities + chartapi/series per 2 fondi LU/IE.
9. investing.com (solo per capire, non da integrare): `endpoints.investing.com/pd-instruments/v1/instruments/search?query=<ISIN>&domain_id=1`
   con `urllib`. Ci si aspetta la sfida Cloudflare.
10. BCE `eurofxref-hist.zip`: dimensione e tempo di scaricamento.

Ogni prova va salvata come pagina d'esempio per i test, come per F19a-bis: i test di CI non devono mai andare in rete.

---

## Sintesi

- **Morningstar** si può usare per lo storico dei NAV per ISIN senza chiave, ma **solo** su `lt.morningstar.com`:
  screener `klr5zyak8x` per ISIN→SecId e `timeseries_price` (token `ok91jeenoo` o `t92wz0sj7c`, suffisso `]2]1]`). I
  vecchi `tools.morningstar.co.uk` e `.fr` sono spenti da agosto 2026, e `SecuritySearch.ashx` reindirizza a una pagina
  protetta da WAF: il nostro `morningstar.py` va probabilmente **rifatto**. mstarpy e le API nuove (Selenium, JWT,
  login) non sono adatte a un'app desktop.
- **investing.com** ha i dati migliori (anche BTP e fondi), ma è dietro Cloudflare, l'API di ricerca è cambiata nel
  2026, investpy e investiny sono morti dal 2022 e i termini d'uso con ogni probabilità vietano l'automazione:
  **da non integrare**.
- **Stooq** dal 2026 vuole una chiave API e una verifica JavaScript: la riserva di oggi non funziona più.
- **Catena proposta**: Yahoo per ETF e azioni (riserve justETF, Börse Frankfurt, Borsa Italiana); **Borsa Italiana API
  dei grafici** per BTP e MOT; **Morningstar lt.** per i fondi (riserva FT); BCE storico completo per i cambi; EODHD
  con la chiave dell'utente come opzione ufficiale.
- **Architettura**: `history(isin, start, end) -> History(currency, points, source, adjusted)` in ogni modulo di
  `instrument_sources`. Si salva la chiusura non rettificata in valuta d'origine con fonte e cambio (F43). Backfill
  dalla prima operazione, poi aggiornamento giornaliero dall'ultima data meno 7 giorni. Nessuna riga inventata per i
  festivi (il riporto lo fa F47).
- Nulla è stato provato dal vivo: le 10 prove del §4.6 vanno fatte sul PC dell'utente prima di scrivere il codice.
