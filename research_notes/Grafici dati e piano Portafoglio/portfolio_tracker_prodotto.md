# Portfolio tracker dal punto di vista del prodotto (funzioni, schermate, grafici, metriche, UX), novembre 2026

Raccolta del 9 novembre 2026. Complementa, senza ripeterle, le note in `research_notes/Panorama competitivo finanza personale/github_wealth_investimenti.md` (metriche dei repo, prezzi OSS, issue aperte più votate).

**Metodo e limiti:**
- Per Ghostfolio, Wealthfolio, Portfolio Performance (PP) e Sure ho letto il codice sorgente: clone `--depth 1` del 2026-11-09 (ultimo commit PP: 7 nov 2026). Etichette di interfaccia, route delle pagine, enum dei tipi di attività e di asset e testi di spiegazione delle metriche vengono da lì. Sono fonti primarie.
- I siti commerciali erano tutti **bloccati dalla rete della sessione** (ENOTFOUND): parqet.com, getquin.com, sharesight.com, snowball-analytics.com, kubera.com. Anche ghostfol.io e wealthfolio.app non erano raggiungibili. Per le app commerciali ho usato solo i riassunti della ricerca web (pagine ufficiali indicizzate quando disponibili, altrimenti recensioni). Dove le fonti discordano lo segnalo.
- Reddit e forum.portfolio-performance.info non sono stati consultati.

---

## 1. Schermate e sezioni di ciascuna app

### Takeaway
Gli OSS maturi convergono su quasi la stessa architettura dell'informazione:
- **Dashboard/Overview** con valore e performance
- **Holdings** (posizioni)
- **Activities** (movimenti)
- **Allocations/Insights** (ripartizioni)
- **Performance/Analysis** con benchmark
- **Income/Dividends**
- **Planning** (FIRE, obiettivi, ribilanciamento)
- **Data health** (qualità dei dati), introdotta da Wealthfolio v3

PP è l'eccezione "da analista": viste tabellari configurabili più una dashboard a widget (oltre 60 tipi).

### Cited Findings

**Ghostfolio (3.99, nov 2026)**
- Route del portafoglio: `activities`, `allocations`, `analysis`, `fire`, `x-ray`. Pagine principali: home, accounts, markets, zen (vista minimale). — [sorgente pages/portfolio](https://github.com/ghostfolio/ghostfolio/tree/main/apps/client/src/app/pages/portfolio)
- Componenti della home: `home-overview`, `home-holdings`, `home-summary`, `home-watchlist`, `markets`, `benchmark-comparator`. — [sorgente components](https://github.com/ghostfolio/ghostfolio/tree/main/apps/client/src/app/components)
- La scheda di dettaglio di un holding ha le sezioni Overview, Activities, Accounts, Countries, Sectors, Market Data. — [holding-detail-dialog](https://github.com/ghostfolio/ghostfolio/tree/main/apps/client/src/app/components/holding-detail-dialog)
- La pagina Summary mostra:
  - Investments, Buy, Sell, Invested Capital, Fees, Interest, Cash
  - Absolute Gross/Net Performance, "thereof Dividend", Annualized Performance
  - Net Worth, Total Assets, Liabilities
  - Emergency Fund, Buying Power, Excluded from Analysis, Time in Market
  - Fonte: [portfolio-summary.component.html](https://github.com/ghostfolio/ghostfolio/tree/main/apps/client/src/app/components/portfolio-summary)
- X-ray è un insieme di "regole" di rischio. Le categorie sono: account cluster risk, asset class cluster risk (equity, fixed income), currency cluster risk, economic market cluster risk (developed/emerging), emergency fund, fees (fee ratio sul volume investito), liquidity (buying power) e regional market cluster risk (Asia-Pacifico, emergenti, Europa, Giappone, Nord America). — [sorgente models/rules](https://github.com/ghostfolio/ghostfolio/tree/main/apps/api/src/models/rules)

**Wealthfolio (v3.12, 1 nov 2026)**
- Pagine: dashboard, holdings, activity, performance, income, insights, net-worth, allocation-targets, asset, account, health, ai-assistant, onboarding, settings.
- Sotto-sezioni di settings: accounts, addons, agent-access, ai-providers, contribution-limits, exports, market-data, portfolios, spending, taxonomies, wealthfolio-connect.
- Fonte: [sorgente apps/frontend/src/pages](https://github.com/wealthfolio/wealthfolio/tree/main/apps/frontend/src/pages)
- La dashboard comprende accounts-summary, balance, top-holdings, goals e un selettore di portafoglio (più conti raggruppati). — [pages/dashboard](https://github.com/wealthfolio/wealthfolio/tree/main/apps/frontend/src/pages/dashboard)
- Insights ha le schede Overview / Performance / Income.
  - Breakdown per Classes, Regions, Sectors, Accounts, Risk, Security types, Currency.
  - Card "Target allocation" con "Differences from target" e tolleranza.
  - Net worth con Assets/Liabilities, "Δ {{period}}", "Momentum" e avviso "Not updated in over 90 days".
  - Fonte: [locales/en/insights.json](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/i18n/locales/en/insights.json)
- Pagina Data Health ("Identify and resolve data quality issues"), con livelli Info/Warning/Error/Critical. Esempi di controlli:
  - "Missing manual valuation", "Outdated prices", "Missing exchange rate"
  - "Holding has negative quantity", "Sale missing cost-basis match", "Transaction sells more than was held"
  - "Incomplete transfer detected", "Exchange rates … disagree"
  - Ogni controllo ha un'azione rapida (Sync Prices, Fetch Exchange Rates, View Activities…).
  - Fonte: [locales/en/health.json](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/i18n/locales/en/health.json)

**Portfolio Performance (0.90, nov 2026)**
- Viste principali: Statement of Assets (con le varianti History, Holdings, Derived data series), Performance (Calculation, Chart, Return/Volatility), Securities/All Securities, Watchlist, Deposit Accounts, Taxonomies (con Rebalancing, Pie/Donut, Tree Map, Stacked chart), Payments/Earnings, Trades, Investment Plans, Reports, Dashboard. — [messages.properties](https://github.com/portfolio-performance/portfolio/blob/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/messages.properties)
- Template di tassonomia inclusi, tradotti anche in italiano: asset classes, GICS (1° livello e completo), industry-simple, regioni (anche MSCI), security-type e "kommer" (modello Gerd Kommer). — [sorgente model](https://github.com/portfolio-performance/portfolio/tree/master/name.abuchen.portfolio/src/name/abuchen/portfolio/model)

**Sure (investimenti)**
- Le viste investimento sono essenziali: holdings (Name, Weight, Average cost, Current market price, Total return, Missing data) e trades.
- Il costo di carico (cost basis) può essere "User set", "From trades" o "From provider".
- Fonte: [views/holdings](https://github.com/we-promise/sure/tree/main/app/views/holdings), [locale holdings](https://github.com/we-promise/sure/tree/main/config/locales/views/holdings)
- I sottotipi di conto sono localizzati per regione, con il trattamento fiscale associato. Per l'UE esistono Assurance Vie, PEA, Pillar 3a e Riester; **nessun sottotipo italiano** (PIR, fondo pensione, conto deposito). — [investment.rb](https://github.com/we-promise/sure/blob/main/app/models/investment.rb)

**App commerciali (fonti secondarie)**
- **Parqet**: piano Basis gratuito (1 portafoglio, analisi base), Plus e Investor. Plus comprende benchmark, previsione dividendi, dashboard fiscale (anche ritenute estere recuperabili), X-Ray degli ETF, autosync broker e fino a 5 portafogli. Investor comprende 15 portafogli e 20 integrazioni. **Non ha ribilanciamento né metriche di rischio** (Sharpe, beta). Le crypto si caricano solo da file. — [justETF](https://www.justetf.com/de/academy/parqet-erfahrungsbericht.html), [finanzwissen](https://finanzwissen.de/anbieter/parqet/test/), [diefinanzarena](https://www.diefinanzarena.de/blog/parqet-erfahrungen)
- Parqet si è esteso a immobili, orologi e beni reali. — [broker-test.at](https://www.broker-test.at/news/parqet-portfolio-tracker-erweitert-sich-auf-immobilien-uhren-und-sachwerte/)
- **Sharesight**: le sezioni sono soprattutto report:
  - Diversity (allocazione a qualsiasi data passata)
  - Contribution analysis (contributo di ogni titolo in valuta e in %)
  - Exposure (look-through degli ETF per settore, geografia, asset class, titolo)
  - Multi-period (fino a 5 periodi a confronto)
  - Fonte: [sharesight blog](https://www.sharesight.com/blog/explore-your-portfolio-performance-with-the-contribution-analysis-report/), [help reports](https://help.sharesight.com/reports/), [community exposure](https://community.sharesight.com/t/etf-exposure-diversity-reporting/407)
- **Getquin**: social feed, watchlist, idee d'investimento, "DeepDive X-Ray" (composizione degli ETF e sovraesposizioni), Advanced Analytics (geografia, valute, tipi di asset), previsione dividendi. — [getquin portfolio-tracker](https://www.getquin.com/portfolio-tracker), [help getquin](https://help.getquin.com/en/articles/6817043)
- **Empower**:
  - Investment Checkup: confronta l'allocazione attuale con un target per età e rischio, per stile, dimensione e settore.
  - Fee Analyzer: stima l'impatto delle commissioni nel tempo.
  - Retirement Planner: scenari di pianificazione pensionistica.
  - Fonti secondarie: [roboadvisorpros](https://www.roboadvisorpros.com/a-review-of-empowers-free-tools/), [mybanktracker](https://www.mybanktracker.com/blog/investing/personal-capital-review-310564)
- **Finary**: "fee scanner", disponibile su tutti i piani, rileva costi nascosti di assicurazioni vita, conti titoli, ETF e crypto e suggerisce alternative più economiche. — [finary fees-scanner](https://finary.com/en/insights/fees-scanner)
- **Kubera**: dashboard "a foglio di calcolo" del patrimonio netto (banche, broker, crypto/DeFi, immobili, beni alternativi), pianificazione per i beneficiari ed eredità, documenti allegati, import AI di documenti. Niente budget e poca analisi di portafoglio. — [wallethacks](https://wallethacks.com/kubera-review/), [thecfoclub](https://thecfoclub.com/tools/kubera-software-review/)

### Inferences
- La sezione Portafoglio di MyFinancePlace può adottare lo schema comune: Panoramica / Posizioni / Movimenti / Allocazione / Performance / Rendite / Pianificazione. Wealthfolio dimostra che aggiungere una "Salute dei dati" riduce i ticket del tipo "i numeri sono sbagliati".
- PP ha la profondità (dashboard a widget, tassonomie) ma l'interfaccia più criticata (#1921 è la issue più votata del repo).

### Gaps
- Non ho potuto vedere screenshot né flussi reali delle app commerciali (siti bloccati).
- Snowball Analytics, Delta e Investbrain: schermate non verificate.
- Rotki: non ho trovato fonti nuove sulle funzioni non-crypto (saldi manuali, report PnL) oltre le note precedenti.

---

## 2. Grafici

### Takeaway
Il "kit" standard comprende:
- linea del valore vs capitale investito
- performance cumulata vs benchmark
- torte, ciambelle o treemap di allocazione su più dimensioni
- barre dei dividendi per mese o anno
- heatmap dei rendimenti mensili (PP)
- grafico del drawdown (PP, Wealthfolio)

Il look-through degli ETF è presente in Ghostfolio (By ETF Holding/Provider), Parqet, Getquin e Sharesight. Manca in Wealthfolio e, nativamente, in PP, dove è la seconda richiesta storica (#1665).

### Cited Findings
- **Ghostfolio, pagina Analysis**:
  - Portfolio Evolution, Investment Timeline, Performance Timeline, Dividend Timeline
  - Benchmark comparator
  - Asset Performance vs Currency Performance, cioè la scomposizione dell'effetto cambio, in assoluto e in %
  - Fonte: [analysis-page.html](https://github.com/ghostfolio/ghostfolio/blob/main/apps/client/src/app/pages/portfolio/analysis/analysis-page.html)
- **Ghostfolio, Allocations**: By Account, Asset Class, Continent, Country, Currency, **ETF Holding**, **ETF Provider**, Holding, Market, Sector, Regions. Usa un componente treemap. — [allocations-page.html](https://github.com/ghostfolio/ghostfolio/blob/main/apps/client/src/app/pages/portfolio/allocations/allocations-page.html), [treemap-chart](https://github.com/ghostfolio/ghostfolio/tree/main/libs/ui/src/lib/treemap-chart)
- Ghostfolio prende i dati di settore degli ETF da Trackinsight. La issue #5924 ("Trackinsight data gathering failing", aperta, 11 👍) mostra quanto il look-through dipenda da una fonte esterna fragile. — [issue #5924](https://github.com/ghostfolio/ghostfolio/issues/5924)
- **Wealthfolio, Performance**:
  - Rendimenti cumulati, periodici, giornalieri, mensili e annuali
  - Confronto con uno o più benchmark e tra conti
  - Portfolio Value, Contributions, Drawdown, Best/Worst Day
  - Export ed "Print Report"
  - Fonte: [performance.json](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/i18n/locales/en/performance.json)
- **Wealthfolio, Income**:
  - Monthly/Yearly/Cumulative Income, Year over Year Growth
  - Top 10 Dividend Sources, Income by Symbol/Account/Month/Type
  - Projected Annual Income "Based on current holdings"
  - Torta per valuta e avviso sulle valute non convertite
  - Fonte: [income.json](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/i18n/locales/en/income.json), [pages/income](https://github.com/wealthfolio/wealthfolio/tree/main/apps/frontend/src/pages/income)
- **Wealthfolio, Holdings**: Market Value Over Time, Sector/Asset Class Allocation, Top Gainers/Losers, valori in valuta dell'asset o in valuta base. — [holdings.json](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/i18n/locales/en/holdings.json)
- **PP, widget della dashboard**:
  - heatmap dei rendimenti mensili e annuali
  - heatmap mensili di earnings, investimenti, tasse e commissioni
  - Drawdown chart, Current Drawdown, Max Drawdown Duration
  - Earnings per month/quarter/year e by taxonomy
  - Upcoming dividends
  - Top Contributors (Value) e Top Performers (TTWROR)
  - Actual vs. Target Allocation
  - Distance from ATH, All Time High
  - Trading activity
  - Statement of Assets chart, Taxonomies chart
  - Fonte: [WidgetFactory.java](https://github.com/portfolio-performance/portfolio/blob/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/dashboard/WidgetFactory.java)
- **PP, viste di tassonomia**: Pie chart, Donut chart, Tree Map, Stacked area chart (valore effettivo), Rebalancing. — [messages.properties](https://github.com/portfolio-performance/portfolio/blob/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/messages.properties)
- **PP, Payments**: per mese, trimestre o anno, anche "per strumento" e cumulato, con "Closed trades" e consolidamento dei titoli dismessi. — stessa fonte
- **Look-through negli OSS**:
  - PP #1665 "Extract ETF Asset Allocation (Countries, Sectors, Currencies) from ETF Holdings List": aperta dal 2020, 14 👍.
  - PP #1921 "New UI Design proposal": 22 👍. Le note precedenti riportavano 40 reazioni totali.
  - Fonte: API di ricerca GitHub, 2026-11-09, [#1665](https://github.com/portfolio-performance/portfolio/issues/1665), [#1921](https://github.com/portfolio-performance/portfolio/issues/1921)
- **Look-through nei commerciali**:
  - Sharesight Exposure report: titoli dentro gli ETF. — [sharesight](https://www.sharesight.com/blog/5-ways-to-get-the-portfolio-insights-you-need)
  - Getquin DeepDive X-Ray. — [getquin](https://www.getquin.com/portfolio-tracker)
  - Parqet X-Ray (piano Plus). — [justETF](https://www.justetf.com/de/academy/parqet-erfahrungsbericht.html)
- Snowball pubblicizza un calendario dividendi con previsione. — [snowball dividend-tracker](https://snowball-analytics.com/dividend-tracker)

### Inferences
- Per un utente italiano con un portafoglio di 2–4 ETF ad accumulazione, i grafici di maggior valore sono tre:
  - valore vs versato, che mostra il PAC nel tempo
  - allocazione look-through per paese, settore e valuta
  - heatmap mensile
- I grafici dei dividendi contano meno per chi ha ETF ad accumulazione. Restano utili per cedole BTP e azioni a distribuzione.
- La scomposizione "rendimento asset vs effetto cambio" di Ghostfolio è rara e utile per chi ha ETF in USD.

### Gaps
- Per Sure non ho verificato il grafico di performance degli investimenti.
- Non ho trovato un grafico di "plusvalenze realizzate/non realizzate per anno" esplicitamente documentato fuori da PP (Trades Profit/Loss) e Wealthfolio (Attribution).

---

## 3. Metriche e come vengono spiegate

### Takeaway
Wealthfolio v3 e PP sono i più completi:
- **Wealthfolio**: TWR, MWR/IRR (XIRR), Value Return, Price Return, annualizzati; volatilità, Sharpe, max drawdown con date di picco, minimo e recupero; attribuzione.
- **PP**: TTWROR, IRR, volatilità, semideviazione, Sharpe, max drawdown e durata, tasso di commissioni e di tasse del portafoglio, turnover.
- **Ghostfolio**: usa ROAI e "Net/Gross Performance".
- **Commerciali**: CAGR e yield on cost (Getquin Premium).

Wealthfolio è il riferimento per spiegare le metriche in linguaggio semplice e dichiarare quando una metrica non è calcolabile.

### Cited Findings
- **Wealthfolio, metriche calcolate dal motore**: `twr`, `annualized_twr`, `irr`, `annualized_irr`, `value_return`, `annualized_value_return`.
  - Attribuzione: contributions, distributions, income, realized_pnl, unrealized_pnl_change, fx_effect, fees, taxes, residual.
  - Rischio: volatility, max_drawdown con peak_date, trough_date, recovery_date, drawdown_duration_days.
  - Il campo DataQuality contiene warnings e not_applicable_reasons.
  - Fonte: [performance.rs](https://github.com/wealthfolio/wealthfolio/blob/main/crates/portfolio-engine/src/model/performance.rs)
- **Testi di spiegazione di Wealthfolio** (citazioni):
  - "Time-weighted return (TWR) measures investment performance after removing the effect of deposits and withdrawals. Periods under one year are shown as selected-period returns; periods of one year or longer are shown annualized when available."
  - "Money-weighted return (MWR) … calculated with IRR/XIRR; for periods of one year or longer, annualized XIRR is the standard display."
  - "MWR unavailable for holdings-only scopes because transaction cash flows are not tracked."
  - Il max drawdown è il "Largest peak-to-trough decline … without adjusting for deposits or withdrawals".
  - Fonte: [performance.json](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/i18n/locales/en/performance.json)
- **PP, widget delle metriche**:
  - TTWROR cumulato e annualizzato, IRR
  - Absolute Change, Delta, Invested Capital
  - "Performance-neutral transfers"
  - Max/Current Drawdown e durata, Volatility e Volatility annualized (quest'ultima aggiunta in 0.90)
  - Semideviation, Sharpe ratio (con tasso privo di rischio configurabile)
  - Portfolio Tax Rate, Portfolio Fee Rate
  - Trades Profit/Loss, Average holding period, Turnover Rate
  - Fonte: [WidgetFactory.java](https://github.com/portfolio-performance/portfolio/blob/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/dashboard/WidgetFactory.java), [dashboard](https://github.com/portfolio-performance/portfolio/tree/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/dashboard)
- **Ghostfolio**: Net Performance e Gross Performance, assolute e in %, "thereof Dividend", Annualized Performance; intervalli 1d…max più anni singoli ("'2024', '2023'…"). — [portfolio-summary](https://github.com/ghostfolio/ghostfolio/tree/main/apps/client/src/app/components/portfolio-summary), [date-range.type.ts](https://github.com/ghostfolio/ghostfolio/blob/main/libs/common/src/lib/types/date-range.type.ts)
- **Getquin Premium**: benchmarking, CAGR, yield on cost, previsione dividendi infra-annuale e di crescita a lungo termine. — [help getquin](https://help.getquin.com/en/articles/6817043)
- Le recensioni di Parqet segnalano l'assenza di Sharpe e beta. — [diefinanzarena](https://www.diefinanzarena.de/blog/parqet-erfahrungen)
- **Fiducia nei calcoli**: le issue più commentate di Wealthfolio e Ghostfolio riguardano calcoli di performance percepiti come errati (Wealthfolio #303 e #1119, Ghostfolio #3416 e #5793), come già annotato. Ghostfolio #7468 chiede Total Return inclusi i dividendi. — [note precedenti](../Panorama%20competitivo%20finanza%20personale/github_wealth_investimenti.md)

### Inferences
- Una v1 deve mostrare due numeri chiari e spiegati:
  - **TWR**: misura "il prodotto", neutrale rispetto ai versamenti del PAC.
  - **MWR/XIRR**: misura "il mio rendimento".
- A questi si aggiunge il guadagno assoluto in euro, con un tooltip in italiano per ciascuno e un indicatore "dati incompleti" in stile DataQuality di Wealthfolio.
- Volatilità, Sharpe e drawdown possono arrivare dopo (should have).

### Gaps
- Non ho verificato come Sharesight e Snowball definiscono il proprio "total return" (siti bloccati).

---

## 4. Entità supportate (tipi di asset)

### Takeaway
Wealthfolio ha la tassonomia più ricca e già pensata per obbligazioni (cedola, scadenza, zero coupon), opzioni e beni alternativi con valutazioni manuali. Ghostfolio modella i beni alternativi in modo più povero: niente attività di split o trasferimento, passività come tipo di attività. Nessun OSS ha tipi nativi italiani: BTP Italia/Valore come strumenti con calendario cedole, Buoni Fruttiferi Postali, PIR, fondi pensione italiani.

### Cited Findings
- **Ghostfolio**: AssetSubClass = BOND, CASH, COLLECTIBLE, COMMODITY, CRYPTOCURRENCY, ETF, LOAN, MUTUALFUND, PRECIOUS_METAL, PRIVATE_EQUITY, STOCK. — [schema.prisma](https://github.com/ghostfolio/ghostfolio/blob/main/prisma/schema.prisma)
- **Wealthfolio, AssetKind**: INVESTMENT, PROPERTY, VEHICLE, COLLECTIBLE, PRECIOUS_METAL, PRIVATE_EQUITY, LIABILITY, OTHER, FX. — [constants.ts](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/lib/constants.ts)
- **Wealthfolio, tassonomia "Instrument Type"**:
  - Stocks, Bonds, Funds, ETFs, Options & Futures, Cash & FX, Structured Notes, Physical Assets, Crypto, Private Investments
  - Sottotipi: Government/Corporate/Municipal/Convertible Bond, Preferred Stock, ADR/GDR, Warrant
  - Altre tassonomie: Asset Classes, Industries (GICS), Regions, Risk Category, Custom Groups
  - Fonte: [taxonomies.json](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/i18n/locales/en/taxonomies.json)
- La scheda asset di Wealthfolio ha campi obbligazionari "Coupon", "Zero coupon", "Maturity date" e moltiplicatore per contratti. — [asset.json](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/i18n/locales/en/asset.json), [asset-bond-spec.ts](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/pages/asset/asset-bond-spec.ts)
- La v3 tratta anche opzioni e posizioni short (vedi note precedenti).
- **Valutazioni manuali**: Wealthfolio le gestisce per i beni alternativi e segnala "Missing manual valuation" e "Valuation not updated". — [health.json](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/i18n/locales/en/health.json)
- **Sure**: conti di investimento per regione con trattamento fiscale (taxable, tax_deferred, tax_exempt, tax_advantaged) e conti crypto separati. — [investment.rb](https://github.com/we-promise/sure/blob/main/app/models/investment.rb), [crypto.rb](https://github.com/we-promise/sure/blob/main/app/models/crypto.rb)
- **PP**:
  - #1132 "Performance/Rendite von p2p- u. Tagesgeld-Konten": aperta dal 2019, 8 👍. Chiede la performance dei conti deposito.
  - #177 "Anleihen" (obbligazioni): chiusa, 8 👍.
  - Fonte: API di ricerca GitHub, [#1132](https://github.com/portfolio-performance/portfolio/issues/1132), [#177](https://github.com/portfolio-performance/portfolio/issues/177)
- **Richieste di asset non quotati e prezzi**:
  - Ghostfolio #1352 "Add ability to add unlisted securities": 14 👍, chiusa.
  - Wealthfolio #434 (bond holdings) e #753 (BTP con nominale e prezzo in %), già annotate.
  - Fonte: [#1352](https://github.com/ghostfolio/ghostfolio/issues/1352)

### Inferences
- Per l'Italia, il modello dati deve prevedere obbligazioni con prezzo in percentuale del nominale, cedola, scadenza e calendario dei flussi (BTP, BTP Valore, BTP Italia indicizzati).
- I Buoni Fruttiferi Postali vanno trattati come strumenti a capitalizzazione nota: valore di rimborso tabellare, senza prezzo di mercato.
- Conti deposito e fondi pensione richiedono valutazioni manuali periodiche, con promemoria di aggiornamento.

### Gaps
- Non ho verificato in dettaglio il supporto alle cedole di PP (genera i pagamenti o li registra solo come "interest"?).

---

## 5. Tipi di attività, multi-conto, multi-valuta, lotti

### Takeaway
Wealthfolio ha il set di attività più completo:
- BUY/SELL/SPLIT/DIVIDEND/INTEREST/DEPOSIT/WITHDRAWAL/TRANSFER_IN/OUT/FEE/TAX/CREDIT/ADJUSTMENT
- 4 metodi di costo
- asset swap che preserva il costo

Ghostfolio ha solo 6 tipi. Le richieste più votate riguardano valute delle attività, contanti e cambi.

### Cited Findings
- **Ghostfolio**: Type = BUY, DIVIDEND, FEE, INTEREST, LIABILITY, SELL. — [schema.prisma](https://github.com/ghostfolio/ghostfolio/blob/main/prisma/schema.prisma)
- **Wealthfolio**: ActivityType = BUY, SELL, SPLIT, DIVIDEND, INTEREST, DEPOSIT, WITHDRAWAL, TRANSFER_IN, TRANSFER_OUT, FEE, TAX, CREDIT, ADJUSTMENT, UNKNOWN. — [constants.ts](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/lib/constants.ts)
- Wealthfolio ha un'attività di switch o conversione che conserva il costo: "Units of one fund or asset become units of another and keep their cost: a fund switch, a share-class or series switch, a mutual fund converted to an ETF… If the switch was taxed, record a sell and a buy." — [activity.json](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/i18n/locales/en/activity.json)
- **Metodi di costo**:
  - Wealthfolio: FIFO, costo medio, LIFO, HIFO (note precedenti).
  - Sure: costo medio, con cost basis "User set / From trades / From provider". — [locale holdings Sure](https://github.com/we-promise/sure/tree/main/config/locales/views/holdings)
- **Richieste più votate, tutti gli stati** (2026-11-09):
  - **Ghostfolio**:
    - #3320 "Support activity in custom currency" (20 👍)
    - #4286 "Include cash from accounts to total balance" (19 👍)
    - #705 "Can not edit currency of activity" (14 👍)
    - #1352 titoli non quotati (14 👍)
    - #2449 tasso di cambio errato (10 👍)
  - **Wealthfolio**:
    - #592 SSO OIDC (20 👍)
    - #246 formato data e ora personalizzabile (14 👍)
    - #590 "Missing FX Conversion Activity Support" (12 👍)
    - #219 crypto in tempo reale (11 👍)
    - #889 usare "Amount" per evitare la deriva del saldo di cassa (10 👍)
    - #40 campo ISIN nell'import CSV (9 👍)
    - #1211 saldo progressivo del conto (9 👍)
    - #862 ACB canadese (8 👍)
  - **PP**:
    - #1921 redesign UI (22 👍)
    - #2085 REST API (18 👍)
    - #1665 look-through ETF (14 👍)
    - #1334 opzioni e premi da "Stillhalter" (11 👍)
    - #2216 database (10 👍)
    - #1835 asset swap (9 👍)
    - #1588 duplicare un movimento (8 👍)
    - #1796 precisione delle quotazioni a 8 decimali (8 👍)
  - Fonte: `gh api search/issues … sort:reactions-+1`, [Ghostfolio issues](https://github.com/ghostfolio/ghostfolio/issues), [Wealthfolio issues](https://github.com/wealthfolio/wealthfolio/issues), [PP issues](https://github.com/portfolio-performance/portfolio/issues)

### Inferences
- I punti dolenti ricorrenti sono:
  - valuta della singola attività, con il cambio storico modificabile
  - movimenti di cassa che fanno quadrare il saldo
  - ISIN come chiave di identificazione
  - duplicazione rapida di un movimento
- Per il PAC servono duplicazione e piani ricorrenti.
- In Italia il metodo di costo che conta è il **costo medio ponderato** (prezzo medio di carico, come in regime amministrato). FIFO e LIFO sono secondari.

### Gaps
- Spin-off: non ho trovato un tipo di attività dedicato in nessuno dei tre OSS. Ghostfolio e Wealthfolio non hanno un enum specifico; per Wealthfolio va eventualmente coperto con switch o ADJUSTMENT, ma non l'ho verificato.

---

## 6. Pianificazione: FIRE, Monte Carlo, ribilanciamento, PAC, obiettivi

### Takeaway
- **Wealthfolio**: pianificatore pensione/FIRE con Monte Carlo (fascia 10°–90° percentile), scenari Lean/Fat/Coast FIRE, 6 stress test, obiettivi con stato On track/At risk. Ha anche un "allocation worksheet" di ribilanciamento con bande di tolleranza.
- **Ghostfolio**: calcolatore FIRE semplice e Premium.
- **PP**: widget FIRE, piani d'investimento (PAC) che generano transazioni, ribilanciamento sulle tassonomie.
- **Parqet**: niente ribilanciamento.

### Cited Findings
- **Ghostfolio FIRE**: input "Savings Rate per Month", "Annual Interest Rate", "Retirement Date"; output "Projected Total Amount" e "Sustainable retirement income". È una funzione Premium. — [fire-calculator](https://github.com/ghostfolio/ghostfolio/tree/main/libs/ui/src/lib/fire-calculator), [fire-page.html](https://github.com/ghostfolio/ghostfolio/blob/main/apps/client/src/app/pages/portfolio/fire/fire-page.html), [pricing-page.html](https://github.com/ghostfolio/ghostfolio/blob/main/apps/client/src/app/pages/pricing/pricing-page.html)
- **Wealthfolio, Goals**:
  - Tipi di obiettivo: Retirement, House Purchase, Education, Emergency Fund, Vacation, Custom. Ogni obiettivo si alloca per conto (in %).
  - Stato: On Track/Behind/Ahead/At risk, con "Required Monthly" e "Projected Completion".
  - Proiezione in "Today's value" o "Nominal".
  - Lean FIRE (70% della spesa pianificata), Fat FIRE (150%), Coast FIRE.
  - Testo del Monte Carlo: "We model different market paths… The shading shows the 10th–90th percentile range… Money lasts counts paths that cover essential spending…"
  - "What could break this plan?" con 6 stress scenario.
  - Fonte: [goals.json](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/i18n/locales/en/goals.json)
- **Wealthfolio, ribilanciamento**:
  - Target per tassonomia, con bande "Absolute", "Relative factor" o "Hybrid" (Tight/Standard/Loose) e "Absolute floor".
  - Colonne Current/Target/Drift, "Largest gaps", "Cash remaining", lock delle categorie, export del worksheet.
  - Fonte: [allocation.json](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/i18n/locales/en/allocation.json), [pages/allocation-targets](https://github.com/wealthfolio/wealthfolio/tree/main/apps/frontend/src/pages/allocation-targets)
- **Wealthfolio, limiti di contribuzione**: contribution limits ricorrenti per anno, pensati per conti con tetti di versamento (TFSA/RRSP). Si potrebbero adattare a fondo pensione e PIR, ma non l'ho verificato. — [goals.json](https://github.com/wealthfolio/wealthfolio/blob/main/apps/frontend/src/i18n/locales/en/goals.json)
- **PP**:
  - Investment Plans con tipi "Security purchase / delivery", "Deposit", "Interest", "Withdrawal".
  - Widget FIRE: FIRE Number, Current Net Worth, Est. Monthly Savings, Est. Returns, FIRE Date, Time to FIRE.
  - Vista Rebalancing (TARGET Value, Delta Value).
  - Fonte: [messages.properties](https://github.com/portfolio-performance/portfolio/blob/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/messages.properties), [InvestmentPlan.java](https://github.com/portfolio-performance/portfolio/blob/master/name.abuchen.portfolio/src/name/abuchen/portfolio/model/InvestmentPlan.java)
- **Empower Investment Checkup**: confronto con un'allocazione raccomandata per età e rischio. Il Retirement Planner sarebbe un Monte Carlo secondo una fonte secondaria, ma non è confermato da Empower. — [roboadvisorpros](https://www.roboadvisorpros.com/a-review-of-empowers-free-tools/)
- **Fineco**: il "Piano Replay" è un PAC su ETF con ribilanciamento automatico, cioè il broker stesso fa PAC e ribilanciamento. — [investimi](https://investimi.com/piattaforme-pac-automatico-etf)

### Inferences
- Il PAC (piano ricorrente che genera acquisti attesi da confermare) è un must per l'Italia, ed è già il modello di PP.
- Ribilanciamento con bande e obiettivi con stato "in linea / in ritardo" sono should-have. Un Monte Carlo stile Wealthfolio è nice-to-have.

### Gaps
- Non ho verificato le funzioni di pianificazione di Kubera ("Fast Forward") e Finary su fonti primarie.

---

## 7. Prezzi e modelli di business (commerciali)

### Takeaway
I tracker commerciali costano da circa 50 a 250 €/$ all'anno. I prezzi delle fonti secondarie sono spesso incoerenti, quindi tutti vanno ricontrollati sulle pagine ufficiali (bloccate in questa sessione).

### Cited Findings
| App | Piani e prezzi (fonte) | Note |
|---|---|---|
| Parqet | Basis gratuito; Plus circa 11,99 €/mese, annuale 99,99 o 107,91 € (dato discorde; più vecchi: 7,99–9,99 €); Investor | [diefinanzarena](https://www.diefinanzarena.de/blog/parqet-erfahrungen), [kagels-trading](https://www.kagels-trading.de/parqet-erfahrungen/) |
| Getquin | Premium 89,99 €/anno (fonte help/recensione); altre fonti: 4,99 €/mese o "sotto 50 €/anno" | [help getquin](https://help.getquin.com/en/articles/6817043), [benzinga](https://benzinga.com/money/getquin-review) |
| Sharesight | AU: Starter 19, Investor 29, Expert 49 AUD/mese (annuale); NZ: portafogli 1/4/10, holdings 30/illimitati | [sharesight AU](https://sharesight.com/au/pricing/), [sharesight NZ](https://www.sharesight.com/nz/pricing/) |
| Snowball | Starter 79,99, Investor 149,99, Expert 249,99 $/anno (App Store); gratuito con 1 portafoglio e 10 holding | [App Store](https://apps.apple.com/app/snowball-analytics/id6463484375), [snowball pricing](https://snowball-analytics.com/public/pricing) |
| Kubera | Circa 249–250 $/anno (Essentials circa 20,83 $/mese secondo Toolradar, sett. 2026); altre fonti 150 o 360 $ | [toolradar](https://toolradar.com/tools/kubera/pricing), [wallethacks](https://wallethacks.com/kubera-review/) |
| Finary | Plus 149,99 €/anno, Pro 349,99 €/anno; fee scanner su tutti i piani | [finary pricing](https://finary.com/en/pricing), [finary plus](https://finary.com/en/finary-plus) |
| Delta (eToro) | Basic gratuito fino a 10 asset; PRO e PRO+ (dati discordi: 53,88–99,90 $/anno); PRO fino a 40 asset | [App Store](https://apps.apple.com/us/app/delta-bitcoin-crypto-tracker/id1288676542), [comparedge](https://comparedge.com/tools/delta-app/pricing) |
| Moneyviz (IT) | Dichiarazione fiscale "da 39 €", "da 129 €", "da 249 €" per conto e anno fiscale; un concorrente indica 49 €; niente tracker gratuito separato | [partitaiva.it](https://www.partitaiva.it/moneyviz/), [waltio](https://www.waltio.com/it/blog/moneyviz-vs-waltio-confronto/) |
| Empower | Strumenti gratuiti; consulenza a pagamento (circa 0,49–0,89% sopra 100k $) | [mybanktracker](https://www.mybanktracker.com/blog/investing/personal-capital-review-310564) |

- Moneyviz calcola le imposte per broker esteri e crypto (regime dichiarativo), con analisi dei dividendi, confronto con 10 benchmark, oltre 28 broker esteri collegati e import da Excel fino a 3.000 transazioni. — [partitaiva.it](https://www.partitaiva.it/moneyviz/), [blog moneyviz](https://blog.moneyviz.it/come-importare-transazioni-da-excel-su-moneyviz/)
- Secondo un sito di confronto per l'Italia, Getquin non calcola le imposte italiane. — [allinvestview](https://www.allinvestview.com/best-portfolio-tracker-italy/)

### Inferences
- In Italia l'unico che fa pagare per la fiscalità è Moneyviz, e copre il regime dichiarativo, a partire da 39–49 € per conto e anno. Questo è un riferimento di disponibilità a pagare per un modulo fiscale.

### Gaps
- Nessun prezzo verificato sulla pagina ufficiale (host bloccati).
- Investbrain Cloud e Snowball mensile non trovati.

---

## 8. Esigenze specifiche europee e italiane

### Takeaway
Le esigenze europee e italiane sono:
- PAC su ETF (spesso ad accumulazione, quindi niente dividendi da tracciare)
- BTP e obbligazioni con prezzo in % e cedole
- conti deposito e Buoni postali
- broker italiani (Fineco e Directa; PP copre solo Directa)
- fiscalità italiana: costo medio, 26% / 12,5%, bollo 0,2%

Nessun grande tracker internazionale li copre insieme.

### Cited Findings
- Sia Fineco sia Directa offrono PAC su ETF. Fineco ha 0 € sui PAC; Directa ha oltre 600 ETF idonei al PAC. — [investimi](https://investimi.com/piattaforme-pac-automatico-etf), [extraETF Directa](https://extraetf.com/it/pac-etf/offerta-pac-etf-directa), [extraETF Fineco](https://extraetf.com/it/pac-etf/offerta-pac-etf-fineco)
- Wealthfolio #753: import CSV dei BTP con nominale e prezzo in percentuale. Wealthfolio #771: costo medio ponderato, cita Fineco. PP #5453: obbligazioni con prezzo in %. — note precedenti, [#753](https://github.com/wealthfolio/wealthfolio/issues/753), [#771](https://github.com/wealthfolio/wealthfolio/issues/771)
- PP #1132: performance dei conti deposito, richiesta dal 2019 e ancora aperta. — [#1132](https://github.com/portfolio-performance/portfolio/issues/1132)
- Il progetto italiano net-worth-tracker ha:
  - prezzi BTP per ISIN da Borsa Italiana
  - calendario cedole con step-up e premio finale (BTP Valore)
  - prezzo medio di carico (PMC) su più broker
  - stima della plusvalenza in regime amministrato (12,5% / 26%)
  - bollo 0,2%, fondo pensione
  - Fonte: [README](https://github.com/GiuseppeDM98/net-worth-tracker) (note precedenti)
- Sure non ha sottotipi di conto italiani, ma ne ha di francesi, tedeschi e svizzeri. — [investment.rb](https://github.com/we-promise/sure/blob/main/app/models/investment.rb)
- I template di tassonomia di PP sono tradotti in italiano (`assetclasses_it`, `regions-msci_it`, `industry-gics_it`, `kommer_it`…). — [sorgente model](https://github.com/portfolio-performance/portfolio/tree/master/name.abuchen.portfolio/src/name/abuchen/portfolio/model)

### Inferences
- Il vantaggio competitivo di MyFinancePlace in Italia è l'unione di quattro elementi:
  - PAC
  - BTP e BFP
  - import Fineco/Directa
  - vista fiscale "come la calcola la banca" (PMC, minusvalenze e zainetto, bollo)
- Look-through e confronto con benchmark sono funzioni di parità con Parqet e Getquin.
- Per gli ETF ad accumulazione conviene mettere in evidenza "valore vs versato" e TWR, non i dividendi.

### Gaps
- Buoni Fruttiferi Postali: nessuna app esaminata li supporta in modo documentato.
- Nessuna fonte sulle esigenze dichiarate dagli utenti italiani: forum e Reddit non sono stati consultati.

---

## 9. Matrice funzioni × app e priorità per la v1

### Takeaway
La matrice qui sotto sintetizza le sezioni 1–8. Legenda: ✔ = documentato; ✖ = assente o dichiarato mancante; ? = non verificato. "Fonte" rimanda alle sezioni precedenti.

### Cited Findings

| Funzione | Ghostfolio | Wealthfolio | PP | Sure | Parqet | Getquin | Sharesight | Snowball | Kubera | Moneyviz |
|---|---|---|---|---|---|---|---|---|---|---|
| Valore vs investito nel tempo | ✔ | ✔ | ✔ | ? | ? | ? | ? | ? | ? | ? |
| TWR | ✖ (ROAI) | ✔ | ✔ (TTWROR) | ? | ? | ? | ? | ? | ? | ? |
| MWR/IRR | ✖ | ✔ | ✔ | ? | ? | ? | ? | ? | ✔ (IRR da recensioni, non verificato) | ? |
| Benchmark | ✔ (Premium) | ✔ | ✔ | ? | ✔ (Plus) | ✔ (Premium) | ? | ? | ? | ✔ (10) |
| Volatilità / Sharpe / drawdown | parziale | ✔ | ✔ | ? | ✖ | ? | ? | ? | ? | ? |
| Heatmap mensile | ✖ | ✖ (barre mensili) | ✔ | ? | ? | ? | ? | ? | ? | ? |
| Allocazione multi-dimensione | ✔ | ✔ | ✔ | ? | ✔ | ✔ | ✔ | ? | ? | ? |
| Look-through ETF | ✔ | ✖ | ✖ (#1665) | ? | ✔ | ✔ | ✔ | ? | ? | ? |
| Dividendi: storico e previsione | ✔ timeline | ✔ + proiezione | ✔ + upcoming | ? | ✔ | ✔ | ? | ✔ calendario | ? | ✔ |
| Effetto cambio separato | ✔ | ✔ (fx_effect) | ? | ? | ? | ? | ? | ? | ? | ? |
| Obbligazioni (cedola/scadenza) | ✖ | ✔ | parziale | ? | ? | ? | ? | ? | ? | ? |
| Beni alternativi / valutazioni manuali | parziale | ✔ | parziale | ✔ | ✔ | ? | ? | ? | ✔ | ? |
| Split / transfer / tasse come attività | ✖ | ✔ | ✔ | ? | ? | ? | ? | ? | ? | ? |
| Metodi di costo | ? | FIFO / medio / LIFO / HIFO | ✔ (configurabile, CostMethodConfig) | medio | ? | ? | ? | ? | ? | ✔ (fiscale IT) |
| PAC / piani ricorrenti | ✖ | ✖ | ✔ | ✖ | ? | ? | ? | ? | ? | ? |
| Ribilanciamento | ✖ | ✔ | ✔ | ✖ | ✖ | ? | ? | ? | ? | ? |
| FIRE / Monte Carlo | FIRE (Premium) | FIRE + Monte Carlo | FIRE | ✖ | ? | ? | ? | ? | ? | ? |
| Salute dei dati | ✖ | ✔ | ✖ | parziale (missing data) | ? | ? | ? | ? | ? | ? |
| Fiscalità italiana | ✖ | ✖ | ✖ | ✖ | ✖ (DE) | ✖ | ✖ | ? | ✖ | ✔ (dichiarativo) |

Le voci ✔ e ✖ vengono dalle fonti citate nelle sezioni 1–8. Fonti per il metodo di costo di PP: [CostMethodConfig.java](https://github.com/portfolio-performance/portfolio/tree/master/name.abuchen.portfolio.ui/src/name/abuchen/portfolio/ui/views/dashboard).

### Inferences
Le priorità che seguono sono una proposta di sintesi, non una fonte.

**Must have (v1):**
1. Panoramica con valore totale, versato netto, guadagno in € e %, TWR e XIRR spiegati in italiano, periodi YTD/1A/3A/5A/Max e anni singoli.
2. Grafico valore vs versato.
3. Posizioni con PMC (costo medio ponderato), plus/minus latente, peso, valori in valuta base e in valuta dello strumento.
4. Movimenti: acquisto, vendita, dividendo, cedola/interesse, commissione, imposta, versamento, prelievo, trasferimento tra conti, frazionamento, con valuta e cambio per singolo movimento.
5. Multi-conto (Fineco, Directa, banca, conto deposito) e import CSV/XLS con ISIN.
6. Allocazione per asset class, valuta, conto e strumento (ciambella o treemap).
7. BTP con prezzo in % e cedole; conto deposito e BFP con valutazione manuale o tabellare.
8. PAC: piano ricorrente che propone i movimenti attesi.
9. Indicatore della qualità dei dati: prezzo vecchio, cambio mancante, vendita oltre la quantità detenuta.

**Should have:**
- Benchmark (ETF o indice scelto dall'utente).
- Look-through degli ETF per paese e settore.
- Rendite: barre mensili e annuali, prossime cedole.
- Heatmap dei rendimenti mensili.
- Ribilanciamento con target e bande.
- Vista fiscale "stile regime amministrato": plusvalenze realizzate per anno, zainetto delle minusvalenze, stima del bollo.
- Volatilità e max drawdown.
- Separazione dell'effetto cambio.

**Nice to have:**
- FIRE e Monte Carlo, obiettivi con stato.
- Contribuzione per titolo (stile Sharesight), multi-periodo.
- Fee analyzer (stile Finary/Empower, molto adatto a fondi e polizze italiane costose).
- Opzioni e short.
- Beni alternativi (immobili, veicoli).
- Dashboard a widget configurabili (stile PP).

### Gaps
- Le celle "?" delle app commerciali richiedono una verifica sulle pagine ufficiali o nell'app. In questa sessione parqet.com, getquin.com, sharesight.com, snowball-analytics.com e kubera.com non erano risolvibili: vanno abilitati nella rete della sessione per completare la matrice.
- Non ho dati di utilizzo che indichino quali grafici gli utenti aprono davvero. Le priorità sono inferite dalle richieste su GitHub e dal contesto italiano.
