# Panorama app di finanza personale in Italia ed Europa (novembre 2026)

> Avvertenza sul metodo (9 nov 2026): **reddit.com non era raggiungibile** da questa sessione (la ricerca web rifiuta il dominio; anche curl verso reddit.com e pullpush.io è stato bloccato dal proxy, 403). Non ci sono quindi citazioni testuali da r/ItaliaPersonalFinance. Anche il recupero di pagine da partitaiva.it, finary.com, dailytool.substack.com e github.com (HTML) non è riuscito per via delle restrizioni di rete. Quello che segue viene da snippet dei motori di ricerca, dalla GitHub search API (gh) e da articoli italiani ed europei. Nessuna citazione è inventata. Dove una cifra arriva solo da uno snippet, lo segnalo.

## 1. Cosa usano e consigliano gli utenti italiani (Reddit, forum, blog)

### Takeaway
Non è stato possibile verificare direttamente cosa si dica su Reddit. Dalle fonti italiane accessibili emerge questo: il "default" culturale è il foglio Excel/Google Sheets (il modello di Mr. RIP); Sossoldi, l'app open source della community di Mr. RIP, è nata proprio per sostituirlo; per gli investimenti si usano Portfolio Performance (gratuito) e tracker tedeschi (Getquin, Parqet); per le spese quotidiane si usano app generiche (Monefy, Wallet, Spendee, Money Manager).

### Cited Findings
- Sossoldi nasce perché "Mr. Rip is a blogger that has a spreadsheet in which he tracks his net worth"; l'app "aims at replacing that spreadsheet", ed è pensata per chi ha poche conoscenze di finanza personale (riportato dagli snippet di F-Droid e GitHub) — [F-Droid Sossoldi](https://f-droid.org/en/packages/com.ripster.sossoldi/); [awesome.ecosyste.ms](https://awesome.ecosyste.ms/projects/github.com%2FRIP-Comm%2Fsossoldi)
- Le guide italiane 2026 ai "migliori software" citano soprattutto app generiche e globali. Money.it (aggiornata a gennaio 2026) mette Money Manager Expense & Budget e Monefy tra le principali. Aranzulla cita Spendee (iPhone) ed Expense Manager (Android). Finanza Digitale ne elenca 15, comprese app bancarie come Tinaba (Banca Profilo) — [Money.it](https://www.money.it/le-15-migliori-app-per-la-gestione-delle-spese); [Aranzulla](https://www.aranzulla.it/app-per-gestione-spese-1176476.html); [Finanza Digitale](https://www.finanzadigitale.com/guide/app-gestione-bilancio/)
- Un articolo Substack italiano sulle app "che ogni giovane dovrebbe avere" cita Monefy e Wallet per le spese quotidiane — [Dimitri Colombo, Substack](https://dimitricolombo.substack.com/p/dalle-spese-giornaliere-agli-investimenti)
- IoInvesto (luglio 2026) propone a lettori italiani strumenti stranieri a pagamento (Tiller, Quicken, PocketGuard, YNAB, circa 79-109 $/anno): un segnale della mancanza di alternative italiane — [IoInvesto](https://www.ioinvesto.net/blog/analisi-finanze-personali/)
- Continuano a nascere piccole app italiane indipendenti, spesso "local-first". Cointrol (App Store IT) dichiara che "i dati restano sul dispositivo". Spenzo (0,99 €) offre import CSV/Excel e regole di categorizzazione. PickPocket Budget è stata presentata su forum.fibra.click per raccogliere feedback — [Cointrol](https://apps.apple.com/it/app/cointrol/id6745321377); [Spenzo](https://apps.apple.com/it/app/spenzo/id6760916937); [forum.fibra.click](https://forum.fibra.click/d/75201-ho-sviluppato-una-piccola-app-per-gestire-le-spese-feedback)
- Satispay viene descritta come un ecosistema che va "oltre i pagamenti", con gestione delle spese personali. Oval offre categorizzazione con suggerimenti AI — [Money.it su Satispay](https://www.money.it/come-funziona-satispay-e-a-cosa-serve); [Mamma Felice](https://risparmiare.mammafelice.it/app-per-risparmiare-satispay-vs-oval)
- Su GitHub compaiono molti progetti personali italiani "finanze personali", creati nell'ott-nov 2026 (es. Loreexe/Spendy "nel proprio server", michi5dev/portafoglio, Prosdino95/leroy): forte domanda fai-da-te e self-hosted, ma nessun progetto con trazione — GitHub search API, `q="finanze personali"`, 9 nov 2026

### Inferences
- Il concorrente principale di MyFinancePlace in Italia non è un'app ma **il foglio Excel**, seguito da Sossoldi (che ha lo stesso pubblico: la community di Mr. RIP). L'import da Excel e l'esportazione verso Excel sono quindi requisiti di adozione.
- Le app generiche (Monefy, Wallet, Spendee) non capiscono gli estratti conto delle banche italiane né il fisco italiano. Le guide italiane non segnalano nessuna app "made for Italy" che copra spese, patrimonio e fisco insieme.

### Gaps
- Nessuna citazione verbatim da r/ItaliaPersonalFinance, r/italy o r/ItaliaCareerAdvice (dominio bloccato). Per completare servono ricerche manuali su "app per gestire le spese", "Portfolio Performance", "Moneyviz", "foglio Excel" nel sub.
- Non sono riuscito ad accedere al Finanza Online forum, a Mr. RIP né ad Affari Miei.

## 2. App italiane ed europee: funzionalità, prezzi, fisco italiano

### Takeaway
Il mercato europeo è diviso in tre gruppi: **budget/spese** (Wallet, Spendee, Money Lover, Fintonic, Finanzguru), **patrimonio e portafoglio** (Finary, Getquin, Parqet, Portfolio Performance) e **fisco italiano per broker esteri** (Moneyviz e simili, a pagamento per conto/anno). Nessuno copre bene insieme budget, patrimonio e fisco italiano. I tracker tedeschi hanno aumentato i prezzi nel 2025.

### Cited Findings
- **Moneyviz** (Italia): piattaforma web che gestisce investimenti su più piattaforme "semplificando le dichiarazioni fiscali", con un pannello aggregato del patrimonio e un confronto con i benchmark. Importa in automatico da eToro, Trading 212, Degiro e Interactive Brokers, oltre ad alcune fonti crypto (Young Platform, MetaMask, Ledger). La registrazione gratuita include l'"anteprima delle tasse dovute". I prezzi variano a seconda della fonte: per una sono "da 39 € / 129 € / 249 € per conto per anno fiscale"; un'altra cita piani a transazioni da 49/169/269 € (promo scaduta il 31/07/24) — snippet di [PartitaIVA.it](https://www.partitaiva.it/moneyviz/) e [RisparmiOggi](https://www.risparmioggi.it/?p=10688) (pagine non aperte direttamente: prezzi da verificare)
- **Parqet** (DE): il piano gratuito esiste, ma l'export CSV richiede Plus o Investor. Getquin e Parqet hanno alzato i prezzi "quasi contemporaneamente"; per Parqet l'aumento vale dal 1° agosto 2025 — [broker-test.at](https://www.broker-test.at/news/portfolio-verwaltung-getquin-parqet-erhoehen-fast-gleichzeitig-die-preise/); [broker-test.at, Parqet ago 2025](https://www.broker-test.at/news/parqet-erhoeht-preise-ab-1-august-2025-jetzt-noch-schnell-bestandsabo-holen/)
- **Getquin** (DE): base gratuita; nel 2023 il premium era passato da 4,99 a 9,99 €/mese (dato vecchio). Nel forum Getquin un utente lamenta che non si possano ancora tracciare i fondi comuni — [broker-test.at](https://www.broker-test.at/tag/getquin/); [Getquin community](https://app.getquin.com/it/post/oTaqxJpogk/comment/1012012)
- **Finary** (FR): Finary Plus costa 99,99 o 149,99 €/anno a seconda dello store o del periodo. Sul forum ufficiale c'è una discussione intitolata "Finary trop cher?" — [App Store ES](https://apps.apple.com/es/app/id1569413444); [Finary community](https://community.finary.com/t/finary-trop-cher/29930/64)
- **MyFinanceTools** (concorrente, fonte di parte) si promuove in italiano come alternativa a Parqet ("Portafogli illimitati, gratis") e a Getquin ("Mai un login al broker"), con prezzi Getquin controllati ad agosto 2026 — [MyFinanceTools vs Parqet](https://myfinancetools.io/it/alternativa-a-parqet/); [vs Getquin](https://myfinancetools.io/it/alternativa-a-getquin/)
- **Portfolio Performance**: gratuito e open source (Java, Win/Mac/Linux). L'app iOS companion non permette di modificare titoli e transazioni — [AlternativeTo](https://alternativeto.net/software/portfolio-performance/about); [App Store](https://apps.apple.com/DE/app/id6451118191)
- **Broker esteri e regime fiscale**: Trade Republic ha lanciato la succursale italiana con IBAN italiano e regime amministrato, "prima challenger bank a offrirlo in Italia" (comunicato del 30 gen 2025). Secondo una tabella di confronto, gli interessi sulla liquidità restano però in regime dichiarativo. Per Scalable Capital le fonti si contraddicono: RisparmiOggi parla di regime amministrato opzionale dal 1° settembre 2026, altre fonti dicono ancora "atteso entro fine 2026" — [comunicato Trade Republic](https://assets.traderepublic.com/assets/files/250130_TradeRepublic_PressRelease_BranchLaunch-Italy_IT_IT.pdf); [promarketer.it](https://www.promarketer.it/?p=10872); [RisparmiOggi](https://www.risparmioggi.it/scalable-capital-sostituto-dimposta-cosa-cambiera/); in contrasto con [webeconomia](https://www.webeconomia.it/scalable-capital-vs-trade-republic/)
- In regime dichiarativo l'IVAFE (0,20%/anno) è a carico dell'investitore — [promarketer.it](https://www.promarketer.it/?p=10872)

### Inferences
- Più broker "neo" passano al regime amministrato (Trade Republic, forse Scalable), quindi il mercato del calcolo RW/RT per questi broker si restringe. Restano però IBKR, Degiro, eToro, Trading 212, crypto e la liquidità/interessi presso broker esteri. Uno strumento per il Quadro RW e l'IVAFE resta utile, ma come funzione, non come prodotto a sé.
- Il prezzo di Moneyviz (per conto, per anno fiscale) mostra che gli utenti italiani pagano per la parte fiscale. Un'app desktop locale con calcolo RW/IVAFE incluso, o venduto una tantum, avrebbe un vantaggio di prezzo.

### Gaps
- Non ho prezzi primari 2026 per Wallet (BudgetBakers), Spendee, Money Lover, Fintonic, Finanzguru, Moneyfarm. Non so se Fintonic sia ancora attiva in Italia (nessun risultato).
- Non ho verificato le funzioni di analisi spese di Fineco, Intesa XME, Revolut e Hype.
- Non ho trovato nessuna funzione del 730 o di detrazioni nelle app europee.

## 3. Bisogni italiani non coperti e progetti open source italiani

### Takeaway
L'open source italiano è frammentato: tanti piccoli strumenti a script singolo per RW/RT/IVAFE, minusvalenze, BFP e 730, quasi tutti con 0-25 stelle, più l'unico progetto con una community vera, Sossoldi (circa 1,4k stelle). Proliferano dal 2026 gli strumenti per agenti AI (MCP server e Claude Skill) sul fisco italiano. I bisogni chiave (RW/IVAFE, minusvalenze in dichiarativo, BFP, BTP) sono coperti solo da tool isolati, senza un'app che li integri con budget e patrimonio.

### Cited Findings (GitHub search API, dati del 9 nov 2026)
- **RIP-Comm/sossoldi**: ★1416, ultimo push 6 nov 2026. Descrizione: "wealth management / personal finance / Net Worth tracking app, made with Flutter". Licenza MIT, dati locali, il README prevede investimenti, tasse e collegamento PSD2. F-Droid annuncia la versione 1.0, mentre un mirror riporta ancora la 0.3.2 — `gh api search/repositories q=sossoldi`; [F-Droid](https://f-droid.org/ja/packages/com.ripster.sossoldi/); [izzysoft](https://apt.izzysoft.de/fdroid/index/apk/com.ripster.sossoldi?repo=main)
- **vjt/decaf**: ★14, push 28 mag 2026. Descrizione: "Genera il tuo Modello Redditi PF dai broker esteri. Niente commercialista." — GitHub search `ivafe`
- **salvomag-hub/tasse-ibkr**: ★1, feb 2026. "Calcolo tasse italiane per conti Interactive Brokers — LIFO/FIFO, IVAFE analitica, forex automatico" — GitHub search `ivafe`
- **morenofx/mt5-fiscal-suite**: ★0, 4 nov 2026. "Quadro RT-RW e proventi Market, cambi BCE, tutto client-side"; anche mastrogiovanni/quadro-rw-rt (★0, 2024) — GitHub search `quadro RW`
- **gabrielerandelli/minus-tracker**: ★0, ott 2026. "Italian capital-gains/loss calculator (LIFO/FIFO) with CLI and MCP server for AI agents — Regime Dichiarativo" — GitHub search `regime dichiarativo`
- **gsaccardi/dichiarino-mcp**: ★25, set 2026. Server MCP che fa da assistente per compilare la dichiarazione italiana (730) — GitHub search `730 precompilato`
- **eliazv/italian-investor**: ★1, set 2026. "Claude Skill per l'analisi di portafoglio tax-aware degli investitori italiani: fiscalità ETF, BTP, …" — GitHub search `minusvalenze`
- **Buoni Fruttiferi Postali**: nemorfol/bfp (simulatore, ★1) e teo2810/Bfpo ("App gestione e visualizzazione buoni fruttiferi postali ordinari", ★0, set 2026) — GitHub search
- **AlvioInsights/BTC-IT-Tax-Calculator**: app Python locale per le tasse BTC italiane (★0, apr 2026) — GitHub search `quadro RW`
- **Parser per estratti conto Fineco/Intesa**: nessun repository trovato con le query "fineco estratto conto" e "intesa sanpaolo estratto conto parser". Per Degiro esistono solo tracker di performance non fiscali (es. datruccone/PortfolioEvolution ★18, 2020) — GitHub search

### Inferences
- **Buco evidente:** nessun progetto (open o commerciale) offre import degli estratti conto delle banche italiane, budget, patrimonio, BTP/BFP e calcolo RW/IVAFE/minusvalenze in un'unica app locale. È il posizionamento naturale di MyFinancePlace.
- Il proliferare di MCP server e skill fiscali italiani nel 2026 (dichiarino-mcp, minus-tracker, italian-investor) indica che l'"assistente AI sul fisco personale" è una tendenza attuale. La categorizzazione con AI locale di MyFinancePlace è in linea; un'estensione verso le domande fiscali è plausibile.
- I bisogni elencati nell'incarico (TFR/fondo pensione, mutuo, spese mediche per il 730, ritenuta 26% sui conti deposito) non hanno trovato strumenti dedicati. Sono probabilmente non coperti, ma non è verificato.

### Gaps
- Non ho trovato strumenti open source per Directa (la query "directa" restituisce solo DirectAdmin), per TFR/fondi pensione o per le spese mediche.
- Non ho potuto leggere i README di decaf ecc. (github.com HTML non raggiungibile): funzioni dichiarate solo dalle descrizioni.

## 4. Contesto regolatorio: PSD2/PSD3, FiDA, aggregatori

### Takeaway
L'accesso gratuito ai dati bancari via aggregatori si è chiuso: GoCardless Bank Account Data (ex Nordigen) non accetta nuovi iscritti da luglio 2025; Enable Banking, Tink e Salt Edge chiedono preventivi. FiDA (open finance) è di fatto in uscita: il 4 nov 2026 la bozza del programma di lavoro 2027 della Commissione ne prevede il ritiro. PSD3/PSR: accordo politico del 27 nov 2025, con un cruscotto obbligatorio dei permessi. Tutto questo rafforza la scelta di MyFinancePlace di importare file invece di sincronizzare.

### Cited Findings
- GoCardless: "from July 2025 onwards, GoCardless has stopped accepting new Bank Account Data accounts"; gli account esistenti continuano a funzionare. Firefly III scrive che GoCardless sta dismettendo il servizio gratuito e che "registration is unfortunately closed" — [Actual Budget docs](https://actualbudget.org/docs/advanced/bank-sync/gocardless/); [Firefly III docs](https://docs.firefly-iii.org/how-to/data-importer/import/gocardless/); [DEV Community (fonte di parte)](https://dev.to/johnfrandsen/gocardless-bank-account-data-alternatives-what-to-use-when-signups-are-disabled-326d)
- Enable Banking: nessun listino pubblico. Da aprile 2026 i prezzi si ottengono con un modulo "Get a Quote" in base a volumi e paesi; i changelog di marzo e aprile 2026 citano un accesso più ampio ai conti carta in Italia — [Enable Banking changelog marzo 2026](https://enablebanking.com/blog/2026/04/08/enable-banking-changelogmarch-2026); [aprile 2026](https://enablebanking.com/blog/2026/05/14/enable-banking-changelog-april-2026)
- Tink (Visa): prezzi enterprise su richiesta ("contact vendor"). Salt Edge: in Italia ha partnership con Supernovae Labs ed EasyPol (2021), prezzi su richiesta — [Capterra Tink](https://www.capterra.com/p/196515/Tink/); [DEV, open banking APIs 2026](https://dev.to/johnfrandsen/the-cheapest-open-banking-apis-for-small-businesses-and-indie-builders-in-2026-5cab); [Open Banking Expo](https://www.openbankingexpo.com/news/salt-edge-joins-forces-with-italys-supernovae-labs/)
- FiDA: MLex riporta che la Commissione intende ritirare la proposta "within six months", secondo la bozza del programma di lavoro 2027; Cash-Online data l'annuncio al 4 nov 2026. Nella bozza si parla di "significant burden and complexity for financial actors". Già nel febbraio 2025 una fuga di notizie aveva annunciato il ritiro, poi smentito. Non risulta un atto formale di ritiro — [MLex](https://www.mlex.com/mlex/articles/2545816); [Cash-Online](https://www.cash-online.de/a/eu-kommission-zieht-fida-verordnung-zurueck-folgen-fuer-versicherer-und-banken-729527/); [Vixio 2025](https://www.vixio.com/insights/pc-fida-lives-see-another-day-european-commission-backs-away)
- PSD3/PSR: accordo provvisorio tra Consiglio e Parlamento il 27 nov 2025. Ci sarà un cruscotto per gestire i permessi dati concessi a terzi e un elenco di ostacoli vietati alle banche. Secondo The Paypers l'ECON ha approvato i testi il 5 mag 2026; la pubblicazione in Gazzetta Ufficiale non è confermata — [Hogan Lovells](https://hlc.com/en/publications/final-texts-for-psd3-and-psr-awaited-as-european-parliament-and-council-of-eu-announce-provisional); [Mondaq / A&O Shearman](https://webiis08.mondaq.com/unitedstates/financial-services/1713372/european-council-and-parliament-reach-provisional-agreement-on-eu-payments-package); [The Paypers](https://thepaypers.com/regulations/interviews/beyond-compliance-the-strategic-impact-of-psd3-and-psr); [Parlamento europeo](https://www.europarl.europa.eu/legislative-train/theme-an-economy-that-works-for-people/file-payment-services-and-electronic-money-services-(directive))

### Inferences
- Per un'app indipendente senza licenza AISP, la sincronizzazione bancaria è diventata più cara e più difficile dal 2025. Con FiDA in uscita, l'open finance su investimenti, pensioni e assicurazioni non arriverà per legge nel medio periodo. Per broker, fondi pensione e polizze l'import di file (Excel/PDF/OCR) resta l'unica via praticabile: è un argomento a favore del modello di MyFinancePlace.
- Elaborare tutto in locale riduce la superficie GDPR (nessun trattamento lato server). È un messaggio di marketing forte, perché sui dati bancari gli utenti italiani sono diffidenti, come mostrano le app "i dati restano sul dispositivo".

### Gaps
- Stato e copertura di CBI Globe per gli aggregatori non verificati.
- Data di pubblicazione ufficiale di PSD3/PSR e date di applicazione non verificate su fonte primaria.
- Nessuna fonte specifica su GDPR e app di finanza personale in Italia (es. provvedimenti del Garante).
