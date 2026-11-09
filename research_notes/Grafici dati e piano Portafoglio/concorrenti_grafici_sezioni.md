# Concorrenti: tipi di grafico, report/dashboard e sezioni di navigazione (stato a novembre 2026)

Metodo e date. Per le app open source ho clonato il ramo principale il 9 nov 2026 e ho cercato nel codice
(Actual 26.11.0, ultimo commit 2026-11-09; Firefly III, ultimo commit 2026-10-26; Sure, 2026-11-09;
ezBookkeeping 2.2.0, 2026-11-09; Fava, 2026-11-03; Wealthfolio 3.12.0, 2026-11-08). Il ramo principale può
contenere funzioni non ancora rilasciate. Per le app SaaS (Monarch, Copilot, YNAB, Lunch Money,
PocketSmith, Empower) WebFetch era bloccato a livello di rete (help.monarch.com, lunchmoney.app,
docs.firefly-iii.org: ENOTFOUND). Ho quindi usato solo i riassunti di WebSearch delle pagine ufficiali:
il livello di fiducia è più basso, e lo segnalo caso per caso. La ricerca issue su GitHub (`gh api search/issues`)
ha funzionato; la lettura delle singole issue (`gh api repos/.../issues/N`) no (403). Reddit non è stato consultato.

## 1. Sezioni e grafici/report, app per app

### Takeaway
Tutte le app hanno un nucleo comune: ciambella o torta per categoria, barre mensili entrate e uscite,
linea o area del patrimonio netto e progresso del budget. Le app open source più evolute nel 2026 (Actual,
ezBookkeeping, Sure, Wealthfolio) hanno aggiunto Sankey, calendario o heatmap e dashboard a widget
personalizzabili. Tra le SaaS, Monarch ha i report più ricchi (Sankey, report salvati dal marzo 2026),
Copilot si distingue per la linea del ritmo di spesa, PocketSmith per le previsioni a calendario.

### Cited Findings

**Actual Budget (v26.11.0, codice al 2026-11-09)**
- Sezioni principali nel codice della sidebar: Budget, Reports, Schedules, Accounts, più More (Payees, Rules, Bank Sync, Tags, Settings). C'è anche un flag `newSidebarUI` per una sidebar ridisegnata, ancora sperimentale. — [prefs.ts](https://github.com/actualbudget/actual/blob/master/packages/loot-core/src/types/prefs.ts); [docs sperimentali: redesigned-sidebar](https://github.com/actualbudget/actual/tree/master/packages/docs/docs/experimental)
- Dashboard dei report "fully customizable", con più dashboard ("as many dashboards as you like"). Ogni widget ha filtri e intervalli di date live o statici. — [docs reports/index.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/reports/index.md)
- Widget stabili:
  - Cash Flow: saldo dei conti in budget nel tempo, con entrate e uscite separate.
  - Net Worth: modalità Trend (linea) e Stacked (area impilata per conto).
  - Spending Analysis: confronta le spese di un periodo, per esempio questo mese contro il mese scorso, quindi MoM.
  - Summary card: un numero, come totale o media mensile.
  - Calendar card: entrate e uscite giornaliere in formato calendario.
  - Text widget in Markdown.
  - Custom Reports.
  - Crossover Point: proiezione FIRE in cui il reddito passivo incrocia le spese, con 4% SWR e mediana con filtro di Hampel.
  
  — [docs reports/index.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/reports/index.md)
- Widget sperimentali dietro feature flag: Budget Analysis (issue #6742), Balance Forecast (#7669), Sankey (#1919), Monte Carlo Analysis (#8571). Nel codice esistono anche `formula-card` (flag `formulaMode`) e `AgeOfMoney`. — [docs reports/index.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/reports/index.md); [prefs.ts FeatureFlag](https://github.com/actualbudget/actual/blob/master/packages/loot-core/src/types/prefs.ts); [cartella reports/reports](https://github.com/actualbudget/actual/tree/master/packages/desktop-client/src/components/reports/reports)
- Custom Reports:
  - Visualizzazioni: Table, Bar, Line, Area, Donut, più StackedBar e BarLine nel codice.
  - Mode: Total o Time.
  - Split: per Category, Group, Payee, Account, Month.
  - Type: Payment, Deposit o Net.
  - Date Live o Static, filtri sulle transazioni, esclusione di categorie.
  - Toggle per legenda, summary e label.
  - Salvataggio: i report salvati diventano card della dashboard.
  - Limiti: Donut e Area non disponibili in modalità Time; Line non disponibile in modalità Total.
  
  — [custom-reports.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/reports/custom-reports.md); [disabledList.ts](https://github.com/actualbudget/actual/blob/master/packages/desktop-client/src/components/reports/disabledList.ts); [ChooseGraph.tsx](https://github.com/actualbudget/actual/blob/master/packages/desktop-client/src/components/reports/ChooseGraph.tsx)
- Sankey (sperimentale):
  - Viste: "Spent" (entrate → conti → gruppi → categorie) e "Budgeted".
  - Controlli: numero massimo di nodi per livello (gli altri finiscono in "Other", con tooltip), ordinamento, scelta dei livelli iniziale e finale, percentuali o valori assoluti, "group accounts".
  - Filtri a chip.
  - Limiti: i valori negativi non sono rappresentabili; layout mobile limitato.
  
  — [sankey-report.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/experimental/sankey-report.md)
- Budget Analysis (sperimentale): serie Budgeted, Spent, Overspending Adjustment e Balance cumulativo. Si passa da linee a barre, con intervalli rapidi da 1/3/6 mesi, 1 anno, YTD e all time. Nel codice c'è un modulo di export CSV dedicato. — [budget-analysis-report.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/experimental/budget-analysis-report.md); [budget-analysis-export.ts](https://github.com/actualbudget/actual/blob/master/packages/desktop-client/src/components/reports/spreadsheets/budget-analysis-export.ts)
- Balance Forecast (sperimentale): saldo futuro giornaliero o mensile, calcolato dalle transazioni programmate (schedules) o dal tracking budget. — [balance-forecast-report.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/experimental/balance-forecast-report.md)
- Monte Carlo (sperimentale): 5.000 simulazioni di pensionamento con percentuale di successo; nel codice ci sono grafico a bande, istogramma e grafico del saldo dei "pot". — [monte-carlo-analysis.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/experimental/monte-carlo-analysis.md); [cartella graphs](https://github.com/actualbudget/actual/tree/master/packages/desktop-client/src/components/reports/graphs)
- Drill-down: `showActivity.ts` riceve navigate, conti e filtri e apre la lista transazioni filtrata dal punto cliccato. — [showActivity.ts](https://github.com/actualbudget/actual/blob/master/packages/desktop-client/src/components/reports/graphs/showActivity.ts)

**Firefly III (codice al 2026-10-26)**
- Voci della sidebar dalle route: Accounts, Budgets, Categories, Tags, Piggy banks, Subscriptions (bills), Recurring, Rules, Transactions, Reports, Search, Export, Object groups, Currencies, Exchange rates, Webhooks. — [sidebar.blade.php](https://github.com/firefly-iii/firefly-iii/blob/main/resources/views/components/layout/sidebar.blade.php)
- Dashboard con grafici fissi, non personalizzabili:
  - accounts-chart (linea dei saldi);
  - budgets-chart e budgets-two-chart;
  - categories-chart;
  - bills-chart;
  - expense-accounts-chart e revenue-accounts-chart.
  
  — [index.blade.php](https://github.com/firefly-iii/firefly-iii/blob/main/resources/views/index.blade.php)
- Report: 6 tipi, cioè default (report finanziario), audit, budget, category, tag, double (conti di spesa e di entrata). Ognuno ha grafici per budget, categoria, conto e tag, più net-worth e operations (`chart.report.net-worth` e `chart.report.operations`). — [resources/views/reports](https://github.com/firefly-iii/firefly-iii/tree/main/resources/views/reports); [app/Http/Controllers/Chart](https://github.com/firefly-iii/firefly-iii/tree/main/app/Http/Controllers/Chart)
- Tipi di grafico (Chart.js): `multiCurrencyPieChart` (37 usi), `columnChart` (12), `lineChart` (7), `stackedColumnChart` (2). Nessuna occorrenza di sankey, treemap o heatmap nel codice. — grep su [firefly-iii](https://github.com/firefly-iii/firefly-iii)
- Richieste degli utenti:
  - #3486 "Clicking on report graphs should show the transactions behind" (2020, chiusa);
  - #12590 "Reports: ability to exclude transactions by tag" (ago 2026, aperta);
  - #6579 "An ignored category" (aperta).
  
  — [ricerca issue](https://github.com/firefly-iii/firefly-iii/issues?q=report+chart)

**Sure (fork di Maybe, codice al 2026-11-09)**
- Navigazione: Home, Transactions, Reports, Assistant (AI); il file di localizzazione contiene anche Budgets, Bills, Plan, Goals. — [layout en.yml](https://github.com/we-promise/sure/tree/main/config/locales/views/layout)
- Dashboard a sezioni che si possono riordinare con drag and drop (`sortable-list`, preferenza `section_order`) e nascondere ("customize", `hidden_dashboard_sections`), più un PeriodPicker. Sezioni:
  - cashflow_sankey;
  - money_flow;
  - spending_trend;
  - outflows_donut;
  - investment_summary;
  - net_worth_chart;
  - balance_sheet;
  - insights_feed.
  
  — [dashboard.html.erb](https://github.com/we-promise/sure/blob/main/app/views/pages/dashboard.html.erb); [pages_controller.rb](https://github.com/we-promise/sure/blob/main/app/controllers/pages_controller.rb)
- Pagina Reports con le sezioni net_worth, trends_insights, spending_vs_normal, investment_performance, investment_flows, transactions_breakdown, budget_performance e summary_dashboard. Offre period picker, stampa ("print report") e istruzioni per Google Sheets. — [app/views/reports](https://github.com/we-promise/sure/tree/main/app/views/reports); [reports_controller.rb](https://github.com/we-promise/sure/blob/main/app/controllers/reports_controller.rb)
- Controller JS per i grafici (D3): bar, donut, net_worth, sankey (anche in preview), spending, time_series, goal_projection, loan_payoff. — [app/javascript/controllers](https://github.com/we-promise/sure/tree/main/app/javascript/controllers)
- Richieste: #4008 grafico del conto investimenti con contributi netti accanto al valore (ott 2026, aperta); #389 tag nella dashboard; #1313 contributi agli investimenti da trattare come trasferimenti nei report. — [issue Sure](https://github.com/we-promise/sure/issues)

**ezBookkeeping (2.2.0, codice al 2026-11-09)**
- Sezioni desktop: overview (dashboard), transactions, statistics, insights (Explorer), accounts, categories, tags, templates, exchangerates, settings. — [src/views/desktop](https://github.com/mayswind/ezbookkeeping/tree/main/src/views/desktop)
- Dashboard a widget con un `LayoutEditorPage` (layout modificabile). Widget disponibili:
  - AccountBalanceList, AssetSummary;
  - ExpenseCategoryRanking;
  - IncomeExpenseTrend, NetAssetsTrend;
  - MonthlyExpenseOverview, MonthlyExpenseProgress;
  - PeriodIncomeExpense, PeriodNetIncomeAndSavingsRate;
  - RecentTransactions, AccountUnreconciledTransactions;
  - TransactionCalendar, TransactionCalendarHeatmap.
  
  — [overview/widgets](https://github.com/mayswind/ezbookkeeping/tree/main/src/views/desktop/overview/widgets)
- Statistics, con tre tipi di analisi:
  - Categorical: Pie, Bar o Radar.
  - Trend: Area, Column o Bubble.
  - AssetTrends: Area, Smooth Area, Column, Boxplot o Candlestick.
  - Dati: spesa o entrata per conto o categoria, Net Cash Flow, Net Income, Net Worth, totali per valuta.
  - Aggregazione: giorno, mese, trimestre, anno, anno fiscale, ciclo di fatturazione.
  
  — [core/statistics.ts](https://github.com/mayswind/ezbookkeeping/blob/main/src/core/statistics.ts)
- Insights Explorer: un costruttore di query con condizioni su giorno della settimana o del mese, ora, tipo, categoria, conti, importo, geolocalizzazione, tag e descrizione. Ha schede Query, Chart, Data Table e Data Table modificabile. Grafici disponibili:
  - Pie, Donut, Nightingale Rose, Radar;
  - Column (stacked o grouped);
  - Line e Smooth Line, Area e Smooth Area (stacked);
  - Bubble;
  - Treemap, Sunburst;
  - Heatmap, Calendar Heatmap;
  - Custom.
  
  C'è anche un componente `AccountAndCategorySankeyChart`. — [core/explorer.ts](https://github.com/mayswind/ezbookkeeping/blob/main/src/core/explorer.ts); [components/desktop](https://github.com/mayswind/ezbookkeeping/tree/main/src/components/desktop)
- Richieste: #711 esportare o copiare un grafico come immagine PNG/SVG (chiusa ott 2026); #507 totale al centro della torta nell'Explorer (chiusa feb 2026); #621 colori della legenda troppo simili; #591 report statistico mensile via email; #675 aggiustamento per l'inflazione (aperta). — [issue ezBookkeeping](https://github.com/mayswind/ezbookkeeping/issues)

**Wealthfolio (3.12.0, codice al 2026-11-08)**
- Pagine: dashboard, holdings, performance, income, net-worth, insights, activity, allocation-targets, health, ai-assistant, settings, più il nuovo modulo Spending con le pagine activity, budget e insights. Le migrazioni del modulo spending sono datate 2026-05-25 e 2026-06-28. — [pages](https://github.com/afadil/wealthfolio/tree/main/apps/frontend/src/pages); [features/spending](https://github.com/afadil/wealthfolio/tree/main/apps/frontend/src/features/spending); [migrazioni](https://github.com/afadil/wealthfolio/tree/main/crates/storage-sqlite/migrations)
- Componenti dei report di spesa:
  - budget-vs-actual-bars, overall-budget-meter;
  - cashflow-area-chart, cashflow-diverging-bars;
  - category-hierarchy-table, category-sparkline-grid;
  - day-of-week-chart, spending-rhythm-heatmap (giorno × ora, con clic sulla cella che apre un pannello di transazioni);
  - period-comparison-card, notable-changes-card, hero-strip;
  - money-flow-chart (Sankey);
  - events-calendar e events-timeline.
  
  Gli insights sono organizzati in "stage": Where I am, What changed, When/where. Dalla categoria si apre il pannello delle transazioni (drill-down). Lato portafoglio c'è un treemap della composizione. — [components/reports](https://github.com/afadil/wealthfolio/tree/main/apps/frontend/src/features/spending/components/reports)

**Fava (Beancount, codice al 2026-11-03)**
- Sidebar: Balance Sheet, Income Statement, Trial Balance, Journal, Query, Holdings, Commodities, Documents, Events, Statistics, Editor, Errors, Import, Options, Help, più filtro globale per tempo, conto e tag/payee. — [frontend/src/sidebar](https://github.com/beancount/fava/tree/main/frontend/src/sidebar)
- Grafici:
  - gerarchici: Treemap, Sunburst, Icicle (componenti presenti nel ramo principale);
  - BarChart, LineChart (balances), ScatterPlot;
  - Brush, per selezionare un intervallo di tempo trascinando sull'asse;
  - ChartSwitcher e ModeSwitch per passare da un tipo all'altro;
  - grafici dai risultati delle query (`query-charts.ts`).
  
  Il PR sull'icicle descrive la modalità salvata per report in localStorage. — [frontend/src/charts](https://github.com/beancount/fava/tree/main/frontend/src/charts); [PR 2191 (mirror)](https://github.forks.workers.dev/beancount/fava/pull/2191)
- Un utente sulla mailing list Beancount indica il "Treemap of Expenses" come la vista più utile, ma lamenta il contrasto del testo. — [Google Groups beancount](https://groups.google.com/g/beancount/c/_hWFZf2al68)

**hledger-web**
- Mostra grafici sopra i report All accounts, Balance sheet, Income statement, Cashflow statement e Holdings, più un grafico del saldo nel tempo nel registro. I tasti c e d mostrano o nascondono grafico e tabella. Fonte: riassunto di WebSearch della pagina ufficiale, non verificato direttamente. — [hledger.org/charts.html](https://hledger.org/charts.html); [manuale hledger-web](https://hledger.org/1.29/hledger-web.html)

**GnuCash**
- Report standard:
  - Income & Expense: Cash Flow e Income Statement in tabella, Budget Report;
  - Expense e Income in Barchart e Piechart;
  - Net Worth Barchart e Linechart (attività, passività e patrimonio netto mensili);
  - Assets e Liabilities in barchart e piechart.
  
  Le fonti sono manuali vecchi (v2.x); un utente segnala che il Cash Flow non si può ordinare per importo. — [manuale 2.0](https://code.gnucash.org/website/docs/v2.0/C/gnucash-help/reports.html); [guida IT](https://code.gnucash.org/docs/it/gnucash-guide/rpt_standardrpts.html); [gnucash-user dic 2023](https://lists.gnucash.org/pipermail/gnucash-user/2023-December/109828.html)

**Monarch (SaaS; solo riassunti di WebSearch)**
- Reports ha sostituito la vecchia pagina Cash Flow, anche su mobile, dove la tab è stata rinominata Reports.
  - Schede: Cash Flow (con Sankey e Trend Bars, impilate di default), Spending e Income.
  - Raggruppamento: categoria, gruppo o merchant; il Sankey per categoria, gruppo o entrambi.
  - Filtri per conti e tag; vista mensile, trimestrale o annuale.
  - Summary card con entrate totali, spese, cash flow netto e tasso di risparmio.
  - Export CSV delle transazioni dietro al report (solo web).
  - L'app ricorda l'ultimo grafico usato.
  
  — [Using Reports](https://help.monarch.com/hc/en-us/articles/21846787088916-Using-Reports); [Cash Flow](https://help.monarch.com/hc/en-us/articles/20504904768020-Cash-Flow)
- "Saved Reports" annunciati nel marzo 2026, con esempi d'uso: spese deducibili, un Sankey per persona. — [monarch.com/blog/saved-reports-and-more](https://www.monarch.com/blog/saved-reports-and-more)
- Dashboard a widget (budget, net worth, credit score...) riordinabili e rimovibili con "Customize"; AI Assistant nella navigazione di sinistra dal dicembre 2025. — [Customize Your Dashboard](https://help.monarch.com/hc/en-us/articles/360058127551-Customize-Your-Dashboard); [Getting Started](https://help.monarch.com/hc/en-us/articles/360048393272-Getting-Started)
- Un post della community segnala il Sankey "inutilizzabile" con i Businesses attivi; è una fonte di terze parti. — [mirror subreddit 2026-06](https://reddit.sentinel-team.org/subreddits/MonarchMoney/snapshots/2026-06-17T00%3A59%3A29.924245Z)

**Copilot Money (SaaS)**
- Tab: Dashboard, Transactions, Investments, Recurrings, Cash Flow (più Categories e Accounts con net worth). Versione web uscita a gennaio 2026; una recensione di marzo 2026 dice che sul web mancano Goals, Cash Flow e "month/year in review", in conflitto con l'annuncio. — [9to5Mac gen 2026](https://9to5mac.com/2026/01/01/copilot-money-brings-clarity-to-your-finances-now-on-the-web/); [Dashboard Tab](https://help.copilot.money/en/articles/6045480-dashboard-tab-overview); [Cash Flow Tab](https://help.copilot.money/en/articles/9682232-cash-flow-tab-overview)
- Grafico del ritmo di spesa (pace) in Dashboard:
  - linea tratteggiata = ritmo ideale per restare nel budget, linea piena = spesa cumulata;
  - in alto il valore "Free to Spend";
  - esclude i ricorrenti;
  - senza budget, confronta con il mese scorso spalmato uniformemente.
  
  Le barre delle categorie sono colorate in base al ritmo (verde, giallo, arancione). Il Cash Flow confronta con il periodo precedente usando una linea tratteggiata. — [Dashboard Tab](https://help.copilot.money/en/articles/6045480-dashboard-tab-overview); [Categories Tab](https://help.copilot.money/en/articles/9504513-categories-tab-overview)

**YNAB (Reflect)**
- Reflect contiene Spending breakdown, Income v Expense (tabella dettagliata su web, barre a 6 mesi su mobile), Net Worth e Age of Money (6 mesi, 1 o 2 anni). — [Income v Expense](https://support.ynab.com/en_us/income-v-expense-Byu1BYWRq?mobile-help=true); [Age of Money](https://support.ynab.com/en_us/age-of-money-H1ZS84W1s.md); [What's new mobile](https://www.ynab.com/whats-new/check-your-income-vs-spending-on-mobile)

**Lunch Money**
- Query Tool: torta, linee o tabella, con granularità annuale, filtro per conto e query salvate. Ci sono anche Stats & Trends (pagina Trends rinnovata, tasso di risparmio), Net Worth mese per mese e Calendar (entrate e uscite in calendario). Fonti: changelog e recensioni, tramite i riassunti di WebSearch. — [Changelog](https://lunchmoney.app/changelog); [11 features](https://lunchmoney.app/blog/11-lunch-money-features-you-should-be-using-and-why); [WalletHacks](https://wallethacks.com/lunch-money-review/)

**PocketSmith**
- Calendario con previsione del saldo giornaliero da "budget events": da 6 mesi (free) fino a 60 anni (Fortune), secondo un confronto di terze parti. Altri report:
  - Cashflow statement: griglia mensile di valori reali e previsti per categoria;
  - Income & Expense Statement, in stile conto economico;
  - Net Worth e Trends.
  
  Dashboard personalizzabili (una recensione parla di fino a 18 dashboard e 15 widget); riepiloghi via email programmati. — [Cashflow statement](https://learn.pocketsmith.com/reports/6a6X8SseDBrzYELeJ73BE2/the-cashflow-statement/6a6X8SseDBX2m4s8JkzR1J); [Reporting](https://www.pocketsmith.com/features/reporting/); [Plans](https://my.pocketsmith.com/plans)

**Empower Personal Dashboard**
- Net worth in tempo reale, cash flow (linea entrate contro uscite), budget di base, Retirement Planner a scenari, fee analyzer, asset allocation, savings planner (barra rispetto al fondo di emergenza). — [Empower tools](https://www.empower.com/personal-investors/financial-tools); [Rob Berger lug 2026](https://robberger.com/empower-review/); [NerdWallet](https://www.nerdwallet.com/finance/learn/empower-personal-dashboard-budget-app-review)

### Inferences
- Sezioni ricorrenti in quasi tutte: Dashboard/Home, Conti, Transazioni, Budget, Report, Ricorrenti/Bollette,
  Obiettivi/Salvadanai, Investimenti, Impostazioni. Dal 2025-26 molte hanno aggiunto un Assistente AI (Sure, Monarch, Wealthfolio).
- La tendenza 2025-26 nelle open source è la dashboard a widget configurabile: Actual (multi-dashboard), Sure (riordino
  e nascondi), ezBookkeeping (layout editor) e Wealthfolio. Firefly III resta a dashboard fissa.

### Gaps
- Elenco esatto e attuale delle voci della sidebar di Monarch (Recurring, Investments, Advice non confermati) e
  di Lunch Money: le pagine ufficiali non erano raggiungibili da questa sessione.
- Non ho letto i dettagli della Firefly III v2 ("layout v2"); ho guardato solo le viste v1.
- Lo stato dei report sperimentali Actual nella release rilasciata, rispetto al ramo principale, non è verificato.

## 2. Grafici standard, differenzianti, amati o richiesti

### Takeaway
Standard: ciambella o torta per categoria, barre entrate e uscite, linea del patrimonio netto, barre di avanzamento del budget.
Differenzianti: Sankey, calendario e heatmap, previsioni del saldo, linea del ritmo di spesa, report personalizzati
salvabili, treemap e sunburst. Le richieste più votate su Actual riguardano report personalizzati, previsioni e progresso
del budget.

### Cited Findings
- Actual, issue per voti 👍 (ricerca del 9 nov 2026):
  - #2965 "Progress bar for targets/templates" (210, chiusa);
  - #730 "Custom Reports" (163, chiusa);
  - #517 "Projected Balances Report" (140, chiusa);
  - #1346 "Spend by category" (83);
  - #1928 "Calendar view for scheduled items" (65);
  - #3248 "report on category balance" (61);
  - #4244 "Forecasting with Schedules and Running Balance Reports" (48);
  - #2673 "Financial planning and projections" (29);
  - #3130 "Custom reports split by Tags" (27);
  - #5062 "Budgeted type in Custom Report" (25);
  - #1919 "[Feedback]: Sankey Chart" (11, aperta, è la issue di feedback del Sankey sperimentale);
  - #1918 "[Feedback]: Custom Reports" (9).
  
  — [ricerca issue Actual](https://github.com/actualbudget/actual/issues?q=is%3Aissue+report+sort%3Areactions-%2B1-desc)
- Firefly III: le richieste sui report hanno pochi voti. Le principali sono il drill-down dal grafico alle transazioni (#3486) e l'esclusione per tag (#12590, 2026). — [issue Firefly](https://github.com/firefly-iii/firefly-iii/issues/3486)
- Sankey presente in Actual (sperimentale), Sure, ezBookkeeping, Wealthfolio e Monarch; assente in Firefly e Fava (grep). — vedi fonti alla sezione 1
- Linea del ritmo di spesa: Copilot (ideale tratteggiato contro reale). Barre colorate per ritmo nelle categorie. — [Copilot Dashboard Tab](https://help.copilot.money/en/articles/6045480-dashboard-tab-overview)
- Previsione e calendario del saldo: PocketSmith (anni), Actual Balance Forecast (sperimentale), Actual Crossover e Monte Carlo (FIRE). — fonti sezione 1
- Boxplot e candlestick per l'andamento dei saldi: solo ezBookkeeping; radar e Nightingale rose solo ezBookkeeping; scatter in Fava. — [statistics.ts](https://github.com/mayswind/ezbookkeeping/blob/main/src/core/statistics.ts); [fava charts](https://github.com/beancount/fava/tree/main/frontend/src/charts)
- Heatmap giorno × ora (ritmo di spesa): Wealthfolio. Heatmap e calendar heatmap: ezBookkeeping. Calendario giornaliero di entrate e uscite: Actual, Lunch Money, ezBookkeeping. — fonti sezione 1

### Inferences
- Per un'app italiana locale le aspettative minime sono ciambella per categoria, barre mensili, patrimonio netto e budget.
  I differenzianti con più domanda documentata sono: report personalizzato salvabile, previsione del saldo, Sankey
  e calendario.
- Waterfall: non l'ho trovato come tipo nativo in nessuna delle app analizzate. Le cose più vicine sono le barre divergenti
  del cash flow di Wealthfolio e la Budget Analysis di Actual.

### Gaps
- Nessuna metrica di voti per le app SaaS (Monarch e Copilot hanno bacheche di feedback non consultabili qui, a parte un
  titolo Copilot "Income vs. Expenses / Cash Flow Graph": [feedback.copilot.money](https://feedback.copilot.money/feature-requests/p/income-vs-expenses-cash-flow-graph)).
- Reddit non consultato: nessuna evidenza su quali grafici gli utenti "amano".

## 3. Pattern di interazione (drill-down, filtri, date, viste salvate, export)

### Takeaway
I pattern comuni sono: un selettore di periodo con preset più date personalizzate, filtri a chip e drill-down dal
grafico alla lista transazioni filtrata. Le viste salvate sono ormai diffuse (Actual, Monarch dal 2026, Lunch Money,
Fava via URL). L'export dei dati dei grafici è debole quasi ovunque: c'è il CSV delle transazioni, ma raramente l'immagine.

### Cited Findings
- Actual: date Live (relative, come "This month" o YTD) o Static. Filtri a regole condivisi con la lista transazioni. Salvataggio con "save as new" e "revert". Drill-down con `showActivity` verso le transazioni filtrate. Più dashboard. Il widget "Save widget" salva le impostazioni del report sulla card. — [custom-reports.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/reports/custom-reports.md); [showActivity.ts](https://github.com/actualbudget/actual/blob/master/packages/desktop-client/src/components/reports/graphs/showActivity.ts)
- Monarch: export CSV delle transazioni sottostanti (web), report salvati, l'app ricorda l'ultimo tipo di grafico, filtri per conto e tag. — [Using Reports](https://help.monarch.com/hc/en-us/articles/21846787088916-Using-Reports)
- Sure: PeriodPicker sulla dashboard e sui report, stampa del report, istruzioni per Google Sheets, sezioni riordinabili e nascondibili. — [reports/index.html.erb](https://github.com/we-promise/sure/blob/main/app/views/reports/index.html.erb)
- ezBookkeeping: tabella dati modificabile accanto al grafico nell'Explorer, query riutilizzabili, export del grafico come immagine richiesto in #711 (chiusa ott 2026), export Mermaid (`ExportMermaidChartType` nel codice). — [explorer.ts](https://github.com/mayswind/ezbookkeeping/blob/main/src/core/explorer.ts); [statistics.ts](https://github.com/mayswind/ezbookkeeping/blob/main/src/core/statistics.ts)
- Wealthfolio: il clic su una categoria o su una cella della heatmap apre un pannello (sheet) con le transazioni. — [heatmap-cell-sheet.tsx](https://github.com/afadil/wealthfolio/tree/main/apps/frontend/src/features/spending/components/reports)
- Fava: brush per selezionare il tempo trascinando sul grafico, filtro globale per tempo, conto e tag nell'header (stato nell'URL), clic sul nodo del treemap per navigare nel conto. — [Brush.svelte](https://github.com/beancount/fava/blob/main/frontend/src/charts/Brush.svelte)
- Copilot: confronto con il periodo precedente, sovrapposto come linea tratteggiata. — [Copilot Dashboard Tab](https://help.copilot.money/en/articles/6045480-dashboard-tab-overview)
- PocketSmith: riepiloghi via email programmati. ezBookkeeping: richiesta di report mensile via email (#591). — [PocketSmith Reporting](https://www.pocketsmith.com/features/reporting/); [issue ezB](https://github.com/mayswind/ezbookkeeping/issues)

### Matrice: tipi di grafico × app
Legenda: ● presente; ◐ sperimentale, parziale o non verificato direttamente; – non trovato.

| Tipo di grafico | Actual | Firefly | Sure | ezBook | Wealthf. | GnuCash | Fava | hledger-web | Monarch | Copilot | YNAB | LunchM | PocketS | Empower |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Ciambella/torta categorie | ● | ● | ● | ● | ● | ● | ◐ | – | ◐ | ◐ | ◐ | ● | ◐ | ◐ |
| Sunburst | – | – | – | ● | – | – | ● | – | – | – | – | – | – | – |
| Treemap | – | – | – | ● | ● (portaf.) | – | ● | – | – | – | – | – | – | – |
| Barre impilate per mese | ● | ● | ◐ | ● | ● | ● | ● | – | ● | – | ◐ | – | ◐ | – |
| Linea/area patrimonio netto | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Sankey | ◐ | – | ● | ● | ● | – | – | – | ● | – | – | – | – | – |
| Calendario/heatmap calendario | ● | – | – | ● | ● | – | – | – | ◐ | – | – | ● | ● | – |
| Heatmap categoria×mese o giorno×ora | – | – | – | ● | ● | – | – | – | – | – | – | – | – | – |
| Tabella categoria×mese | ● | ● | ● | ● | ● | ● | ● | ● | – | – | ● | ● | ● | – |
| Waterfall | – | – | – | – | ◐ (diverging) | – | – | – | – | – | – | – | – | – |
| Previsione saldo/bande | ◐ | – | ◐ (goal/loan) | – | – | – | – | – | – | – | – | – | ● | ● (pensione) |
| Progresso budget (barre) | ● | ● | ● | ● | ● | ◐ | ◐ | – | ● | ● | ● | ● | ● | ◐ |
| Ritmo di spesa/burn-down | – | – | – | ◐ | ◐ | – | – | – | – | ● | – | – | – | – |
| Scatter/bubble | – | – | – | ● | – | – | ● | – | – | – | – | – | – | – |
| Box plot/candlestick | – | – | – | ● | – | – | – | – | – | – | – | – | – | – |
| Confronti YoY/MoM | ● | ◐ | ● | ◐ | ● | – | – | – | ◐ | ● | – | ◐ | ◐ | – |
| Costruttore di report personalizzati | ● | ◐ | – | ● | – | ◐ | ● (query) | – | ● | – | – | ● | ◐ | – |
| Report salvati | ● | – | – | ◐ | – | ● | ◐ (URL) | – | ● | – | – | ● | – | – |
| Dashboard a widget personalizzabile | ● | – | ● | ● | ◐ | – | – | – | ● | – | – | – | ● | – |

Note sulla matrice. Le celle delle app SaaS si basano su riassunti di WebSearch, non su verifiche dirette.
Il "◐" su Firefly per il report builder indica che i report sono configurabili (conti, budget, categorie, tag, periodo) ma
hanno un layout fisso. GnuCash ha opzioni per ogni report e "saved report configurations"; il nome della funzione
viene dalla mia conoscenza generale, non da una fonte di questa sessione.

### Inferences
- Il drill-down dal grafico alle transazioni è la richiesta d'interazione più trasversale (Firefly #3486, Actual
  showActivity, Wealthfolio sheet). Costa poco se la lista transazioni accetta già i filtri via URL o parametri.
- L'export dell'immagine del grafico manca quasi ovunque, e lo chiedono gli utenti (ezB #711): è un piccolo
  differenziante possibile.

### Gaps
- Dettagli d'interazione di YNAB, Lunch Money e PocketSmith (drill-down, export) non verificati nelle pagine ufficiali.
- Celle "–" nella matrice per le SaaS: significano "non trovato in questa sessione", non "assente".
