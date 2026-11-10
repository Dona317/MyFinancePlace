# MyFinancePlace — inventario verificato sul codice (ramo claude/charming-fermi-3izxwg = test-Cloud @ a6dcf0c + docs 293a3ca, 9 nov 2026)

Fonti = file del repo locale `/home/user/MyFinancePlace` (percorso:riga). Stati: **implementato** / **parziale** / **pianificato** / **assente**. Solo ciò che il codice mostra; dove cito un documento di piano lo dico.

Contesto tecnico: Flask + Jinja + PostgreSQL (anche incorporato nell'exe desktop pywebview), grafici con **Chart.js 4.4.3** in locale (`app/static/vendor/chart.umd.min.js`, intestazione del file), nessuna CDN. Nessun Plotly nel codice (lo cita solo `docs/ANALISI_COMPETITOR.md:62`). Ultimi commit: F34 prestiti come conti di debito (a6dcf0c), F39/F32/F28, F40, F33, F38, F37, F35, F36 (`git log --oneline -40`).

## 1. Sezioni / navigazione (menu) e disattivazione per utente (F18)

### Takeaway
Il menu laterale ha 5 gruppi (Panoramica, Contabilità, Stile di Vita, Gestione, Strumenti) con ~27 voci, quasi tutte marcate badge «TBD»; ogni sezione (tranne Dashboard e Impostazioni) può essere spenta per tutti (Moduli), bloccata da un admin per un utente, o nascosta dall'utente stesso (F18, implementato).

### Cited Findings
- **Panoramica**: Dashboard (`app/templates/base.html:59`), Transazioni (`:64`), Entrate `/reports/income` (`:70`), Uscite `/reports/spending` (`:74`), Abbonamenti (`:80`), Report (`:85`, contiene schede Riepilogo, Ritmo, Bilancio dell'anno — `app/routes/reports.py:181,217,229`). Tutte tranne Dashboard/Transazioni hanno il badge `nav-badge-tbd` — `app/templates/base.html` (righe dei link).
- **Contabilità**: una voce sola (`base.html:100`), pagina a schede `app/templates/accounting/base.html`: Stato patrimoniale (`balance_sheet.html`), Conto economico (`income_statement.html`), Flusso di cassa (`cash_flow.html`), Crescita del patrimonio (`growth.html`), Bilanci annuali chiusi (`closes.html`, F37).
- **Stile di Vita**: sottotitolo *Strategia* → Obiettivi (`:119`), Budget (`:125`); sottotitolo *Pianificazione* → Eventi (`:136`), Previsioni (`:142`, con sotto-pagina Pensione e FIRE `forecast/retirement.html`), Promemoria (`:148`). («Spese e tendenze» è stata fusa in Uscite il 2 nov — `docs/PIANO_E_TODO.md:111`.)
- **Gestione**: Conti e Carte (`:167`), Portafoglio (`:173`), Debiti (`:179`), Lavoretti (`:185`), Prestiti tra persone (`:191`), Assicurazioni (`:197`), Bollette (`:203`), Documenti (`:209`, con scheda Documenti in scadenza `documents/expiring.html`), Fisco (`:215`).
- **Strumenti**: Istantanee (`:231`), Importa (`:237`), Esporta (`:241`), Salute dei dati (`:247`), Clienti (`:253`), Gruppi e famiglia (`:259`).
- Piede della barra: account utente/esci (`:294-295`), campanella notifiche (`:303`), chiaro/scuro, Impostazioni (`:314`); bottone tondo «+» Nuova transazione con scelta singola/«Carica un file» (`:401-415`); bollino AI «Chiedi ai tuoi dati» con pannello laterale (`:429`, F29).
- Impostazioni: account, AI, categorie, valute, desktop, menu personale, titolari/IBAN, fonti prezzi, regole, classificazioni titoli (`app/templates/settings/*.html`).
- **F18, tre livelli** — `app/services/sections.py:1-12`: (1) interruttore globale Impostazioni → Moduli (solo per portfolio, debt, insurance, documents, tax, snapshots, export, goals: campo `setting` in `SECTIONS`, `sections.py:34-61`); (2) bloccata dall'admin per un utente (`User.blocked_sections`, `app/models/user.py`; `blocked()` `sections.py:~89`; pagine e API rispondono «accesso negato», template `section_blocked.html`); (3) nascosta dall'utente dal proprio menu (`User.hidden_sections`, `hidden()`), ancora raggiungibile da link. Admin mai bloccati; Dashboard e Impostazioni sempre presenti (`sections.py:9-11`).
- 26 chiavi di sezione in `SECTIONS` (`sections.py:34-61`): reports, accounting, forecast, subscriptions, lifestyle, budget, goals, events, transactions, accounts, portfolio, debt, insurance, gigs, loans, utilities, documents, tax, deadlines, snapshots, export, assistant, health, clients, groups, notifications.

### Inferences
- I gruppi in `SECTIONS` (usati nelle pagine delle Impostazioni) non coincidono più con il menu reale (es. `transactions` è nel gruppo «Gestione», `forecast`/`subscriptions` in «Contabilità», `deadlines` in «Strumenti» — `sections.py:36-53`), residuo della riorganizzazione F28: piccola incoerenza UI.
- Il badge «TBD» quasi ovunque indica che il proprietario considera le sezioni da rivedere (convenzione `ROADMAP.md:157`).

### Gaps
- Non ho verificato pagina per pagina il contenuto di Impostazioni → Moduli (solo le chiavi `setting`).

## 2. Grafici, tabelle e KPI

### Takeaway
Tre soli tipi Chart.js (linea, barre — anche orizzontali/impilate/miste con linee e doppio asse —, ciambella/torta) più due visualizzazioni disegnate dal server (Sankey SVG, calendario-heatmap) e una tabella-heatmap; drill-down al clic verso le transazioni filtrate su dashboard e report. **Assenti**: area pura come tipo dedicato (ci sono linee con `fill`), treemap, waterfall, candlestick, scatter, bubble, radar, gauge, zoom/pan, confronto di periodi generico.

### Cited Findings
- Costruttori unici in `app/static/js/charts.js` (373 righe): `makeLineChart` (`:222`, type "line" `:232`), `makeBarChart` (`:272`; dataset con `type` per mescolare linee nelle barre `:285`, `stack` `:301`, `indexAxis` per orizzontali `:309`, `stacked` `:313-314`), `makeDoughnutChart` (`:336`, pie o doughnut `:344`); clic → `onClickIndex(index, datasetIndex)` (`:322-329`); legenda HTML con interruttori/«tutte» (`:81-168`); temi chiaro/scuro e palette entrate/uscite (`:9-46`, F31).
- **Dashboard** (`app/templates/dashboard/index.html`), 11 blocchi riordinabili, larghezza 1–3 terzi, altezza 0–3, nascondibili, con 3 preset nominati di disposizione+periodo (`app/services/dashboard_prefs.py:38-50`, F36):
  - «Flusso di cassa e risparmio»: barre+linee miste, entrate/uscite/risparmio del mese (linee), risparmio cumulato (barre, asse destro), cumulati entrate/uscite opzionali; clic su un mese → transazioni del mese (`index.html:441-453`).
  - «Andamento del patrimonio»: barre impilate liquidità/investimenti/altri beni/debiti + linea patrimonio netto (`:458-468`).
  - «Uscite/Entrate per categoria»: ciambelle; clic fetta → transazioni della categoria nel periodo (`:482-484`).
  - «Uscite/Entrate per categoria nel tempo»: linee per categoria mese per mese; clic punto → transazioni categoria×mese (`:487-497`).
  - «Totale dell'anno»: 3 barre entrate/uscite/netto, clic → transazioni (`:501-508`).
  - «Tasso di risparmio mese per mese»: linee per anno, chip per scegliere gli anni da confrontare (salvati in localStorage) (`:520-530`).
  - «Dove va il denaro»: **Sankey SVG generato dal server** (categorie entrata → totale → categorie uscita + risparmio/«Dai risparmi», max 7 per lato + «Altre»; nodi cliccabili → transazioni) — `app/services/sankey.py:1-30`, `dashboard/index.html:253-280`.
  - «Ultime transazioni» (con scelta conti), «Salute finanziaria» (mesi di autonomia ecc.) — `dashboard_prefs.py:48-49`.
  - KPI in alto (9 schede riordinabili, larghezza 1–2): Patrimonio netto, Entrate, Uscite, Tasso di risparmio, Investimenti, Debito totale + 3 segnaposto «Nuova scheda» TBD (`dashboard_prefs.py:106-116`); previsione sotto le schede: prossimo mese / chiusura mese / 12 mesi / nessuna (`:19-25`).
- **Report / Entrate / Uscite** (`app/templates/reports/index.html`): barre orizzontali o ciambella per categoria con clic → categoria (`:249-250`), linee per categoria nel tempo (`:263`), barre flusso entrate/uscite/netto (`:267`); periodi preset (questo mese … anno scorso, personalizzato — `app/services/reports.py:19-23`); confronto col periodo precedente come totale (`app/routes/reports.py:108-109`); sotto-categorie quando si sceglie una categoria principale (`:104-106`); CSV e PDF (`reports.py:134,143`).
- **Riepilogo**: tabella categoria × mese con heatmap CSS (`--heat`) — `app/templates/reports/summary.html:16`; F2 ✅ `docs/PIANO_E_TODO.md:67`.
- **Ritmo**: calendario-heatmap giornaliero dell'anno (celle `level-N`, clic → movimenti) + barre spesa media per giorno della settimana (`app/templates/reports/rhythm.html:29-33,78`).
- **Contabilità**: barre attività vs passività (`accounting/balance_sheet.html:134`); conto economico barre mensili + ciambella uscite (`income_statement.html:114,118`); flusso di cassa barre netto mensile + linea cumulata con fill (`cash_flow.html:113-114`); crescita del patrimonio barre impilate risparmio/mercati/debito rimborsato/nuovi beni (`growth.html:57-64`).
- **Previsioni**: linee storico+previsione con banda tra metodi/minimo (`forecast/index.html:383,391,398`); **Pensione/FIRE** linee Monte Carlo 10°/50°/90° percentile + linea quota obbligazioni (glide path) (`forecast/retirement.html:96,102`).
- **Portafoglio**: ciambella allocazione per classe + linea investimenti nel tempo (`portfolio/index.html:167,173`); linea prezzo del titolo (`portfolio/detail.html:144`, `history.html:81`); linea rendimento cumulato TWR vs benchmark (`performance.html:84`); barre impilate rendite mensili per tipo (`income.html:65-67`); ciambelle per area, settore e per ogni tassonomia propria (`composition.html:64,67`).
- Altre: Debiti linea piano di ammortamento + ciambella per tipo (`debt/index.html:123,126`); Assicurazioni ciambella premi (`insurance/index.html:125`); Bollette barre €/mese + €/unità su asse destro (`utilities/index.html:196`); Istantanee linea patrimonio netto con fill (`snapshots/index.html:128`); Consolidato di gruppo linee per membro, barre entrate/uscite, ciambelle spese e allocazione (`groups/consolidated.html:171-181`).
- Barre di avanzamento HTML (non Chart.js): budget con linea «dove dovresti essere», obiettivi, tetti di versamento, soglia Lavoretti, debiti rimborsati, scostamento dal modello — `lifestyle/budget.html:55`, `lifestyle/goals.html:49`, `tax/limits.html:76`, `gigs/index.html:64`, `debt/index.html:94`, `portfolio/highlights.html:47`.

### Inferences
- Il drill-down esiste solo verso la lista transazioni (non tra livelli di grafico, es. categoria → sottocategoria nel grafico); fuori da dashboard e report i grafici non sono cliccabili.
- Il grafico «Investimenti nel tempo» del Portafoglio legge le **Istantanee** (`app/routes/portfolio.py:109-121`: `Snapshot.query`, mostrato solo con ≥2 istantanee) e non lo storico prezzi × quantità: senza istantanee il grafico non c'è.
- Nessun grafico di saldo per singolo conto (nessun `make*Chart` in `templates/accounts/`), nessun grafico nelle Transazioni.
- Cambio periodo: dashboard (periodo unico, anni/semestre/trimestre, preset), report (preset), performance (finestre 1/3/5 anni e dall'inizio, F20h). Nessun selettore zoom sul grafico stesso.

### Gaps
- Non ho aperto ogni template per elencare tutte le tabelle; elencati solo grafici, heatmap e KPI principali.

## 3. Gestione dei dati

### Takeaway
Modello a movimento singolo (niente partita doppia, scartata — `ROADMAP.md:148-152`) con split, tag, ricorrenze, giroconti a due conti, multivaluta per transazione; import molto ricco (9 layout bancari + generico, OFX/QFX/QIF/CAMT.053/052, Excel/CSV/PDF/Word/ODF, OCR locale, AI locale o Claude); regole, storico e AI per la categorizzazione; duplicati, riconciliazione, undo a un passo, backup completo e cifrato. I dati sono **per archivio (cliente), non per utente**.

### Cited Findings
- **Modelli** (`app/models/__init__.py`, 873 righe totali): `Account` (tipo, valuta, saldo iniziale, IBAN, banca, preferito, intestatario, conti fissi Contanti/Debiti F30, riconciliazione `reconciled_on/_balance`, regole commissioni broker, regime fiscale amministrato/dichiarativo, estero) — `app/models/account.py:4-40`. `Transaction` (data, descrizione, importo, valuta, `amount_base` in valuta base, tipo income/expense/transfer, categoria testo, cluster, controparte, **tags ARRAY**, ricorrenza weekly/monthly/quarterly/yearly con fine, note, causale bancaria originale, `import_ref` impronta, `counter_import_ref`, conto e contro-conto, importi effettivi nella valuta del conto, `holding_id`, `units`, `unit_price`, `fee_for_id`, `debt_id`, `event_id`) e `TransactionSplit` — `app/models/transaction.py:6-89`. `Category` (tipo, hint per l'AI, discrezionale, natura fissa/periodica/variabile, esclusa dalle analisi, **un livello di sottocategorie** `parent_id`, tag suggeriti) e `CategoryRule` (parola chiave → categoria, manual/learned, hits) — `app/models/category.py`. Inoltre `Budget` (categoria, mese o ogni mese, rollover), `ExchangeRate` (manual/ecb), `SpendingEvent`, `Reminder`, `Goal`, `Debt`, `InsurancePolicy`, `Document`, `Snapshot`, `YearClose`, `ContributionLimit`, `DuplicateDismissal`, `ClusterRule`, `Gig`, `PersonalLoan`, `UtilityReading`, `Client`, `ClientGroup`, `User`.
- Categorie: la transazione salva il nome (testo), non una FK (`transaction.py:15`); gerarchia a 2 livelli + cluster sopra (Necessità / Scelte e svago / Risparmio) — `app/services/clusters.py` docstring.
- **Import estratti conto**: layout Fineco, Intesa Sanpaolo, UniCredit, BPER, Poste/BancoPosta, ING, Revolut, N26 + generico (`app/services/bank_import/__init__.py:4-21`; 10 `BankLayout(` in `layouts.py`). File: Excel, CSV, TXT, PDF testuale, Word .docx/.doc, RTF, ODS/ODT (`__init__.py:23`; `statement_readers.py`). Formati interscambio OFX 1/2, QFX, QIF, CAMT.053/052 con quadratura saldi (`app/services/structured_statements.py:1-12`, F6). OCR offline RapidOCR per scansioni/foto (`ocr.py`). AI per i casi non leggibili: Ollama locale (qwen2.5vl:7b) o Anthropic, con controllo saldi anti-allucinazione (`ai_extraction.py:1-19`). Import CSV/Excel/ODS con mappatura colonne indovinata dai valori, aiuto AI su un campione (`column_guess.py`, route `export.py:199,214`).
- **Categorizzazione automatica**: ordine regole utente → storico appreso (punteggio parole, senza modello) → regole incorporate per parola chiave (`bank_import/categorize.py:1-15`, `history_classifier.py`, `category_rules.py`); AI classifica categoria e controparte, sempre da confermare (`ai_classification.py`); estrazione esercente dalla causale (`merchant.py`); regole apprese quando l'utente corregge (`category_rules.py`).
- **Giroconti**: unione automatica dei due lati entro 15 giorni (`bank_import/transfers.py`), riconoscimento da IBAN/titolari (`owners.py`); prelievi bancomat → giroconto verso Contanti (F22i).
- **Duplicati**: stessa tipologia/importo, date vicine, descrizioni simili; pagina e avviso in anteprima import; «non è un doppione» memorizzato (`duplicates.py`, `transactions.py:508-532`, modello `DuplicateDismissal`); reimport dello stesso file bloccato dall'impronta `import_ref`.
- **Riconciliazione**: saldo vs estratto per conto (`app/routes/accounts.py:115-124`); «Conta i contanti» per il conto Contanti (F22i).
- **Multivaluta**: ogni transazione tiene valuta originale + `amount_base` nella valuta base al cambio del giorno; cambi BCE scaricabili o manuali (`app/services/currency.py:1-9,127-160`); conto Contanti multi-valuta (`account.py` `opening_foreign`).
- **Undo/redo**: un passo per direzione, per aggiunte/eliminazioni di transazioni, 30 minuti (`app/services/undo.py`, route `transactions.py:231,245`; F13). **Audit log: assente** (nessun modello/servizio di storico modifiche; solo `bank_description` originale non modificabile e versioni dei bilanci annuali `YearClose`).
- **Backup/restore**: zip completo (tutte le tabelle + documenti), copia di sicurezza prima del restore (`backup.py`); backup automatico cifrato X25519+AES-256-GCM su cartella scelta (`encrypted_backup.py`, F23).
- **Export**: CSV, JSON, PDF report, export fiscale per anno, PDF bilancio dell'anno (`app/routes/export.py:144-189`, `reports.py:238-244`); MCP server read-only per assistenti AI (`mcp_server.py`, F22h).
- **Ricerca/filtri/bulk**: registro con ricerca, cronologia ricerche, ordinamento per colonna, filtri categoria/importo/date/conto/persona, modifica massiva (tipo, categoria, gruppo, ricorrenza, conto, data) su selezione o su tutta la ricerca, elimina/assegna conto/conferma AI/classifica in blocco, «Controlla registro» (`transactions.py:312-606`; F24, F35, F38 in `docs/PIANO_E_TODO.md:108,118,121`).
- **Allegati**: `Document` collegabile a una transazione, con tipo, anno fiscale, scadenza e garanzia (`app/models/wealth.py` classe Document).
- **Multi-utente**: utenti con admin; «The data is shared by every user» (`app/services/users.py`; `app/models/user.py` docstring); separazione per **archivio** = un database PostgreSQL per cliente (`app/models/client.py` docstring, F11) e gruppi consolidati in sola lettura (`consolidation.py`, F21); `User.default_client_id` apre l'archivio del membro. Nessun `user_id` nei modelli dei dati (`docs/PIANO_E_TODO.md:33`; grep su `app/models`).
- **Salute dei dati**: lista di problemi (quantità negative, valute senza cambi, prezzi vecchi, giroconti a un lato, doppioni, senza categoria, titoli non prezzabili, conti non riconciliati) — `data_health.py`.

### Inferences
- Nessun collegamento bancario automatico (PSD2) per scelta (`docs/PIANO_E_TODO.md:127`).
- Undo limitato a creazione/cancellazione; modifiche (edit, bulk edit) non sembrano annullabili (docstring di `undo.py` cita solo "added or deleted").

### Gaps
- F4 (prova con estratti reali anonimizzati) ⬜ (`docs/PIANO_E_TODO.md:74`): l'affidabilità reale dei parser PDF non è verificata.
- F27 (classificazione AI in errore nell'exe) ⬜ (`docs/PIANO_E_TODO.md:110`).

## 4. Macro-sezione Portafoglio

### Takeaway
Portafoglio ampio e funzionante (F19 a–e ✅, F20c/h/j, F22c/d/e/f): titoli con ISIN, operazioni come transazioni, prezzo medio ponderato, XIRR + TWR, volatilità, drawdown, benchmark, rendite, composizione e tassonomie, portafoglio modello con ribilanciamento, regole/alert, PAC, import Degiro/generico, 5 siti prezzi + Stooq/CoinGecko + fonti custom, e fisco italiano (plusvalenze/RT/bollo/IVAFE/IC). Mancano: lotti/FIFO, guadagno da cambio separato, obbligazioni come strumento (scadenza, cedole programmate, rateo, YTM), BFP/buoni, grafico del valore ricostruito dai prezzi, broker oltre Degiro specifici, quadro RW/RM calcolati.

### Cited Findings
- **Modelli**: `Holding` unico (nome, ticker, classe, quantità, prezzo medio, prezzo corrente+data, intestatario, regione, settore, svalutazione annua, aliquota propria, estero, ISIN, valuta di quotazione, borsa, moltiplicatore derivati, fonte prezzo, posizione iniziale qty/prezzo/data) con proprietà value/cost/gain/gain_pct — `app/models/wealth.py` classe Holding; commento: «prices are kept in euro». `HoldingPrice` storico (data, prezzo, nota, stimato) — stesso file. Operazioni = `Transaction` con `holding_id`, `units` (negativo = vendita), `unit_price`, commissione collegata `fee_for_id` (`app/models/transaction.py:34-41`). Tipi operazione: buy, sell, fee, coupon (descrizione con «cedol»), dividend, tax — `app/services/portfolio_ops.py:52-59`. `PortfolioTemplate/TemplateSlot/SlotHolding` (modelli con tolleranza in punti), `PortfolioRule` (drift, drawdown, price_above, price_below, concentration), `InvestmentPlan` (PAC mensile/trimestrale, frazionario) — `app/models/portfolio_model.py`. `Taxonomy/TaxonomyCategory/HoldingCategory` con pesi % — `app/models/taxonomy.py`.
- **Classi**: Azione, ETF, Fondo, Obbligazione, Criptovaluta, Derivato (nel portafoglio); Conto Risparmio, Fondo Pensione, Immobile, Veicolo, Oggetti di valore, Altro (fuori dal portafoglio investimenti) — `app/services/wealth.py:27-41`.
- **Schermate** (`app/templates/portfolio/_nav.html`): Posizioni (index), In evidenza, Rendimenti, Rendite, Composizione, Portafoglio modello (+ ribilanciamento), Regole e PAC, Importa dal broker; più dettaglio titolo, operazione, storico prezzi, aggiorna prezzi, collega movimenti, frazionamento (`app/routes/portfolio.py:101-317`, `portfolio_rules.py:35-216`, `portfolio_templates.py:19-125`, `portfolio_import.py:31-146`).
- **Metriche**: KPI Posizioni = Valore totale, Guadagno, Investito, Dividendi (anno) (`portfolio/index.html` kpi); dettaglio = Valore, Guadagno non realizzato, Realizzato e incassato, Rendimento annuo (XIRR) (`portfolio/detail.html`); Rendimenti = TWR (Modified Dietz mensile concatenato), XIRR, volatilità annua, calo massimo, mese migliore/peggiore, finestre 1/3/5 anni, benchmark da ticker con prezzi mensili Yahoo (`app/services/performance.py:1-10,98-160`); XIRR in `portfolio_ops.py:185-256`. Rendite: ultimi 12 mesi e stima prossimi 12 (`portfolio/income.html`). In evidenza: movers da 1/1 e 12 mesi, 5 più pesanti e concentrazione, distanza dal modello, prezzi fermi (`portfolio_highlights.py:1-5`). Composizione per regione/settore/tassonomie (`composition.py:55`, `taxonomies.py:112`). Frazionamento azioni (`composition.py:31`).
- **Costo**: prezzo medio ponderato, commissioni d'acquisto incluse, ricalcolato da zero dalla posizione iniziale + operazioni a ogni modifica (`portfolio_ops.py:1-13,70-90`); **nessun lotto/FIFO** (nessun modello lotti; `capital_gains.py:4-5` usa il costo medio, come richiesto dal fisco IT).
- **Fonti prezzi** (gratis, senza chiave, solo se attivate): Yahoo Finance chart (con ricerca ticker da ISIN), Stooq di riserva, CoinGecko per cripto (`app/services/price_feed.py:1-13`); siti per ISIN OpenFIGI, justETF, Borsa Italiana (MOT, BTP in % del nominale), Morningstar (NAV fondi), ordinabili/disattivabili (`app/services/instrument_sources/__init__.py:13-24`); fonti personalizzate JSON/HTML/CSV con {ISIN}/{TICKER}/{DATA} (`instrument_sources/custom.py`). Aggiornamento automatico una volta al giorno (prima visita o app desktop) e primo anno di prezzi settimanali al primo aggiornamento (`price_feed.py:10-13,401-441`). Scraping fragile: «la pagina è cambiata» (`instrument_sources/base.py:5-7`); i siti reali non provati dalla sandbox (`docs/PIANO_E_TODO.md:102`).
- **FX**: prezzo in altra valuta convertito in euro con i cambi salvati al momento della lettura (`price_feed.py:7`, `_to_euro` `:197`); nessuna separazione rendimento in valuta locale vs effetto cambio (nessun codice trovato).
- **Import broker**: Degiro «Transactions» (intestazioni EN/IT) + generico per titoli di colonna; obbligazioni % nominale convertite; impronta anti-doppioni; titolo trovato per ISIN/ticker/nome o creato (`app/services/broker_import.py:1-14,108-110`); collegamento movimenti del conto corrente a operazioni (`portfolio_import.py:123-146`). Nessun parser specifico per Fineco, Directa, Scalable, Trade Republic, IBKR, Banca Sella ecc. (grep in `broker_import.py`).
- **Fisco (F15)**, schede `tax/_tabs.html`: 730 spese detraibili, Plusvalenze, Bollo e IVAFE, Tetti di versamento, Lavori occasionali. Plusvalenze: redditi di capitale (ETF/fondi) vs diversi, minus compensabili per 4 anni, titoli di Stato 12,5% con peso 48,08%, cripto 26%→33% dal 2026, per broker (amministrato) o dichiarativo con riepilogo RT (`app/services/capital_gains.py:1-16`). Bollo 34,20 € > 5.000 € giacenza media, 2‰ titoli/depositi, IVAFE estero, IC cripto (`app/services/stamp_duty.py:1-12`). Parametri per anno da L. 207/2024 e L. 199/2025 (`tax_rules.py:1-6`). Quadro RM solo come nota testuale (`tax/investments.html:80`); **RW assente**; F15 «da fare poi»: tetto detrazioni > 75.000 €, quadro RM, pro rata del bollo (`docs/PIANO_E_TODO.md:101`).
- **Obbligazioni/BTP/BFP**: BTP prezzabili da Borsa Italiana (quantità = nominale, prezzo/100) e aliquota 12,5% impostabile sul titolo (`instrument_sources/borsaitaliana.py:1-5`, `wealth.py` Holding.tax_rate). **Nessun campo** scadenza, cedola, rateo, YTM, duration; nessun BFP/buoni fruttiferi (grep vuoto su services/models/templates portfolio).
- **Altro**: svalutazione automatica di veicoli/beni (`valuations.py`, F22c); debito collegato al bene finanziato (F20d); filtro per persona (`portfolio.py:106`); alert delle regole nei promemoria e notifiche desktop (`portfolio_rules.py`); PAC con proposta d'acquisto secondo il modello e commissioni (`investment_plans.py:89-144`).
- **Test** dedicati (numero di funzioni `test_`): broker_fees 6, broker_import 12, composition 3, holding_prices 7, instrument_sources 15, instruments 14, performance 7, portfolio_highlights 3, portfolio_models 9, portfolio_ops 8, portfolio_rules 11, price_feed 6, tax 14, taxonomies 4, currency 6 (grep su `tests/`); 834 funzioni di test in totale (grep), 1047 test passati il 2 nov secondo `docs/PIANO_E_TODO.md:140`.
- **Stato F19**: ✅ «F19 completo» (a, a-bis, b, c, d, e) — `docs/PIANO_E_TODO.md:102`.

### Inferences
- **Assenti/deboli rispetto a un portfolio tracker dedicato**: lotti e metodi FIFO/LIFO (per conti esteri/dichiarativo); calendario cedole/dividendi programmati (la stima è «se si ripetono gli ultimi 12 mesi»); scheda obbligazione (scadenza, cedola, YTM, rateo, rimborso); BFP/libretti; grafico valore storico del portafoglio ricostruito da prezzi×quantità (oggi da Istantanee) e confronto multi-titolo; effetto cambio; ritenute estere sui dividendi (solo «tax» generico); prezzi intraday/candlestick; più parser broker; quadro RW e RM calcolati; analisi costi (TER) e look-through ETF (assenti, nessun campo TER).
- Il prezzo è salvato solo in euro: un titolo USD perde il prezzo in valuta originale, quindi niente rendimento in valuta locale.

### Gaps
- Non ho eseguito i test né l'app: le funzioni sono verificate sul codice, non al runtime.
- Il funzionamento reale dei siti scraped (justETF, Borsa Italiana, Morningstar) è dichiarato non provato dalla sandbox (`docs/PIANO_E_TODO.md:102`).

## 5. Elementi pianificati (documenti di piano) su grafici, dati e portafoglio

### Takeaway
Quasi tutto il backlog storico è ✅; restano aperti F24 (grafici «del costruttore», dati per utente, cluster oltre due livelli), F41 carte collegate ai conti (prossima), F4, F27, i «dopo» di F15 e F29, D1 merge su main.

### Cited Findings
- F24 🔄 «Da fare»: carte collegate ai conti (mockup TBD), clusterizzazione oltre i due livelli, **grafici del costruttore oltre quelli di base**, separazione dati tra utenti — `docs/PIANO_E_TODO.md:108`.
- F41 ⬜ «▶ PROSSIMA — Carte collegate ai conti» — `docs/PIANO_E_TODO.md:124`.
- F28 🔄 resta ⑥ verifica finale; deciso: bilanci solo annuali o semestrali, niente trimestri — `docs/PIANO_E_TODO.md:111`.
- F15 «da fare poi»: tetto detrazioni > 75.000 €, quadro RM, pro rata bollo — `docs/PIANO_E_TODO.md:101`.
- F29 «Dopo»: chat con memoria e streaming — `docs/PIANO_E_TODO.md:164`.
- F4 ⬜ estratti reali; F27 ⬜ AI nell'exe — `docs/PIANO_E_TODO.md:74,110`.
- Esclusi per scelta: collegamento automatico banche, budget a buste/zero-based, partita doppia — `docs/PIANO_E_TODO.md:127`, `docs/ANALISI_COMPETITOR.md:73-74`, `ROADMAP.md:148-152`.
- D1 (merge PR #8 su main) ⏸ novembre 2026 — `docs/PIANO_E_TODO.md:45`.
- `docs/ANALISI_COMPETITOR.md` (aggiornato 8 ott) segna ✅ split, Sankey, Riepilogo, tasso di risparmio, rollover, fisse/variabili, abbonamenti, OFX/QIF/CAMT (`:58-70`); nessun item portafoglio ancora aperto lì. ROADMAP descrive i 4 grafici + 2 istogrammi + Sankey della dashboard come ✅ (`ROADMAP.md:43-60`).

### Inferences
- Nessun documento di piano contiene oggi un elenco di lavori futuri specifico del Portafoglio dopo «F19 completo»: è lo spazio che il piano Portafoglio dovrà riempire.
- `PIANO_E_TODO.md:7` (732 test, 24 migrazioni, 31 ott) è disallineato rispetto a `:140` (1047 test passati il 2 nov).

### Gaps
- `docs/NEXT_STEPS.md` è solo cronologia e rimanda a PIANO_E_TODO (`docs/NEXT_STEPS.md:120-122`); non l'ho letto riga per riga.
