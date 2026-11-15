# Progetti open source per patrimonio e investimenti su GitHub, novembre 2026

Raccolta del 9 novembre 2026. Stelle, fork, licenza, linguaggio, data di creazione e issue aperte vengono dall'API di ricerca GitHub (`search/repositories`, `search/issues`), interrogata oggi.

Le altre metriche vengono da cloni git "commit-only" (`--filter=tree:0`) dei repository:
- **"Autori"**: indirizzi email distinti degli autori dei commit. È un'approssimazione del numero di contributori: include i bot e conta due volte chi usa due indirizzi.
- **Release**: tag git con la loro data.
- **Commit 2026**: commit dal 1° gennaio 2026 in poi.

In questa sessione non erano raggiungibili gli endpoint REST `/repos/...` (contributors e releases), GraphQL e i siti dei progetti (ghostfol.io, wealthfolio.app, rotki.com). I prezzi vengono quindi da ricerche web e dal codice sorgente, e sono segnalati come tali dove serve.

## 1. Tabella dei progetti: metriche, stack, funzioni (dati al 2026-11-09)

### Takeaway
I leader per stelle tra i tracker di patrimonio e investimenti sono:
- **Sure** (fork di Maybe): 11,2k stelle
- **Ghostfolio**: 9,7k
- **Wealthfolio**: 9,4k
- **Portfolio Performance**: 4,2k
- **Rotki**: 4,1k

Wealthfolio è il concorrente più vicino a MyFinancePlace. È un'app desktop locale (Tauri/Rust) che a novembre 2026 copre già budget, debiti con piano di ammortamento, FIRE, AI locale, app mobile, localizzazione italiana e un preset italiano per categorizzare le spese.

Portfolio Performance è lo standard di fatto per l'import dei PDF dei broker europei. Ha 146 estrattori PDF, tra cui Directa SIM, Degiro, Trade Republic, Scalable, Revolut e Trading212, ma non Fineco.

Nessun progetto grande gestisce la fiscalità italiana (regime amministrato o dichiarativo). L'unico progetto con logica fiscale italiana esplicita è il piccolo GiuseppeDM98/net-worth-tracker (79 stelle).

### Cited Findings

**Tabella metriche (2026-11-09)**

| Progetto | Stelle | Fork | Autori (tutti / 2026) | Commit 2026 | Ultima release stabile | Release 2026 (tag) | Licenza | Stack | Forma |
|---|---|---|---|---|---|---|---|---|---|
| [we-promise/sure](https://github.com/we-promise/sure) | 11.191 | 771 | 468 / 309 | 2.321 | v0.7.6 (2026-10-30); alpha v0.7.7-alpha.4 (2026-11-09) | 20 tag; stabili circa mensili da v0.6.7 (31 gen) a v0.7.6 | AGPL-3.0 | Ruby on Rails, PostgreSQL | Self-hosted Docker, browser, app desktop macOS, app mobile, API, agenti LLM |
| [ghostfolio/ghostfolio](https://github.com/ghostfolio/ghostfolio) | 9.677 | 1.409 | 330 / 83 | 1.627 | 3.99.0 (2026-11-07) | 144 (da 2.226.0 del 1° gen a 3.99.0); una ogni 1–3 giorni | AGPL-3.0 | TypeScript: Angular, NestJS, Prisma, PostgreSQL, Redis, Nx | Self-hosted Docker (amd64/arm), cloud SaaS, PWA mobile-first |
| [wealthfolio/wealthfolio](https://github.com/wealthfolio/wealthfolio) (ex afadil/wealthfolio) | 9.394 | 810 | 113 / 92 | 4.626 | v3.12.0 (2026-11-01) | 33 tag; stabili da v3.0.0 (2026-02-24) a v3.12.0, circa 2–3 a settimana fino a una ogni 2–3 settimane | AGPL-3.0 | Rust, Tauri, React/TypeScript, SQLite; server REST Axum | Desktop Win/macOS/Linux, iOS, Android, self-hosted Docker/web |
| [maybe-finance/maybe](https://github.com/maybe-finance/maybe) | 54.195 | 5.665 | n.d. | 0 (ultimo push 2025-07-24) | v0.6.0 (finale) | 0 | AGPL-3.0 | Ruby on Rails | **Archiviato** |
| [beancount/beancount](https://github.com/beancount/beancount) | 6.155 | 486 | 104 / 10 | 41 | 3.2.3 (2026-05-05) | 3 | GPL-2.0 | Python | CLI, testo semplice |
| [portfolio-performance/portfolio](https://github.com/portfolio-performance/portfolio) | 4.155 | 841 | 308 / 71 | 931 | 0.90.0 (2026-11-01) | 23 tag (da 0.81.1 dell'11 gen), circa ogni 17 giorni | EPL-1.0 | Java, Eclipse RCP | Desktop Win/macOS/Linux |
| [rotki/rotki](https://github.com/rotki/rotki) | 4.084 | 788 | 250 / 43 | 4.134 | v1.44.2 (2026-10-22) | 8 (da v1.42.0 del 20 feb a v1.44.2) | AGPL-3.0 | Python, Vue/Electron | Desktop locale, Docker |
| [beancount/fava](https://github.com/beancount/fava) | 2.602 | 423 | 141 / 28 | 201 | v1.30.16 (2026-08-18) | 9 | MIT | Python | Web locale |
| [gloom-sh/gloomberb](https://github.com/gloom-sh/gloomberb) | 2.680 | 193 | n.d. | n.d. | n.d. | n.d. | MIT | TypeScript | Terminale ("finance terminal") |
| [RIP-Comm/sossoldi](https://github.com/RIP-Comm/sossoldi) (team italiano) | 1.416 | 218 | 74 / 10 | 88 | 1.0.0 (2026-08-20) | 2 | MIT | Dart, Flutter | Mobile/desktop |
| [investbrainapp/investbrain](https://github.com/investbrainapp/investbrain) | 940 | 76 | 13 / 6 | 129 | v1.4.1 (2026-11-05) | 10 | NOASSERTION (licenza non riconosciuta da GitHub) | PHP (Laravel) | Self-hosted Docker e cloud (investbra.in) |
| [LuoDi-Nate/financial-management](https://github.com/LuoDi-Nate/financial-management) | 376 | 46 | n.d. | n.d. | n.d. | n.d. | AGPL-3.0 | Java | Self-hosted (Cina): XIRR/TWR, "check-up AI" del patrimonio |
| [LosaLosSantos/aurelio-finance](https://github.com/LosaLosSantos/aurelio-finance) | 349 | 105 | n.d. | n.d. | n.d. | n.d. | MIT | Python e Node | App locale (localhost), consulente AI via OpenRouter |
| [spacious-team/investbook](https://github.com/spacious-team/investbook) | 336 | 106 | n.d. | n.d. | n.d. | n.d. | AGPL-3.0 | Java | Locale/self-hosted (Russia), commissioni e tasse |
| [Zproger/Aurum](https://github.com/Zproger/Aurum) | 271 | 40 | n.d. | n.d. | n.d. | n.d. | NOASSERTION | TypeScript | Self-hosted |
| [open-net-worth-ai/open-net-worth](https://github.com/open-net-worth-ai/open-net-worth) | 250 | 20 | n.d. | n.d. | n.d. | n.d. | AGPL-3.0 | Python | Self-hosted, agente AI |
| [letehaha/moneymatter](https://github.com/letehaha/moneymatter) | 224 | 89 | n.d. | n.d. | n.d. | n.d. | AGPL-3.0 | TypeScript | Self-hosted, sincronizzazione bancaria |
| [GiuseppeDM98/net-worth-tracker](https://github.com/GiuseppeDM98/net-worth-tracker) (italiano) | 79 | 19 | 5 / 4 | 1.223 | v11.0.0 (2026-10-08) | 11 (da v3.0.0 del 20 gen) | AGPL-3.0 | Next.js, TypeScript, Firebase, Vercel | Web (Vercel o self-hosted) |
| [finanze/finanze](https://github.com/finanze/finanze) | 74 | 13 | n.d. | n.d. | n.d. | n.d. | AGPL-3.0 | Python | Self-hosted: aggrega banche e investimenti (focus Spagna, da verificare) |
| [quovibe-web/quovibe](https://github.com/quovibe-web/quovibe) | 17 | 6 | n.d. | n.d. | n.d. | n.d. | AGPL-3.0 | TypeScript | Self-hosted: TTWROR, IRR, Sharpe |

Fonte della tabella: API di ricerca GitHub, interrogata il 2026-11-09, più i cloni git dei repository linkati. Ghostfolio aveva 9,7k stelle e 1,4k fork anche sulla [pagina del repo](https://github.com/ghostfolio/ghostfolio).

**Wealthfolio (il concorrente più vicino a MyFinancePlace)**
- Si presenta come "open-source, private portfolio tracker — investments, net worth, spending, and simulations", con dati in locale, nessun account e "free forever". — [README](https://github.com/wealthfolio/wealthfolio)
- Calcola rendimenti time-weighted e money-weighted, confronto con benchmark e quattro metodi di costo: FIFO, costo medio ponderato, LIFO, HIFO. — [README](https://github.com/wealthfolio/wealthfolio)
- Patrimonio netto: passività, prestiti e mutui con piano di ammortamento, asset alternativi (immobili, veicoli, collezionismo). — [README](https://github.com/wealthfolio/wealthfolio), [ROADMAP](https://github.com/wealthfolio/wealthfolio/blob/main/ROADMAP.md)
- Gestisce opzioni e posizioni short. — [README](https://github.com/wealthfolio/wealthfolio), [ROADMAP](https://github.com/wealthfolio/wealthfolio/blob/main/ROADMAP.md)
- Budget e spese: categorie, regole, budget, eventi, insight (fase 7 completata). — [ROADMAP](https://github.com/wealthfolio/wealthfolio/blob/main/ROADMAP.md)
- Obiettivi: simulazione di obiettivi di risparmio e simulatore di pensione/FIRE. — [ROADMAP](https://github.com/wealthfolio/wealthfolio/blob/main/ROADMAP.md)
- Ribilanciamento verso allocazioni target. — [ROADMAP](https://github.com/wealthfolio/wealthfolio/blob/main/ROADMAP.md)
- Assistente AI con modelli locali (Ollama, LM Studio) o chiave propria (OpenAI, Anthropic, Gemini, Groq, OpenRouter). Importa CSV via AI ed espone un server MCP per Claude, ChatGPT e Cursor. — [ROADMAP](https://github.com/wealthfolio/wealthfolio/blob/main/ROADMAP.md), [README](https://github.com/wealthfolio/wealthfolio)
- Fornitori di prezzi: Yahoo Finance, Alpha Vantage, MarketData.app, Finnhub, Börse Frankfurt, AMFI e Metal Price API, più fornitori personalizzati. — [ROADMAP](https://github.com/wealthfolio/wealthfolio/blob/main/ROADMAP.md)
- Sistema di addon con SDK TypeScript, sandbox, catalogo e marketplace. — [README](https://github.com/wealthfolio/wealthfolio)
- Sicurezza: crittografia opzionale del database, blocco dell'app, profili separati, backup protetti da password, SSO OIDC nella versione self-hosted. — [ROADMAP](https://github.com/wealthfolio/wealthfolio/blob/main/ROADMAP.md)
- 11 lingue. — [ROADMAP](https://github.com/wealthfolio/wealthfolio/blob/main/ROADMAP.md)
- Prossimi passi dichiarati: CLI per agenti, conti a margine, costo fiscale aggregato tra conti (ACB) e selezione dei lotti specifici. — [ROADMAP](https://github.com/wealthfolio/wealthfolio/blob/main/ROADMAP.md)
- **Segnali Italia nel 2026:**
  - Il 30 agosto 2026 è stata unita una PR della community (MobilettoSoft) per la localizzazione italiana, con "Italy as a formatting region".
  - Il 25 ottobre 2026 è stato aggiunto un preset italiano per la categorizzazione delle spese, con commit "feat(spending): add Italian categorization preset" e "prioritize Italian internet and utility rules".
  - Fonte: storico commit del [repo](https://github.com/wealthfolio/wealthfolio/pull/1588).
- Import broker: CSV con mappatura dei campi e template, per esempio Wealthsimple dal 29 marzo 2026. I commit non menzionano parser specifici per Fineco, Directa, Degiro, Trade Republic, Scalable, IBKR o Revolut. La sincronizzazione automatica dei broker passa da Connect ("30+ institutions, read-only"). — [README](https://github.com/wealthfolio/wealthfolio), storico commit
- L'issue #753 (marzo 2026) chiede un import CSV corretto dei BTP: quantità nominale e prezzo in percentuale. — [issue #753](https://github.com/wealthfolio/wealthfolio/issues/753)

**Ghostfolio**
- Calcola la performance come ROAI (Return on Average Investment) inclusi i dividendi, sui periodi Today, WTD, MTD, YTD, 1Y, 5Y e Max. Il README non cita la TWR. — [repo](https://github.com/ghostfolio/ghostfolio)
- Fonti dati: Yahoo, CoinGecko, Manual. GHOSTFOLIO è una fonte solo Premium; Premium usa inoltre "professional data providers". — [repo](https://github.com/ghostfolio/ghostfolio)
- Funzioni Premium: Portfolio Summary, Portfolio Allocations, Performance Benchmarks, FIRE Calculator, Ghostfolio MCP e Professional Data Provider. — [sorgente pricing-page.html](https://github.com/ghostfolio/ghostfolio/blob/main/apps/client/src/app/pages/pricing/pricing-page.html)
- Server MCP sperimentale, disattivato di default. — [repo](https://github.com/ghostfolio/ghostfolio)
- Release 3.90–3.99 (21 ottobre–7 novembre 2026): import con "Ghostfolio AI" (sperimentale), endpoint OAuth 2.1 per MCP, mappatura dei settori da Trackinsight. — [releases](https://github.com/ghostfolio/ghostfolio/releases)
- Lo storico commit non contiene parser per singoli broker. "Degiro", "Trade Republic", "Fineco" e "Directa" compaiono in 0 commit; "Interactive Brokers" in uno solo. L'import è CSV/JSON generico. — storico commit del [repo](https://github.com/ghostfolio/ghostfolio)
- La traduzione italiana è aperta come issue #3587 ("Ghostfolio in Italiano", 11 commenti). — [issue #3587](https://github.com/ghostfolio/ghostfolio/issues/3587)

**Portfolio Performance (PP)**
- 146 estrattori PDF di banche e broker in `datatransfer/pdf/`. Tra questi: DirectaSim, Degiro, TradeRepublic, ScalableCapital, RevolutLtd, Trading212, Unicredit (probabilmente UniCredit/HypoVereinsbank Germania, da verificare), SaxoBank, Swissquote, BourseDirect, BoursoBank, INGDiBa, OpenBankSA, Robinhood e Schwab. **Non c'è Fineco, Intesa, Banca Sella né Webank.** Interactive Brokers si importa via Flex. — [sorgente](https://github.com/portfolio-performance/portfolio/tree/master/name.abuchen.portfolio/src/name/abuchen/portfolio/datatransfer/pdf), [releases](https://github.com/portfolio-performance/portfolio/releases)
- Directa SIM: importer PDF aggiunto il 2024-01-08; supporto alle vendite aggiunto il 2026-01-14 (#5322). — storico commit del [repo](https://github.com/portfolio-performance/portfolio)
- Release 2026:
  - 0.90.0 (1° novembre): widget "Volatility (annualized)", importer CSV per XTB, 19 importer migliorati.
  - 0.89.0 (11 ottobre): endpoint MCP sperimentale per assistenti AI.
  - 0.88.0 (4 ottobre): fornitore di prezzi storici "Sifting".
  - 0.85.0 (7 luglio): quote di proprietà sui conti raggruppati.
  - Fonte: [releases](https://github.com/portfolio-performance/portfolio/releases)
- Traduzione italiana aggiornata regolarmente: 8 commit "Updated Italian translation" da marzo a ottobre 2026. — storico commit del [repo](https://github.com/portfolio-performance/portfolio)

**Sure (fork di Maybe)**
- È un "community fork of the now-abandoned Maybe Finance project". Si usa da browser, app desktop macOS, app mobile, API e agenti LLM. — [README](https://github.com/we-promise/sure)
- Nello storico commit, "Enable Banking" (open banking europeo) compare in 67 commit, "IBKR" in 39, "Trade Republic" in 35. — storico commit del [repo](https://github.com/we-promise/sure)
- L'issue #392, "Add/Sync Trade Republic data" (11 reazioni, 21 commenti), è chiusa. — [issue #392](https://github.com/we-promise/sure/issues/392)

**Investbrain**
- "Smart LLM-enabled investment tracker". Offre cloud (investbra.in) o self-hosted Docker, chat AI, server MCP, API REST, dividendi e frazionamenti. — [README](https://github.com/investbrainapp/investbrain)

**GiuseppeDM98/net-worth-tracker (italiano)**
- Si descrive come "built for Italian investors". — [README](https://github.com/GiuseppeDM98/net-worth-tracker)
- Prezzi da Yahoo Finance e da Borsa Italiana (BTP per ISIN). Calendario delle cedole con step-up e premio finale, compatibile con BTP Valore. — [README](https://github.com/GiuseppeDM98/net-worth-tracker)
- Calcolatore del prezzo medio di carico (PMC) su più broker. — [README](https://github.com/GiuseppeDM98/net-worth-tracker)
- Stima della plusvalenza "as a broker in regime amministrato computes it", con aliquota 12,5% sui BTP e 26% sulle azioni. Imposta di bollo allo 0,2%. "Plusvalenze realizzate" per anno fiscale. — [README](https://github.com/GiuseppeDM98/net-worth-tracker)
- Fondo pensione, TWR, benchmark contro portafogli modello, Monte Carlo, FIRE e analisi AI con Claude. — [README](https://github.com/GiuseppeDM98/net-worth-tracker)
- Stack Firebase e Vercel: non è un'app desktop locale. — [README](https://github.com/GiuseppeDM98/net-worth-tracker)

### Inferences
- Tre dei cinque progetti principali (Ghostfolio, Sure, Investbrain) sono app web self-hosted con PostgreSQL o Rails. Solo Wealthfolio, PP e Rotki sono desktop locali. Il posizionamento "desktop locale" di MyFinancePlace si scontra soprattutto con Wealthfolio, che ha la stessa filosofia, più l'app mobile, ed è gratuito.
- Il vuoto più chiaro per MyFinancePlace è la fiscalità italiana: regime amministrato o dichiarativo, compensazione delle minusvalenze ("zainetto"), bollo e IVAFE, quadro RW/RT. Gli unici a coprirla, in parte, sono un progetto da 79 stelle e il PP sviluppato in Germania (che ha fiscalità tedesca, non italiana).
- Il secondo vuoto è l'import Fineco, che manca in tutti i progetti esaminati. Directa è coperta solo da PP.
- Wealthfolio ha aggiunto la lingua italiana e regole di categorizzazione italiane nell'autunno 2026: è un segnale che sta entrando nel mercato italiano.

### Gaps
- Le cifre esatte dei contributori GitHub non sono disponibili (endpoint `/contributors` bloccato). Ho usato gli autori distinti dei commit come approssimazione.
- Non ho trovato dati affidabili su Kubera-like OSS e su Firefly III (fuori ambito, budget).
- Per Rotki non ho verificato funzioni fiscali specifiche per l'Italia.
- Per gloomberb, Aurum, open-net-worth e finanze ho solo metriche di ricerca, senza release o contributori.
- Non ho verificato la lista completa dei fornitori di prezzi di Ghostfolio Premium.

## 2. Issue e richieste più votate o commentate (Ghostfolio, Wealthfolio, PP, Sure)

### Takeaway
Le richieste ricorrenti sono:
- Import da broker: convertitori CSV, Trading212, Trade Republic, BTP, ETF look-through.
- Calcoli di performance corretti e trasparenti: total return con dividendi, performance assoluta, bug nei calcoli.
- Copertura di obbligazioni e crypto.
- Metodi di costo e fiscalità locale: ACB canadese, costo medio, LIFO.
- Packaging (flatpak, deb), database scelto dall'utente o sincronizzabile.

Le issue di Ghostfolio hanno pochi voti (massimo 11 reazioni), perché la discussione avviene soprattutto in Discussions e Discord. PP ha la richiesta più votata in assoluto: il redesign della UI, con 40 reazioni.

### Cited Findings

**Wealthfolio** (469 issue aperte al 2026-11-09)
- [#418 Add converters for popular brokerage CSV formats](https://github.com/wealthfolio/wealthfolio/issues/418): 14 reazioni.
- [#590 Missing FX Conversion Activity Support](https://github.com/wealthfolio/wealthfolio/issues/590) (v3 beta): 12 reazioni.
- [#219 Crypto tickers and realtime price updates](https://github.com/wealthfolio/wealthfolio/issues/219): 11 reazioni.
- [#393 Trading212 API](https://github.com/wealthfolio/wealthfolio/issues/393): 9 reazioni.
- [#197 SimpleFIN integration](https://github.com/wealthfolio/wealthfolio/issues/197): 9 reazioni, 12 commenti.
- [#98 Flatpak](https://github.com/wealthfolio/wealthfolio/issues/98): 8 reazioni.
- [#339 Short positions](https://github.com/wealthfolio/wealthfolio/issues/339): 8 reazioni. La roadmap le dà già come fatte.
- [#862 Canadian ACB per le plusvalenze](https://github.com/wealthfolio/wealthfolio/issues/862): 8 reazioni.
- [#434 Tracking of bond holdings](https://github.com/wealthfolio/wealthfolio/issues/434): 7 reazioni.
- [#344 Posizione del database personalizzabile (backup cloud e multi-dispositivo)](https://github.com/wealthfolio/wealthfolio/issues/344): 7 reazioni.
- [#499 Simboli manuali e import CSV senza prezzo e quantità](https://github.com/wealthfolio/wealthfolio/issues/499): 6 reazioni.
- Le più commentate:
  - [#223 AppImage vuota](https://github.com/wealthfolio/wealthfolio/issues/223): 16 commenti.
  - [#303 Performance mostrata in modo errato](https://github.com/wealthfolio/wealthfolio/issues/303): 15 commenti.
  - [#601 Allocation targets e rebalancing advisor](https://github.com/wealthfolio/wealthfolio/issues/601): 8 commenti.
  - [#1119 "Odd calculations all over the place after 3.5 update"](https://github.com/wealthfolio/wealthfolio/issues/1119): 7 commenti.
- Rilevanti per l'Italia:
  - [#753 Import BTP con nominale e prezzo in percentuale](https://github.com/wealthfolio/wealthfolio/issues/753).
  - [#771 Metodi di costo configurabili (costo medio ponderato, LIFO)](https://github.com/wealthfolio/wealthfolio/issues/771), che cita Fineco.
  - [#605 Dati Euronext](https://github.com/wealthfolio/wealthfolio/issues/605).
  - [#1939 Commissioni in un'altra valuta o su un altro conto (caso Degiro)](https://github.com/wealthfolio/wealthfolio/issues/1939).

**Ghostfolio** (173 issue aperte)
- [#5924 Raccolta dati da Trackinsight non funzionante](https://github.com/ghostfolio/ghostfolio/issues/5924): 11 reazioni, 28 commenti.
- [#2115 Docker Secrets](https://github.com/ghostfolio/ghostfolio/issues/2115): 7 reazioni.
- [#5324 Clonare un'attività con asset manuale crea un asset nuovo](https://github.com/ghostfolio/ghostfolio/issues/5324): 7 reazioni, 25 commenti.
- [#7468 Total Return e Annualized Total Return inclusi i dividendi](https://github.com/ghostfolio/ghostfolio/issues/7468) (luglio 2026): 6 reazioni.
- [#524 Panoramica per singolo conto](https://github.com/ghostfolio/ghostfolio/issues/524): 5 reazioni.
- Bug di calcolo della performance:
  - [#3416](https://github.com/ghostfolio/ghostfolio/issues/3416): 14 commenti.
  - [#5793](https://github.com/ghostfolio/ghostfolio/issues/5793): 20 commenti.
- [#512 Dividends](https://github.com/ghostfolio/ghostfolio/issues/512): 17 commenti, aperta dal 2021.
- [#2640 Dati storici Yahoo mancanti](https://github.com/ghostfolio/ghostfolio/issues/2640): 23 commenti.
- [#5193 Import CSV di asset manuali errato](https://github.com/ghostfolio/ghostfolio/issues/5193): 27 commenti.
- [#6482 Crash quando mancano i tassi di cambio](https://github.com/ghostfolio/ghostfolio/issues/6482).

**Portfolio Performance** (342 issue aperte)
- [#1921 Proposta di nuovo design della UI](https://github.com/portfolio-performance/portfolio/issues/1921): 40 reazioni, 34 commenti.
- [#1665 Estrarre l'asset allocation degli ETF (paesi, settori, valute) dalle liste di holding](https://github.com/portfolio-performance/portfolio/issues/1665): 14 reazioni, 25 commenti.
- [#2216 PP con un database](https://github.com/portfolio-performance/portfolio/issues/2216): 10 reazioni, 25 commenti.
- [#1835 Asset swap](https://github.com/portfolio-performance/portfolio/issues/1835): 9 reazioni.
- [#1132 Performance di conti P2P e conti deposito](https://github.com/portfolio-performance/portfolio/issues/1132): 8 reazioni.
- [#5612 Trasferimenti di fondi in stile Spagna](https://github.com/portfolio-performance/portfolio/issues/5612) (aprile 2026): 6 reazioni.
- [#4864 Widget di performance assoluta o total return %](https://github.com/portfolio-performance/portfolio/issues/4864): 6 reazioni.
- [#2827 Pacchetto Debian](https://github.com/portfolio-performance/portfolio/issues/2827).
- [#5453 Obbligazioni con prezzo in percentuale](https://github.com/portfolio-performance/portfolio/issues/5453): 17 commenti, febbraio 2026.
- [#5863 Import doloroso per i broker mobile-first, i cui documenti esistono solo sul telefono](https://github.com/portfolio-performance/portfolio/issues/5863) (luglio 2026).
- [#1184 Importer scriptabili](https://github.com/portfolio-performance/portfolio/issues/1184): 18 commenti.

**Sure (parte investimenti)**
- [#1313 Versamenti negli investimenti trattati come trasferimenti, non come spese](https://github.com/we-promise/sure/issues/1313): 7 reazioni.
- [#1804 Piani di ammortamento nativi per i prestiti](https://github.com/we-promise/sure/issues/1804): 5 reazioni.
- [#3723 Proprietà percentuale degli asset di famiglia](https://github.com/we-promise/sure/issues/3723): 3 reazioni.
- [#3494 Investment/Trading upgrades](https://github.com/we-promise/sure/issues/3494).
- [#10 Calcolo del patrimonio netto errato](https://github.com/we-promise/sure/issues/10): 26 commenti.
- [#3364 Import degli importi di dividendi e interessi](https://github.com/we-promise/sure/issues/3364).

Fonte delle classifiche: API di ricerca GitHub, issue aperte ordinate per reazioni e per commenti, interrogata il 2026-11-09.

### Inferences
- Le richieste più comuni riguardano funzioni che MyFinancePlace ha già o può differenziare: import dei broker locali, ammortamento dei debiti (che Sure non ha), obbligazioni e BTP, total return con dividendi, metodi di costo per la fiscalità locale.
- La fiducia nei calcoli di performance è un punto debole ricorrente (Ghostfolio #3416 e #5793, Wealthfolio #303 e #1119). Una spiegazione trasparente dei calcoli può distinguere MyFinancePlace.

### Gaps
- Non ho potuto interrogare le GitHub Discussions (voti delle idee di Ghostfolio e Wealthfolio), né il Discord o il forum di PP (forum.portfolio-performance.info), dove si trova gran parte delle richieste.

## 3. Modelli di business e prezzi

### Takeaway
Il modello dominante è "open core / servizio": l'app è gratuita (AGPL) e si paga il servizio, cioè hosting, dati di mercato professionali, sincronizzazione dei broker e dei dispositivi.

| Progetto | Offerta a pagamento | Prezzo |
|---|---|---|
| Ghostfolio | Premium cloud; da novembre 2026 anche il piano "Max" | Circa 48 $/anno (non confermato da fonte primaria) |
| Wealthfolio | Connect (sync broker e dispositivi) | Circa 3,99 $/mese (non confermato) |
| Rotki | Premium a livelli | Basic 25 €/mese IVA inclusa (dal 10 novembre 2025) |
| Portfolio Performance | Nessuna | — |
| Investbrain | Versione cloud | Prezzo non trovato |

### Cited Findings
- **Ghostfolio**
  - Piani: Basic gratuito, Premium e, dal 2 novembre 2026, un piano "Max" ("For seasoned investors who manage multiple portfolios… Up to 5 User Accounts, Centralized User Management"). — [sorgente pricing-page.html](https://github.com/ghostfolio/ghostfolio/blob/main/apps/client/src/app/pages/pricing/pricing-page.html), commit "Feature/Max plan on pricing page (#8376)" del 2026-11-02
  - I prezzi sono dinamici (Stripe, "per year") e prevedono uno sconto studenti. Nell'ottobre 2026 sono state aggiunte varianti di trial (#8258). — stesso sorgente e commit
  - Il riassunto di una ricerca web della pagina ufficiale indica Premium a **48 $/anno**. Altri siti riportano 15 $/anno, 40 $/anno e 83,88 $/anno. Non sono riuscito a leggere direttamente ghostfol.io (host bloccato). — [ghostfol.io/en/pricing](https://ghostfol.io/en/pricing) via ricerca web, [findmymoat](https://www.findmymoat.com/tools/ghostfolio), [sourceforge](https://sourceforge.net/software/product/Ghostfolio/)
  - Il ricavo "is used to cover operational costs for the hosting infrastructure and professional data providers, and to fund ongoing development". — [sorgente pricing-page.html](https://github.com/ghostfolio/ghostfolio/blob/main/apps/client/src/app/pages/pricing/pricing-page.html)
- **Wealthfolio**
  - Wealthfolio Connect è "an optional subscription that covers the real cost of the brokerage data connections". Comprende sincronizzazione automatica dei broker (30+ istituti, sola lettura), sincronizzazione E2EE tra dispositivi e backup cloud cifrati. L'app resta gratuita. — [README](https://github.com/wealthfolio/wealthfolio), [ROADMAP](https://github.com/wealthfolio/wealthfolio/blob/main/ROADMAP.md)
  - La roadmap riassume: "Free or pay once to support". — [ROADMAP](https://github.com/wealthfolio/wealthfolio/blob/main/ROADMAP.md)
  - Prezzo di Connect da fonti terze, non ufficiali: 3,99 $/mese (Toolradar). FindMyMoat riporta un livello gratuito "Connect Basic" con sync per una persona e "Connect Essentials" a 3,99 $/mese. Non ho trovato una pagina prezzi ufficiale. — [toolradar](https://toolradar.com/tools/wealthfolio/pricing), [findmymoat](https://www.findmymoat.com/tools/wealthfolio)
- **Rotki**
  - Premium a livelli. Dal 10 novembre 2025 i piani trimestrali e semestrali passano alla fatturazione mensile del livello Basic, a **25 €/mese IVA inclusa**. Il prezzo era invariato dal 2017. — [blog rotki, 13/10/2025](https://blog.rotki.com/2025/10/13/rotki-tiers/)
  - Esistono livelli superiori (per esempio Advanced) e piani su misura. — [docs](https://docs.rotki.com/premium/plans-and-pricing.html)
  - Nel codice, ottobre 2026, c'è un limite di dimensione dei backup per livello ("Abort backup early when over tier size limit"). — storico commit del [repo](https://github.com/rotki/rotki)
- **Maybe Finance**: il team ha speso "nearly $1 million on development"; il B2C ospitato "didn't work out". Sure prosegue come fork della community. — [README Sure](https://github.com/we-promise/sure)
- **Investbrain**: offre una versione cloud (investbra.in) accanto al self-hosted. — [README](https://github.com/investbrainapp/investbrain)
- **Portfolio Performance**: nessun livello a pagamento risulta dai materiali consultati.

### Inferences
- MyFinancePlace ha licenza proprietaria ed è desktop locale. I concorrenti diretti sono gratuiti e incassano solo sui servizi che hanno costi marginali: dati, sync, hosting. Per giustificare un prezzo servono funzioni che nessun OSS copre, come la fiscalità italiana, l'import Fineco e delle banche italiane e i rendiconti contabili. Le funzioni base di tracking non bastano.
- Il prezzo di riferimento del mercato OSS è basso: da circa 4 $/mese (Wealthfolio Connect, Ghostfolio) a 25 €/mese (Rotki, crypto e fiscale).

### Gaps
- Prezzi ufficiali di Ghostfolio Premium e Max, Wealthfolio Connect, Rotki Advanced e Investbrain Cloud non verificati sulle pagine primarie: gli host erano bloccati nella sessione.
- Non ho dati su ricavi o numero di utenti paganti.

## 4. Segnali di crescita 2025–2026

### Takeaway
I segnali di crescita più forti sono:
- **Wealthfolio**: 9,4k stelle in circa 2,5 anni; v2.0 a novembre 2025, v3.0 a febbraio 2026, 12 minor release fino a v3.12; app iOS e Android, AI e MCP.
- **Sure**: 11,2k stelle in circa 16 mesi, 309 autori nel 2026.

Nel 2026 l'AI arriva in tutti i progetti principali, soprattutto attraverso server MCP: Wealthfolio, Ghostfolio, PP (0.89), Investbrain e Sure. Il numero di nuovi progetti piccoli con "AI advisor" e "local-first" è molto alto.

### Cited Findings
- **Wealthfolio**
  - Creato il 2024-05-27; 9.394 stelle al 2026-11-09. — [repo](https://github.com/wealthfolio/wealthfolio)
  - Tag v2.0.0 il 2025-11-20; v3.0.0 (dopo le beta da 3.0.0-beta.1 del 10 febbraio) il 2026-02-24; v3.12.0 il 2026-11-01. — tag git del [repo](https://github.com/wealthfolio/wealthfolio)
  - 4.626 commit e 92 autori distinti nel 2026, contro 113 in tutta la storia. — tag git del [repo](https://github.com/wealthfolio/wealthfolio)
  - App iOS sull'App Store e pagina download che indica la 3.12.0 del 1° novembre 2026. — [App Store](https://apps.apple.com/us/app/wealthfolio-private-finance/id6732888445), [docs mobile](https://wealthfolio.app/docs/guide/mobile/), via ricerca web
  - Il repository è passato da afadil/wealthfolio all'organizzazione wealthfolio/wealthfolio. — [repo](https://github.com/wealthfolio/wealthfolio)
- **Sure**: creato il 2025-07-23, 11.191 stelle, 468 autori in totale (309 nel 2026), 2.321 commit nel 2026. Release stabili mensili, con un tag a calendario "v2026.11.8-alpha" a novembre 2026. — [repo](https://github.com/we-promise/sure)
- **Maybe**: archiviato con 54.195 stelle; ultimo push il 2025-07-24. — [repo](https://github.com/maybe-finance/maybe)
- **Ghostfolio**: 144 release nel 2026, dalla 2.226.0 alla 3.99.0, quindi il salto di major 2→3 è avvenuto nel 2026. 83 autori e 1.627 commit nel 2026. Attività AI e MCP: 31 commit con "MCP"; import con "Ghostfolio AI" a ottobre 2026; piano Max a novembre 2026. — storico git e [releases](https://github.com/ghostfolio/ghostfolio/releases)
- **Portfolio Performance**: 23 tag nel 2026, 71 autori e 931 commit. Endpoint MCP sperimentale in 0.89.0; tag "rest-api-v1.0.0" l'11 ottobre 2026. — [releases](https://github.com/portfolio-performance/portfolio/releases), tag git
- **Rotki**: 4.134 commit nel 2026, il secondo valore dopo Wealthfolio; 8 release; nuovo pricing a livelli da novembre 2025. — [repo](https://github.com/rotki/rotki), [blog rotki](https://blog.rotki.com/2025/10/13/rotki-tiers/)
- **Sossoldi** (team italiano, Flutter): versione 1.0.0 il 2026-08-20. — tag git del [repo](https://github.com/RIP-Comm/sossoldi)
- **Nuovi progetti 2025–2026 nei topic** portfolio-tracker, net-worth e wealth-management (tutti con push a ottobre o novembre 2026):
  - aurelio-finance (349 stelle), "AI financial advisor".
  - Aurum (271).
  - open-net-worth (250), "Self-hosted alternative to Claude and ChatGPT Personal Finance".
  - finlynq (30), con server MCP proprietario.
  - track3 (87), desktop e iOS local-first.
  - Molti progetti cinesi local-first con AI (licai, financial-management 376).
  - Fonte: API di ricerca GitHub, topic [portfolio-tracker](https://github.com/topics/portfolio-tracker), [net-worth](https://github.com/topics/net-worth), [wealth-management](https://github.com/topics/wealth-management), 2026-11-09.
- Il topic "self-hosted + portfolio-management" è dominato da OpenByteInc/QuantDinger (13.645 stelle), un "Agentic Trading OS". Appartiene alla categoria trading e non al tracking del patrimonio. — [repo](https://github.com/OpenByteInc/QuantDinger)

### Inferences
- Il ritmo di Wealthfolio nel 2026 (circa 4,6k commit e oltre 30 release) e la sua copertura funzionale ne fanno il benchmark diretto di MyFinancePlace. L'arrivo della lingua italiana suggerisce che potrebbe intercettare la stessa utenza italiana prima che MyFinancePlace arrivi sul mercato.
- L'MCP e l'"AI che importa i CSV" stanno diventando funzioni base. L'AI locale di MyFinancePlace è un elemento di parità con la concorrenza più che un elemento distintivo.

### Gaps
- Non ho una serie storica delle stelle (star-history.com e ossinsight.io non raggiungibili; endpoint stargazers bloccato). La crescita è stimata solo da età del repo e stelle attuali.
- Non ho numeri di download o installazioni (App Store, Docker pulls).
