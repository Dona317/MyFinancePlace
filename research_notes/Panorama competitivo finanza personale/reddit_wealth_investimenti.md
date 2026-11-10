# Reddit e community: strumenti per patrimonio netto e portafoglio (2025–2026)

> **LIMITE DI ACCESSO, da leggere prima di tutto.** Da questa sessione Reddit non era raggiungibile per nessuna via:
> - `curl` verso www.reddit.com e old.reddit.com, anche in formato `.json`: tunnel 403 rifiutato dal proxy;
> - WebFetch: "unable to fetch from www.reddit.com";
> - WebSearch con `allowed_domains: reddit.com`: "domains are not accessible to our user agent".
>
> Erano bloccati dalla rete della sessione anche i mirror e i siti alternativi: reddit.sentinel-team.org, gummysearch.com, piefed/Lemmy, news.ycombinator.com e bogleheads.org.
>
> **Non c'è quindi NESSUNA citazione verbatim da Reddit con permalink verificato.** Le note usano solo gli estratti dei risultati di ricerca da community vicine: Hacker News, il forum Bogleheads.org (equivalente diretto di r/Bogleheads), Lemmy, GitHub e qualche rassegna. Le citazioni tra virgolette sono frammenti di snippet di ricerca, non letti in pagina. Date e punteggi non sono quasi mai visibili e sono segnalati come "n.d.". Per avere citazioni Reddit vere bisogna abilitare reddit.com nella rete della sessione oppure raccoglierle a mano.

## 1. Strumenti consigliati per patrimonio netto e portafoglio

### Takeaway
Dalle fonti raggiungibili emerge una divisione dei ruoli:
- **Empower** (gratis, aggregazione) e **Kubera** (circa 150 $/anno, asset eterogenei) per il patrimonio netto negli USA;
- **ProjectionLab** e Boldin per la pianificazione;
- **Portfolio Performance** (desktop, open source, standard di fatto in Germania), **Parqet** e **Getquin** per il portafoglio in Europa;
- **Ghostfolio** e **Wealthfolio** nel filone open source / self-hosted / local-first.

Il foglio di calcolo resta il riferimento per gli utenti più esigenti.

### Cited Findings
- Forum Bogleheads: Kubera è descritto come "basically like keeping an Excel sheet, but the accounts are automatically connected", con "better connectivity and the UI is also very customizable" rispetto a Personal Capital. Data n.d. — [Bogleheads: anyone using Kubera](https://www.bogleheads.org/forum/viewtopic.php?t=422420)
- Bogleheads: Empower "is decent for aggregation and basic allocation visibility, but it doesn't really help with decision-making". Data n.d. — [Bogleheads: Frustrated with PersonalCapital](https://www.bogleheads.org/forum/viewtopic.php?t=406745)
- Bogleheads: ProjectionLab "doesn't connect to accounts" e serve un account a pagamento per salvare i dati. È citato per il Monte Carlo con rendimenti storici USA — [Bogleheads: Experience with ProjectionLab](https://www.bogleheads.org/forum/viewtopic.php?t=375804)
- Bogleheads, sintesi dei thread: "Kubera or Quicken fill the tracking role and ProjectionLab or Boldin fill the planning role". Sono citati anche Maxifi, Monarch e Quicken Classic per chi vuole un desktop. **Sintesi del motore di ricerca, non citazione** — [Bogleheads: What Retirement Planning/Budgeting Software](https://www.bogleheads.org/forum/viewtopic.php?t=411655&start=50); [Bogleheads: Who is using a personal finance app?](https://www.bogleheads.org/forum/viewtopic.php?t=413828)
- Europa:
  - Portfolio Performance è "free open source" e "very reliable" (commenti Reddit riportati da una rassegna);
  - Getquin "automatically imports your portfolio and tracks your dividends";
  - Parqet conta "more than 100,000 investors in Germany" (dato del produttore) e ha codice chiuso.

  Fonti: [GummySearch: Portfolio Trackers reviews from Reddit](https://gummysearch.com/tools/best-products/portfolio-trackers/) (pagina vista solo come snippet, il fetch è bloccato); [Parqet vs Portfolio Performance (blog Parqet)](https://parqet.com/en/blog/parqet-vs-portfolio-performance)
- Thread r/eupersonalfinance "What app are you using to track your net worth" (luglio 2024, fuori finestra), visibile solo il titolo tramite mirror — [mirror lr.eu.psf.lt](https://lr.eu.psf.lt/r/eupersonalfinance/comments/1e4n2uo/what_app_are_you_using_to_track_your_net_worth)
- Wealthfolio 2.0 (Show HN, fine 2025, circa 8 mesi prima di luglio 2026): app mobile iOS, desktop macOS/Windows/Linux e immagine Docker self-hosted, con sistema di estensioni — [HN: Wealthfolio 2.0](https://news.ycombinator.com/item?id=46006016)
- Altri tracker local-first comparsi su HN nel 2025: privatefolio (AGPLv3, SQLite, desktop interamente locale), 8020money (file JSON locale), WealthYogi ("Offline-first & private"), tracker self-hosted di patrimonio e portafoglio — [HN: privatefolio](https://news.ycombinator.com/item?id=44354093); [HN: self-hosted net worth and portfolio manager](https://news.ycombinator.com/item?id=45641598); [HN: WealthYogi](https://news.ycombinator.com/item?id=46186836); [HN: simple private free net worth tracker](https://news.ycombinator.com/item?id=39981006)

### Inferences
- Nessuno strumento copre insieme budget, patrimonio, portafoglio europeo e pianificazione: gli utenti ne combinano 2 o 3, ad esempio tracker + planner + foglio di calcolo.
- Gli strumenti più usati negli USA (Empower, Kubera, Monarch) dipendono dall'aggregazione bancaria USA. In Italia/UE quel vantaggio sparisce, e strumenti manuali come Portfolio Performance e Wealthfolio diventano lo standard.

### Gaps
- Nessun dato Reddit verificabile su Snowball Analytics, Sharesight, Delta, Tiller e GOOGLEFINANCE, né sugli investimenti in Monarch nel 2025–26: tutte le fonti utili erano bloccate.
- Manca il sentiment di r/ETFs_Europe, r/dividends, r/Ghostfolio e r/wealthfolio.

## 2. Punti dolenti: import da broker/CSV, multivaluta, dividendi, rendimenti, immobili, privacy, prezzi, chiusure, chiamate di Empower

### Takeaway
I temi ricorrenti sono:
- l'import dai broker (il CSV manuale è visto come lavoro quotidiano);
- le operazioni societarie (split, fusioni, dividendi);
- il calcolo corretto dei rendimenti;
- i dashboard rigidi e non esportabili (Kubera);
- le chiamate commerciali di Empower sopra i 100.000 $;
- la fragilità del modello di business (Maybe), che a sua volta spinge verso open source e local-first.

### Cited Findings
- **Import da broker.** HN, thread Wealthfolio 2.0: la mancanza di collegamenti con broker e aggregatori "would be a deal-breaker" per una diffusione ampia, perché CSV e inserimento manuale costano lavoro quotidiano. Un utente chiede "a mapping profile for each major broker", un altro prova LLM locali per leggere gli estratti conto. **Parafrasi da snippet** — [HN comment 46006920](https://news.ycombinator.com/item?id=46006920)
- Wealthfolio ha poi introdotto ricette di import per broker (IBKR, Schwab, Fidelity e altri). La sincronizzazione automatica con i broker è nell'abbonamento opzionale "Wealthfolio Connect"; inserimento manuale e CSV restano gratuiti — [Wealthfolio GitHub](https://github.com/wealthfolio/wealthfolio); [Wealthfolio changelog](https://wealthfolio.app/changelog/)
- **Multivaluta.** Bug documentato nel changelog di Wealthfolio: un CSV senza colonna valuta salvava acquisti, vendite e dividendi "with an empty currency", e questo "later broke exchange-rate conversion" — [Wealthfolio changelog](https://wealthfolio.app/changelog/)
- **Operazioni societarie e rendimenti.** HN (2023, fuori finestra ma pertinente): "Does it handle stock splits, consolidations, dividends etc? Calculating returns … is a non-trivial problem". Un utente di Ghostfolio dice di aver gestito gli split a mano ("multiply and divide all actions") e che non lo rifarebbe — [HN 37340114](https://news.ycombinator.com/item?id=37340114); [HN 37341662](https://news.ycombinator.com/item?id=37341662)
- **Usabilità di Portfolio Performance.** HN: "easier to set up though, it's a plain old Java desktop application", ma anche "non-intuitive and very hard to use" e "UX is not the best". Thread del 2023 — [HN 37340091](https://news.ycombinator.com/item?id=37340091); [HN 37337482](https://news.ycombinator.com/item?id=37337482)
- **Monarch e azioni.** Su HN si nota che Monarch gestisce male le azioni: "no good way to view historic portfolio value / net worth". Parafrasi dalla sintesi di ricerca — [HN: Wealthfolio 2.0](https://news.ycombinator.com/item?id=46006016)
- **Privacy / "local".** Commenti HN: Wealthfolio si collega a wealthfolio.app e yahoo.com (per le quotazioni), quindi non è del tutto offline. Le promesse "local" vanno verificate — [HN: Wealthfolio 2.0](https://news.ycombinator.com/item?id=46006016)
- **Modello di business.** HN, Show HN Wealthfolio 2024: proteste contro le ipotesi di vendere dati anonimizzati e mostrare pubblicità ("crypto scam ad while viewing your portfolio") — [HN 41465735](https://news.ycombinator.com/item?id=41465735)
- **Rigidità di Kubera.** Bogleheads: "not bad for a starting point, but the dashboard is rigid / I can't model anything / no way to export to a spreadsheet" — [Bogleheads: Why is wealth software still so bad?](https://www.bogleheads.org/forum/viewtopic.php?p=8765791)
- **Sincronizzazione Empower.** Bogleheads: "problems with synching and repeated re-authentication" — [Bogleheads 406745](https://www.bogleheads.org/forum/viewtopic.php?t=406745)
- **Chiamate di Empower.** Utente Reddit citato in una recensione: "if you have more than $100k, be prepared for the 'free' consultation calls". Le chiamate calano dopo qualche rifiuto. **Fonte secondaria, nessun permalink Reddit** — [Mezzi: Empower free dashboard vs advisor pitch](https://www.mezzi.com/blog/empower-free-dashboard-vs-advisor-pitch-reading-real-product); [Financial Samurai: Empower free financial review](https://www.financialsamurai.com/empower-free-financial-review/)
- **Chiusura di Maybe.** Luglio 2025: Maybe passa al B2B ("We're now a B2B software company"). App consumer e prodotti collegati chiudono entro 6–8 settimane, v0.6.0 è l'ultima release e il repository viene archiviato. Il fork comunitario **Sure** (we-promise/sure, AGPLv3) è considerato il più attivo. Discussione cross-postata su Lemmy, titolo "Maybe drops open-source support - pivots to B2B data and scenario planning" — [Lemmy/piefed](https://piefed.jeena.net/post/210475); [GitHub vinteo/sure (fork)](https://github.com/vinteo/sure); [AlternativeTo: Maybe](https://alternativeto.net/software/maybe/about)
- **Prezzi.** Kubera circa 150 $/anno; Monarch 14,99 $/mese o 99,99 $/anno (dati da recensioni di terzi) — [Bogleheads Kubera](https://www.bogleheads.org/forum/viewtopic.php?t=422420); [guardfolio: Empower alternatives](https://guardfolio.pages.dev/empower-alternatives)

### Inferences
- Per MyFinancePlace, che non sincronizza con le banche, l'import CSV è il cuore del prodotto: profili per i broker italiani/UE (Fineco, Directa, Degiro, Scalable, Trade Republic, IBKR, Moneyfarm, BancoPosta) risolverebbero il punto dolente più citato.
- Valuta obbligatoria per riga, gestione corretta di split e dividendi e un TWR/IRR affidabile sono condizioni minime: sono esattamente gli errori che gli utenti notano.
- La chiusura di Maybe è un argomento di vendita per un'app locale con dati in un formato aperto ed esportabile, senza rischio che il servizio venga spento.

### Gaps
- Nessuna citazione Reddit 2025–26 su TWR e IRR, sulla gestione di immobili e beni illiquidi, sulla tassazione dei dividendi in UE o sui prezzi di Getquin/Parqet: le fonti non erano accessibili.
- Engagement (upvote, numero di commenti) non disponibile per nessun thread.

## 3. Esigenze del pubblico FIRE: proiezioni, Monte Carlo, piano di prelievo

### Takeaway
Gli utenti FIRE e Bogleheads separano il tracciamento dalla pianificazione. Usano ProjectionLab, Boldin, Maxifi e Pralana per Monte Carlo, conversioni Roth e prelievi, ma lamentano che servono comunque setup manuale e fogli di calcolo personalizzati. Molti costruiscono da sé il proprio strumento.

### Cited Findings
- ProjectionLab: a pagamento, con Monte Carlo su rendimenti storici USA e senza collegamento ai conti — [Bogleheads: Experience with ProjectionLab](https://www.bogleheads.org/forum/viewtopic.php?t=375804)
- Pralana Gold è citato come strumento di modellazione specialistico, ad esempio per le conversioni Roth; Tablewealth "seems to somehow enable everything I need" — [Bogleheads: Why is wealth software still so bad?](https://www.bogleheads.org/forum/viewtopic.php?p=8765791)
- "many of them would have highly specific requirements … would still require a lot of manual setup". Un utente ha creato uno strumento proprio per la famiglia, che "isn't really sharable" — [Bogleheads 8765791](https://www.bogleheads.org/forum/viewtopic.php?p=8765791)
- Altri thread di pianificazione: preferenze sui calcolatori per la pensione e software per coppie — [Bogleheads 403975](https://www.bogleheads.org/forum/viewtopic.php?t=403975); [Bogleheads 438962](https://www.bogleheads.org/forum/viewtopic.php?t=438962); [Bogleheads 8834993](https://www.bogleheads.org/forum/viewtopic.php?p=8834993)
- Wealthfolio include oggi "simulations" e, secondo un sito di confronto, Monte Carlo, metriche di rischio e attribuzione della performance. **Fonti secondarie** — [Wealthfolio GitHub](https://github.com/wealthfolio/wealthfolio); [OpenAlternative: Ghostfolio vs Wealthfolio](https://openalternative.co/compare/ghostfolio/vs/wealthfolio)

### Inferences
- Gli strumenti FIRE sono pensati per gli USA (Roth, 401k, Social Security). Per l'Italia mancano modelli con TFR, fondi pensione e deducibilità, INPS, tassazione al 26% / 12,5% sui titoli di Stato, imposta di bollo e IVAFE. MyFinancePlace può occupare questo spazio vuoto.

### Gaps
- Mancano citazioni dirette da r/financialindependence, r/Fire, r/fatFIRE e r/ExpatFIRE, compresa l'esigenza multivaluta degli expat: Reddit non era accessibile.

## 4. Cosa vorrebbero gli utenti in un'unica app (budget + patrimonio + investimenti)

### Takeaway
I desideri ricorrenti sono:
- un'unica vista di tutto;
- import da broker senza fatica;
- dashboard modellabili ed esportabili;
- supporto per asset complessi (azioni aziendali/RSU, private market, immobili);
- privacy e dati locali senza essere offline "a metà";
- un prezzo sostenibile o nullo.

Il mercato fatica a monetizzare: la disponibilità a pagare è bassa.

### Cited Findings
- Il post iniziale del thread Bogleheads lamenta che la categoria è "so underbuilt" visto quante persone hanno "complex compensation structures, startup equity, private market exposure, RSUs, carry". Si chiede se le famiglie sofisticate usino ancora "custom spreadsheets and advisors" — [Bogleheads 8762990](https://www.bogleheads.org/forum/viewtopic.php?p=8762990)
- Spiegazione economica: "generally people are not willing to pay for software", e non c'è "money in having a big development team making 'really good' wealth software" — [Bogleheads 8765791](https://www.bogleheads.org/forum/viewtopic.php?p=8765791)
- Su HN la categoria è vista come un problema "low frequency, low pain" per i non professionisti — [HN 37337482](https://news.ycombinator.com/item?id=37337482)
- Richieste esplicite: profili di import per broker, parsing degli estratti conto con LLM locali, export verso fogli di calcolo, possibilità di "model anything" — [HN 46006920](https://news.ycombinator.com/item?id=46006920); [Bogleheads 8765791](https://www.bogleheads.org/forum/viewtopic.php?p=8765791)
- Una guida Reddit-oriented suggerisce agli appassionati FIRE i template dei fogli di calcolo della community. Fonte SEO di bassa qualità — [joingerald](https://joingerald.com/learn/financial-wellness/net-worth-tracker-tools-2026)

### Inferences
- Il posizionamento di MyFinancePlace (locale, italiano, budget + patrimonio + portafoglio + mutui con ammortamento + previsioni) risponde a più desideri citati insieme. I rischi principali sono la fatica dell'import manuale e la scarsa disponibilità a pagare, che spinge verso licenza una tantum o freemium.

### Gaps
- Non è stato possibile verificare le migrazioni concrete raccontate su Reddit (Mint → Monarch/Empower, Maybe → Sure/Wealthfolio/Actual, Personal Capital → Kubera), con date e permalink. Va rifatto con accesso a reddit.com.
- Le pagine SEO dei risultati (fured.hotspotsystem.com, hub.bocatc.org, mindcrate.vercel.app, impressivemagazine.com ecc.) sono state scartate perché inaffidabili.
