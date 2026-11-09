# justETF, portafogli multipli, ribilanciamento, registro ordini e dashboard Investimenti (ricerca al 9 nov 2026)

> **Nota di metodo.** Da questa sessione non si raggiungono `www.justetf.com`, `wealthfolio.app` e
> `help.portfolio-performance.info`: WebFetch risponde "host non nel dominio consentito". Tutto ciò che segue
> viene da **estratti dei motori di ricerca** (WebSearch) che puntano alle pagine ufficiali. Il testo integrale
> non è stato letto, quindi i dettagli vanno riverificati aprendo le pagine indicate. Reddit non è stato
> consultato. Le date dei prezzi sono quelle degli estratti e non hanno una data di pubblicazione propria.

## 1. justETF: offerta Free e Premium

### Takeaway
justETF è un sistema di portafoglio **virtuale** basato su transazioni inserite a mano, senza import documentato
dai broker. Il piano Free comprende 1 portafoglio e 1 watchlist. Premium costa da 9,90 €/mese (5 portafogli) a
19,90 €/mese (25 portafogli) con fatturazione annuale. Le funzioni di valore per MyFinancePlace sono tre:
monitoraggio delle **bande di tolleranza** con avviso via e-mail (±5 punti percentuali di default), **lista ordini
di ribilanciamento** da portare al broker e opzione **"solo acquisti"** con calcolo del **versamento minimo** che
riporta l'allocazione al target senza vendere.

### Cited Findings
**Piani e prezzi**
- Free: 1 portafoglio, 1 watchlist, lista degli ordini per il broker, analisi di base — [justETF Versione Free](https://www.justetf.com/it/free.html); [Panoramica offerta](https://www.justetf.com/it/our-offer.html)
- Premium 5: 9,90 €/mese con fatturazione annuale, 14,90 €/mese con fatturazione trimestrale, 5 portafogli. Premium 25: 19,90 €/mese annuale, 24,90 €/mese trimestrale — [justETF Premium (IT)](https://www.justetf.com/it/premium.html); [Panoramica offerta](https://www.justetf.com/it/our-offer.html); conferma da una recensione di terzi: [affarimiei.biz](https://www.affarimiei.biz/justetf/35196)
- I prezzi cambiano da paese a paese: Svizzera da 12,90 CHF/mese annuale (154,80 CHF l'anno) o 18,90 CHF/mese trimestrale; Austria 14,90 €/mese trimestrale; Belgio 9,90 €/mese annuale — [Premium CH](https://www.justetf.com/ch/premium.html); [Premium AT](https://www.justetf.com/en-at/premium.html); [Premium BE](https://www.justetf.com/en-be/premium.html)
- Premium aggiunge simulazione storica dei portafogli con confronto benchmark, monitoraggio e ribilanciamento, esportazione in Excel, diagramma rischio/rendimento sul contributo dei singoli ETF al rischio totale e watchlist illimitate (pagina CH) — [Premium EN-DE](https://www.justetf.com/en-de/premium.html); [Premium CH](https://www.justetf.com/ch/premium.html); [Panoramica offerta IT](https://www.justetf.com/it/our-offer.html)
- Durata minima con rinnovo automatico e disdetta con un mese di preavviso dalle impostazioni (pagine CH/BE). La pagina NL indica invece 5 giorni prima della scadenza — [Premium CH](https://www.justetf.com/ch/premium.html); [Premium NL](https://justetf.com/nl/premium.html)
- Avvisi di prezzo in tempo reale solo nell'app justETF: 10 nel Free e fino a 100 in Premium, secondo le pagine di registrazione — [registrazione IT](https://www.justetf.com/it/registration.html); [registration premium EN](https://www.justetf.com/en/registration-premium.html)
- Dichiarati inoltre: pianificatore di investimenti, costruttore di strategie di portafoglio in ETF, screener completo, modelli di portafoglio da copiare, strategie per i PAC e strategie di terze parti — [registrazione IT](https://www.justetf.com/it/registration.html); [Panoramica offerta](https://www.justetf.com/it/our-offer.html)

**Come justETF modella il portafoglio**
- "Sistema di portafoglio virtuale": tutte le transazioni inserite sono virtuali. Il portafoglio si salva **per transazioni, non per posizioni**, e le transazioni si creano e modificano a mano dalla lista transazioni — [Introduction to transactions](https://www.justetf.com/en/tutorial/transactions/introduction-transactions.html)
- Le pagine justETF trovate non documentano import CSV o da broker. È un'assenza negli estratti, non una prova che la funzione manchi — stessa fonte

**Monitoraggio e avvisi**
- Le bande di tolleranza si impostano per **asset class o per singolo ETF**. Il default è **±5 punti percentuali** alla creazione del portafoglio, modificabile trascinando le barre o con "Set standard range" per tutte le posizioni. Il peso target appare in grigio. Il peso corrente è verde dentro la banda e rosso fuori. Fuori banda arriva un'e-mail e compare un avviso dopo il login — [How does portfolio monitoring work](https://justetf.com/en/tutorial/monitoring/how-does-portfolio-monitoring-work.html); [Come opera il monitoraggio (IT)](https://www.justetf.com/it/tutorial/monitoraggio/come-opera-la-funzione-di-monitoraggio-di-portafoglio.html)
- Orario delle e-mail: nei giorni di borsa alle 9:00 GMT secondo la versione EN, alle 10:00 secondo quella IT (differenza non risolta) — stesse fonti
- Avvisi individuali su **peso**, **valore aggregato** o **quotazione**, notificati il giorno successivo alle 9:00 GMT — [Set individual alerts](https://justetf.com/en/tutorial/monitoring/set-individual-alerts.html)

**Ribilanciamento**
- Calcola gli ordini di acquisto e vendita che riportano all'allocazione target e produce una lista ordini da usare col proprio broker. La funzione si può provare gratis una volta — [Ribilanciare il portafoglio (IT)](https://www.justetf.com/it/tutorial/ribilanciamento/ribilanciare-il-portafoglio.html); [How does portfolio rebalancing work](https://www.justetf.com/en/tutorial/rebalancing/how-does-portfolio-rebalancing-work.html)
- **Versamento con ribilanciamento**: nelle impostazioni si sceglie "Only buy transactions" per ribilanciare senza vendite. Un suggerimento calcola il **versamento minimo** che basta a ribilanciare senza vendere, e un clic lo porta nel calcolo. Con un versamento più piccolo justETF esegue "il miglior ribilanciamento possibile". La stessa pagina gestisce i **prelievi** con ribilanciamento — [Deposit/withdrawal with rebalancing](https://www.justetf.com/de/tutorial/rebalancing/portfolio-deposit-with-rebalancing.html)
- justETF avverte che il ribilanciamento può comportare commissioni e tasse sulle plusvalenze — stessa fonte
- Una recensione di terzi cita "segnali di ribilanciamento anti-ciclico", senza conferma su pagine ufficiali — [affarimiei.biz](https://www.affarimiei.biz/justetf/35196)

**Dati dello screener ETF**
- Filtri per asset class, regione/paese, emittente, domicilio, dimensione del fondo e borse di quotazione. Colonne: dimensione del fondo, TER annuo, domicilio, replica, disponibilità di piano di accumulo e distribuzione — [justETF find-etf](https://www.justetf.com/uk/find-etf.html?index=Gold); [justETF search](https://www.justetf.com/en/search.html/1000)
- La **tracking difference** di justETF è citata da guide di terzi ("prendere la TD a 3 anni da justETF") — [haobin-tan notes](https://haobin-tan.netlify.app/docs/finance/etf/04_etf_selection/tracking_difference)
- justETF pubblica anche pagine broker con le offerte di PAC in ETF, ad esempio Trade Republic — [justETF broker Trade Republic](https://www.justetf.com/en/broker/trade-republic)

**Condizioni d'uso e scraping**
- Le AGB (sezione 3.1) obbligano l'utente ad astenersi da tutto ciò che può compromettere operatività, funzionalità o infrastruttura di justETF. Negli estratti letti non compare una clausola esplicita sullo scraping — [justETF AGB](https://www.justetf.com/documents/justETF_AGB.pdf); [Termini e Condizioni IT](https://www.justetf.com/documents/justETF_Termini_e_Condizioni_Generali.pdf)
- Esistono scraper non ufficiali su GitHub (ad esempio "JustETF Scraper API"), ma la loro esistenza non dimostra che lo scraping sia permesso — [GitHub Quadra-Ryo](https://github.com/Quadra-Ryo/JustETF-Scraper-API)

### Inferences
- Ciò che serve copiare da justETF in MyFinancePlace: (a) target per ETF **e** per asset class, (b) banda di
  default ±5 pp modificabile per posizione, (c) semaforo verde/rosso target/attuale, (d) lista ordini esportabile,
  (e) modalità "solo acquisti" con **calcolo del versamento minimo**. In Italia la (e) è la più preziosa, perché
  ogni vendita in plusvalenza paga il 26% (12,5% sulla quota in titoli di Stato).
- justETF non lega l'avviso a eventi come "data del PAC" o "nuovo versamento". L'avviso scatta solo sulla banda
  (controllo giornaliero) oppure su soglie di peso, valore o prezzo. MyFinancePlace può distinguersi offrendo
  trigger su eventi (versamento registrato, data PAC, calendario, movimento di mercato).
- justETF non ha il concetto di "conto titoli" sotto un portafoglio: ogni portafoglio è virtuale e piatto. Il
  modello "N conti per portafoglio" di MyFinancePlace va quindi preso da PP, Ghostfolio o Parqet, non da justETF.
- Non integrare dati di justETF via scraping senza aver letto per intero AGB e robots.txt. Meglio un link
  profondo alla scheda ETF (`justetf.com/it/etf-profile.html?isin=…`, schema URL da verificare) e dati propri
  (ISIN, TER, replica, distribuzione) inseriti a mano o presi da fonti con licenza.

### Gaps
- Testo integrale delle pagine Premium e AGB non letto (host bloccato). Non verificati: clausola anti-scraping,
  esistenza di un'API, fonte dei dati (dagli estratti non risulta).
- Non confermato se il Free includa l'analisi per paesi/settori/holding (look-through), né i dettagli di
  dividendi e metriche di performance (TWR/MWR) del tracker.
- Non trovati: pagina "Weltportfolio"/portafogli strategici ufficiali con elenco aggiornato al 2026, confronto PAC
  (Sparplan-Vergleich) per l'Italia, import dai broker.
- Nessuna data esplicita sui prezzi: valgono come "visti a nov 2026 negli estratti".

## 2. Come gli altri tool modellano portafogli multipli su più conti

### Takeaway
Nei tool di mercato ci sono due modelli. **(A)** "Portafoglio = vista che raggruppa uno o più conti" (PP con i
filtri, Sharesight con le Consolidated Views, Parqet con l'aggregazione di più depositi). **(B)** "Raggruppamento
per tag o tassonomia" (Ghostfolio con i tag, PP con le classificazioni). Gli estratti non mostrano un tool in cui
un conto titoli venga diviso tra più portafogli logici senza tag o classificazioni.

### Cited Findings
- **Portfolio Performance**: il ribilanciamento lavora su una classificazione con pesi target per categoria. Gli
  utenti devono impostare il **filtro su depositi e conti** per un calcolo corretto. Un conto che non partecipa
  va comunque incluso nella classificazione con target 0. Le proposte di acquisto e vendita escono solo a
  livello di titolo, mentre i delta si vedono anche per regione. Il peso è riferito alla categoria superiore, e
  questo è un limite segnalato dagli utenti. Esiste una colonna "% sul patrimonio totale" — [Forum PP: Rebalancing mit Portfolio Performance](https://forum.portfolio-performance.info/t/rebalancing-mit-portfolio-performance/19); [Forum PP: Abweichung in %](https://forum.portfolio-performance.info/t/abweichung-in-beim-rebalancing-bezogen-auf-das-gesamtvermogen/16047)
- **Sharesight**: le "Consolidated Views" uniscono più portafogli in un'unica panoramica con alcuni report
  (Diversity, Performance, Future Income, Contribution). Tutti i portafogli devono avere la stessa residenza
  fiscale, la funzione è pensata per **al massimo 5 portafogli** e i report fiscali non sono disponibili nella
  vista consolidata — [Sharesight Help: Consolidated Views](https://help.sharesight.com/consolidated_views); [Sharesight blog](https://sharesight.com/blog/consolidated-views); [new functionality](https://sharesight.com/blog/new-functionality-for-consolidated-views)
- **Parqet**: più depositi in una panoramica centrale, con il tab "Attività" che riunisce le transazioni di tutti
  i depositi. Portafogli separati: 1 nel piano base, fino a 5 in Plus, fino a 15 in Investor — [Parqet blog: mehrere Portfolios](https://parqet.com/en/blog/mehrere-portfolios); [justETF: Parqet Erfahrungsbericht](https://www.justetf.com/de/academy/parqet-erfahrungsbericht.html)
- **Getquin**: un portafoglio si collega a un broker via PSD2. Gli estratti non dicono come funzioni la vista
  aggregata tra depositi — [finanzwissen.de: getquin test](https://finanzwissen.de/anbieter/getquin/test/)
- **Ghostfolio**: posizioni raggruppate per **account** (broker, banche, previdenza, exchange crypto) e piattaforma,
  con filtri per account, asset class, intervallo di date e **tag**. X-Ray segnala rischi di concentrazione, valuta
  e liquidità. Fonti di terzi, non la documentazione ufficiale — [elest.io](https://blog.elest.io/ghostfolio-free-open-source-privacy-first-portfolio-wealth-tracker/); [Railway template](https://railway.com/deploy/ghostfolio-self-hosted-portfolio-and-wealth-tracker--ghostfolio-portfolio-tracker)
- **Wealthfolio**: nessuna documentazione ufficiale trovata (host bloccato, ricerca senza risultati pertinenti).

### Inferences
- Modello consigliato per MyFinancePlace: `Portafoglio (logico, con target)` ⟷ `Conto titoli (broker)` in relazione
  **molti-a-molti a livello di posizione o lotto**. Ogni operazione appartiene a un conto titoli e a un
  portafoglio. Così un portafoglio "Pensione" può stare su Fineco e Directa, e un conto Directa può ospitare
  "Pensione" e "Obiettivo casa". Le viste servono aggregate per portafoglio, per conto, per broker e totale, come
  le viste consolidate di Sharesight e i filtri di PP.
- Il limite di PP (target solo sulla categoria superiore, filtro obbligatorio) suggerisce di legare i target al
  portafoglio logico, non alla vista filtrata.

### Gaps
- Docs ufficiali di Wealthfolio (account groups, rebalancing/targets) e di Ghostfolio non lette: gli host
  wealthfolio.app e ghostfol.io non sono stati raggiunti, e i dettagli sono coperti dagli altri ricercatori.
- Non verificato se Parqet o Getquin permettano a uno stesso deposito di comparire in più portafogli.

## 3. Ribilanciamento: target, bande, solo nuova liquidità, notifiche

### Takeaway
Le pratiche comuni sono: target per titolo o per categoria; banda assoluta, tipicamente 5 pp (justETF ±5 pp di
default; RBC cita una soglia assoluta del 5% come best practice); ribilanciamento con i flussi in entrata o in
uscita (justETF "solo acquisti" + versamento minimo, Endowus); attenzione al costo fiscale delle vendite (Wealthfront). Gli avvisi esistenti sono quasi sempre **basati su soglia, con controllo
giornaliero**.

### Cited Findings
- justETF: banda ±5 pp per asset class o ETF, e-mail giornaliera, "Only buy transactions", versamento minimo — vedi sezione 1 ([monitoring](https://justetf.com/en/tutorial/monitoring/how-does-portfolio-monitoring-work.html), [deposit with rebalancing](https://www.justetf.com/de/tutorial/rebalancing/portfolio-deposit-with-rebalancing.html))
- Wealthfront controlla ogni giorno il drift rispetto ai target, concede più margine alle classi con peso target
  maggiore (banda di fatto relativa) e tiene conto del costo fiscale delle vendite — [Wealthfront support](https://support.wealthfront.com/hc/en-us/articles/209353766-How-often-do-you-rebalance-my-portfolio-)
- Endowus usa i flussi in entrata e in uscita per avvicinarsi ai target, salta il ribilanciamento se lo
  scostamento è piccolo e manda un avviso quando un fondo esce dalla banda — [Endowus help](https://help.endowus.com/hc/en-sg/articles/360000669273-why-is-my-portfolio-allocation-different-from-the-target-allocation)
- Soglia assoluta del 5% citata come best practice — [RBC Wealth Management](https://wmc.rbcwealthmanagement.com/7638184593319206765/blog/gaining-traction/)
- Il ribilanciamento tramite PAC (spostare le rate sulle posizioni sottopesate) non genera vendite né tasse, ma
  non basta più quando il capitale è grande rispetto alla rata — [Finanzfluss: ETF-Rebalancing](https://www.finanzfluss.de/etf-handbuch/etf-rebalancing/); [Finanztip forum](https://www.finanztip.de/community/forum/thema/13241-regelm%C3%A4%C3%9Figes-re-balancing/)
- Trigger tipici citati: a tempo (ad esempio annuale) o a soglia (ad esempio 5%) — [aktienrenterechner.de](https://aktienrenterechner.de/ratgeber/depot-rebalancing-anleitung)
- extraETF offre un calcolatore di ribilanciamento gratuito con target per titolo — [extraETF calculator](https://extraetf.com/de/calculator/rebalancing)
- Parqet: nessuna informazione trovata su una funzione di target o ribilanciamento.

### Inferences
- Specifica proposta per MyFinancePlace:
  - Target su due livelli: asset class (o tassonomia libera) e strumento. La somma deve fare 100%, validata.
  - Banda per posizione, **assoluta (pp) o relativa (% del target)**, con regola "5/25": 5 pp assoluti oppure il 25%
    relativo per pesi piccoli. Default ±5 pp come justETF.
  - Tre modalità di calcolo: *completo* (compra e vendi), *solo acquisti con importo X*, *versamento minimo per
    tornare in banda o al target*. Più *prelievo con ribilanciamento* (vende i sovrappesati).
  - Ordini suggeriti arrotondati a quote intere (o frazionarie se il broker lo consente), con commissione stimata
    per broker e **tassa stimata sulle vendite** (26% / 12,5% pro-quota sui titoli di Stato, con compensazione
    minusvalenze). Gli estratti non mostrano nessun tool di riferimento che lo faccia per l'Italia: è un
    differenziatore.
  - Distribuzione degli ordini tra conti: suggerire su quale conto titoli comprare (commissione più bassa, PAC
    gratuito sul broker) quando il portafoglio sta su più conti.
- Trigger di notifica (richiesta dell'utente), tutti configurabili per portafoglio:
  1. **Drift**: una posizione o classe esce dalla banda (controllo giornaliero dopo l'aggiornamento prezzi), come justETF.
  2. **Nuovo versamento o liquidità disponibile** sul conto del portafoglio oltre una soglia → "investi X così".
  3. **Data PAC** (N giorni prima) → ripartizione suggerita della rata per ridurre il drift.
  4. **Calendario** (mensile, trimestrale, annuale) → revisione periodica.
  5. **Movimento di mercato**: variazione del valore del portafoglio o di un indice oltre il ±X% in N giorni.
     Riprende gli avvisi justETF su valore e quotazione.
  6. Dedup e quiete: non ripetere lo stesso avviso finché la condizione persiste, con snooze.
  Canali: notifiche desktop già presenti (vedi `docs/DESKTOP.md`) + riepilogo in-app.

### Gaps
- Implementazioni di Wealthfolio, Ghostfolio e Parqet non verificate (fonti irraggiungibili o mancanti). Gli altri
  ricercatori coprono gli interni di Wealthfolio, Ghostfolio e PP.
- Non trovata nessuna fonte su tool che legano l'avviso alla data del PAC: sembra una lacuna di mercato, ma non è
  dimostrato.

## 4. Registro ordini: campi, imposte italiane, fissati bollati

### Takeaway
Un registro ordini completo deve salvare almeno: data e ora, conto titoli/broker, portafoglio, ISIN e ticker,
mercato/venue, lato, quantità, prezzo, valuta dello strumento, cambio, commissioni, imposte (Tobin tax italiana su
azioni italiane, tasse estere), totale regolato nella valuta del conto, tipo ordine, note e allegato PDF del
fissato bollato. Per l'Italia bisogna tenere separate la Tobin tax (per operazione) dall'imposta di bollo
(annuale, a livello di conto) e dalla tassazione delle plusvalenze.

### Cited Findings
- Tobin tax italiana sugli acquisti di azioni italiane quotate: 0,1% fino al 2025, **0,2% dal 2026** (0,4% per
  quelle non quotate) — [Milano Finanza](https://www.milanofinanza.it/news/equita-tobin-una-patrimoniale-sulle-societa-italiane-2722468); [Fisco Investimenti](https://fiscoinvestimenti.it/?p=7627)
- **In conflitto**: Teleborsa (2 nov 2026) scrive di una manovra che porterebbe l'imposta dallo 0,2% allo 0,4% (un
  "secondo raddoppio"). Non c'è conferma che sia legge — [Teleborsa 2026-11-02](https://www.teleborsa.it/News/2026/11/02/tobin-tax-nessun-crollo-dopo-il-primo-raddoppio-ma-il-secondo-e-una-scommessa-117.html); [FinanzaOnline](https://www.finanzaonline.com/notizie/la-tobin-tax-raddoppia-tutti-gli-effetti-su-borsa-fondi-azioni-ed-etf)
- Gli ETF in genere non pagano la Tobin tax lato investitore (la paga l'OICR quando compra azioni italiane).
  Sono escluse le società con capitalizzazione sotto i 500 milioni di euro (elenco MEF annuale) — [Moneyfarm: Tobin Tax e ETF](https://blog.moneyfarm.com/it/investimenti/tobin-tax-etf/); [FinanzaOnline](https://www.finanzaonline.com/?p=692193)
- Portfolio Performance importa più PDF di contratti in blocco. Per Scalable i documenti stanno presso Baader Bank
  e un add-on del browser li raccoglie — [Forum PP: Trade Republic vs Scalable](https://forum.portfolio-performance.info/t/was-ist-ubersichtlicher-trade-republic-oder-scalable-capital/26925)
- Import CSV di PP: 5 tipi di dati (transazioni di conto, di deposito, titoli, quotazioni storiche, deposito) — [Forum PP: Import CSV](https://forum.portfolio-performance.info/t/import-csv-file/17123)
- Campi minimi dell'import di TradingView: Symbol, Side, Qty, Fill Price, Commission, Closing Time — [TradingView support](https://www.tradingview.com/support/solutions/43000756014)
- Finanzfluss Copilot importa Trade Republic in automatico (numero di cellulare + PIN) e separa deposito e conto
  di regolamento — [Finanzfluss Copilot help](https://www.finanzfluss.de/copilot/hilfe/trade-republic-depot-importieren/)

### Inferences
- Schema proposto per `ordine`/`operazione` (da validare con gli altri ricercatori):
  `id, portafoglio_id, conto_titoli_id, data_esecuzione, ora, data_valuta, strumento_id (ISIN, ticker, nome),
  mercato/venue (es. Borsa Italiana ETFplus, Xetra, TradeGate), lato (acquisto/vendita/PAC/dividendo/split/
  trasferimento), quantità (decimale, per frazionarie), prezzo unitario, valuta_strumento, cambio, controvalore,
  commissione, altre spese, tobin_tax, tasse_estere, ritenuta (per i dividendi), totale_addebitato
  (valuta del conto), tipo_ordine (mercato/limite/stop/PAC), id_ordine_broker, note, allegato (PDF fissato
  bollato), origine (manuale/import CSV/import PDF)`.
- Il bollo titoli (0,2% annuo sul controvalore, secondo il regime noto prima del 2026) va trattato come
  **movimento di conto periodico**, non come campo dell'ordine. Gli estratti trovati sono datati o contraddittori
  e l'aliquota 2026 va verificata (vedi Gaps).
- I campi di PP per il "Kauf" (data e ora, quote, prezzo, commissioni, tasse, cambio, nota) li conosco da prima,
  non da una fonte letta in questa sessione: da confermare con il ricercatore su PP.

### Gaps
- Aliquota dell'imposta di bollo sui conti titoli nel 2026: non trovata una fonte aggiornata (gli estratti parlano
  di 0,15%/0,20% in termini storici).
- Esito della proposta "Tobin tax 0,4%" nella legge di bilancio 2027: non confermato al 9 nov 2026.
- Formati dei fissati bollati dei broker italiani (Fineco, Directa, Banca Sella, IBKR IT): non ricercati qui.

## 5. Cosa mostrano le dashboard di portafoglio (base per la dashboard Investimenti)

### Takeaway
Le dashboard dei tracker mostrano di solito: valore totale, rendimento con TWR/MWR, guadagno o perdita
(realizzato/non realizzato), variazione del giorno, valore nel tempo, allocazioni, dividendi o rendite future,
confronto benchmark, attività recenti, e (justETF) target contro attuale con semaforo. Mancano quasi sempre
"prossimo PAC", "stima tasse" e "commissioni pagate", che diventano differenziatori per l'Italia.

### Cited Findings
- Ghostfolio: valore del portafoglio, guadagni e perdite, patrimonio netto nel tempo, attività recenti, widget e
  filtri. X-Ray per concentrazione, valuta e liquidità (fonti di terzi) — [elest.io](https://blog.elest.io/ghostfolio-free-open-source-privacy-first-portfolio-wealth-tracker/); [Railway](https://railway.com/deploy/ghostfolio-self-hosted-portfolio-and-wealth-tracker--ghostfolio-portfolio-tracker)
- Sharesight: Overview con performance combinata e report Diversity (anche per Custom Groups contro un target),
  Performance, Future Income (dividendi futuri) e Contribution Analysis — [Sharesight Consolidated Views](https://help.sharesight.com/consolidated_views); [Sharesight blog insights](https://sharesight.com/blog/5-ways-to-get-the-portfolio-insights-you-need)
- justETF: peso target (grigio) e attuale (verde o rosso) per posizione, avviso fuori banda nella panoramica,
  simulazione storica contro benchmark, rischio/rendimento per ETF (Premium) — [monitoring](https://justetf.com/en/tutorial/monitoring/how-does-portfolio-monitoring-work.html); [Premium](https://www.justetf.com/en-de/premium.html)
- Parqet: panoramica centrale di più depositi e feed delle attività su tutti i depositi — [justETF: Parqet Erfahrungsbericht](https://www.justetf.com/de/academy/parqet-erfahrungsbericht.html)

### Inferences
Elenco proposto per la dashboard Portafoglio/Investimenti di MyFinancePlace (con selettore: Tutti · Portafoglio X ·
Conto titoli Y · periodo):
1. **KPI in alto**: valore attuale · capitale investito netto (versamenti meno prelievi) · guadagno non realizzato
   (€, %) · guadagno realizzato nell'anno · variazione del giorno e della settimana · rendimento TWR e MWR/IRR nel
   periodo · liquidità disponibile sui conti titoli.
2. **Grafico valore nel tempo**: valore contro capitale investito (area), con benchmark opzionale (ad esempio MSCI
   ACWI) normalizzato.
3. **Allocazione contro target**: barre per asset class e strumento con target, attuale, delta in pp e in €,
   semaforo della banda. Pulsante "Ribilancia" che apre le tre modalità.
4. **Allocazioni**: per asset class, area geografica, valuta, broker/conto, portafoglio. Look-through per
   paese/settore/holding se i dati sono disponibili.
5. **Prossimi eventi**: prossimo PAC (data, importo, ripartizione suggerita), prossimi dividendi o cedole, avvisi
   attivi (drift, liquidità, mercato).
6. **Rendite**: dividendi e cedole incassati (anno corrente contro precedente, mensile) e stima a 12 mesi.
7. **Costi e tasse**: commissioni pagate nell'anno e dall'inizio, costo TER annuo stimato (somma del TER pesato
   sul valore), Tobin tax pagata, bollo maturato e stimato, **tassa latente** sulle plusvalenze (26% / 12,5%) e
   minusvalenze compensabili con scadenza.
8. **Migliori e peggiori**: posizioni migliori e peggiori nel periodo e contributo al rendimento.
9. **Ultimi ordini**: ultime N operazioni dal registro ordini, con link al fissato bollato.

### Gaps
- Contenuto esatto delle dashboard di PP, Wealthfolio e Ghostfolio non verificato su fonti primarie (host
  bloccati): lo coprono gli altri ricercatori.
- Non verificato cosa mostri la dashboard Getquin o Parqet (TWR/IRR, dividendi): nessuna fonte primaria letta.
