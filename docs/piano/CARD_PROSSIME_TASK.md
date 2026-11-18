# Card delle prossime task (F106) — 16 novembre 2026

Una Card per ognuna delle task ancora aperte tra le 48 di «Piano delle prossime task» in [PIANO_E_TODO.md](PIANO_E_TODO.md), nello
stesso ordine (giri 0–6, più il giro D di design aggiunto il 18 nov). Ogni Card sta in piedi da sola e si può copiare così com'è.

- **Priorità**: Alta, Media, Bassa. **Sforzo**: S fino a mezza giornata, M un giro di lavoro, L più giri.
- **Origine**: la voce del piano (Fn, Dn), la card dei brainstorm del 15 nov (Card 1–21, P, D, O, B) o la misura di
  velocità del 15 nov da cui nasce.
- **Card finite e tolte da questo file**: T01 file personali fuori dal repository e dalla storia, T02 promemoria tenuti tra le pagine, T03 serie storiche e patrimonio mese per mese, T04 Uscite e Bollette, T05 utente di prova, T07 elenco «sezione finita» (16 nov 2026); T09 orizzonte e avviso del periodo, T11 promemoria e storico della riconciliazione, T15 Transazioni senza card e con la finestra AI (18 nov 2026). I risultati sono nel piano.
- Le pagine non sono state riviste a schermo una per una: nelle Card di revisione la revisione a schermo è il primo
  passo.

---

## Giro 0 — Fondamenta

**Card T06 — Test live a ogni giro**
- **Area:** Affidabilità · **Giro:** 0 · **Priorità:** Alta · **Sforzo:** S
- **Fatto il 18 nov:** suite completa verde (1308 passati; fallisce solo il test dell'OCR locale), copertura 97,24 %, `untested_functions` a 0, CI verde su GitHub, numeri in `CLAUDE.md`.
- **Resta:** i test live (`sh scripts/live/run.sh`) non girano su questo PC Windows: servono gunicorn (solo Linux e macOS), Playwright con Chromium e `psql`. Al loro posto le pagine nuove si provano a schermo con il server demo (T05).
- **Da decidere:** dove farli girare — in un container Linux (Docker, con un `Dockerfile` di prova) o in una sessione cloud — oppure lasciarli prima dei rilasci soltanto.
- **Dipende da:** la tua decisione.
- **Origine:** Card 1 e 4.
- **Fatto quando:** i test live sono verdi su `test-Cloud` dopo il giro 2.

---

## Giro 1 — Schemi comuni

**Card T08 — Export CSV ed Excel dove manca, con numeri veri**
- **Area:** Esportazioni · **Giro:** 1 · **Priorità:** Media · **Sforzo:** M
- **Descrizione:** L'export c'è in Transazioni, Report, Portafoglio, Fisco e Clienti. Manca sulle tabelle di Budget, Obiettivi, Debiti, Assicurazioni, Bollette, Lavoretti, Prestiti tra persone, Documenti, Istantanee ed Eventi. Inoltre nell'Excel importi e date sono testo, come nel CSV: devono diventare numeri e date, così si sommano senza conversioni. I nomi dei file seguono la regola `YYYYMMDD_archivio_nome`.
- **Dipende da:** T07.
- **Origine:** richiesta «export ovunque», Card 15.
- **Fatto quando:** ogni tabella delle sezioni elencate ha i due pulsanti, e una somma in Excel sugli importi esportati funziona.

**Card T10 — Menu a hamburger su tutte le pagine**
- **Area:** Periodo e barra · **Giro:** 1 · **Priorità:** Media · **Sforzo:** M
- **Descrizione:** Su finestre strette solo la Dashboard raccoglie i comandi della barra in un menu a destra. Va esteso a tutte le pagine, con le voci nello stesso ordine della barra (Periodo, preset o viste, Confronta, altre azioni, Modifica, Gestisci).
- **Dipende da:** niente.
- **Origine:** Card 10.
- **Fatto quando:** sotto i 1200 px nessuna barra va a capo o esce dallo schermo.

---

## Giro 2 — Tutti i giorni

**Card T12 — Riconciliazione: candidati e controllo in Salute dei dati**
- **Area:** Conti · **Giro:** 2 · **Priorità:** Media · **Sforzo:** M
- **Descrizione:** Prima di registrare la differenza come «Riconciliazione», l'app propone le cause probabili: un movimento con lo stesso importo su un altro conto, una spesa senza conto, un import non finito. In Salute dei dati un controllo segnala i conti non riconciliati da più di N giorni (N impostabile), con il link alla riconciliazione.
- **Dipende da:** T11.
- **Origine:** Card 6 e 7.
- **Fatto quando:** la riconciliazione mostra prima i candidati e solo dopo registra la differenza, e un conto fermo da troppo tempo compare tra i controlli.

**Card T13 — Regole di categoria, seconda tornata (F94)**
- **Area:** Transazioni · **Giro:** 2 · **Priorità:** Alta · **Sforzo:** M
- **Descrizione:** Oggi una regola è «descrizione o controparte contiene una parola → categoria». Si aggiungono condizioni (importo uguale, tra, sopra o sotto; entrata o uscita; conto o carta), azioni (tag, controparte pulita come «PAYPAL *NETFLIX 1234» → «Netflix», nota) e una priorità tra le regole quando ne valgono più d'una.
- **Dipende da:** niente.
- **Origine:** F94.
- **Fatto quando:** una regola con condizione sull'importo e azione sul tag si crea da Impostazioni → Regole e viene applicata a un import.

**Card T14 — Transazioni: modelli, «duplica», viste da gestire**
- **Area:** Transazioni · **Giro:** 2 · **Priorità:** Media · **Sforzo:** M
- **Descrizione:** Una transazione si può duplicare e si possono salvare modelli per quelle che si ripetono a mano. Le viste salvate del registro si possono rinominare e riordinare, e una può aprirsi da sola entrando in Transazioni.
- **Dipende da:** niente.
- **Origine:** F66, Card 14.
- **Fatto quando:** «Duplica» crea una transazione già compilata, e dal menu «Viste» sono disponibili rinomina, ordine e vista predefinita.

**Card T16 — Annulla un import intero e registro delle modifiche (F62)**
- **Area:** Importa · **Giro:** 2 · **Priorità:** Media · **Sforzo:** M
- **Descrizione:** Oggi «Annulla» vale un passo per 30 minuti. Ogni import prende un numero e si può annullare per intero anche giorni dopo, togliendo solo i movimenti che ha creato. Un registro tiene traccia di chi ha cambiato cosa.
- **Dipende da:** niente.
- **Origine:** F62.
- **Fatto quando:** un import di una settimana prima si annulla con un clic, e il registro elenca le modifiche con utente e data.

**Card T17 — Flussi: conti piccoli in «Altri», netto e confronto, immagine PNG**
- **Area:** Flussi · **Giro:** 2 · **Priorità:** Bassa · **Sforzo:** M
- **Descrizione:** Con tanti conti, quelli con flussi sotto una soglia finiscono in un pallino «Altri», apribile con un clic. Sotto ogni pallino compare il netto (entrate − uscite ± giroconti) e le frecce del periodo prima sono tratteggiate. Un pulsante salva il grafo come PNG.
- **Dipende da:** niente.
- **Origine:** Card 16, 17 e 18; F67.
- **Fatto quando:** con molti conti il grafo resta leggibile, pallini e frecce mostrano il confronto, e il file scaricato riproduce il grafo visibile.

**Card T18 — Report salvabili (F63)**
- **Area:** Report · **Giro:** 2 · **Priorità:** Media · **Sforzo:** L
- **Descrizione:** Dal costruttore di grafici si salva un report con tipo di grafico, raggruppamento (categoria, gruppo, controparte, conto, mese, tag), periodo relativo o fisso e filtri. Il report salvato diventa una scheda della Dashboard, al posto della «Nuova scheda — TBD».
- **Dipende da:** D14 (libreria dei grafici).
- **Origine:** F63, F91.
- **Fatto quando:** un report salvato si riapre identico e si può aggiungere alla Dashboard come scheda.

**Card T19 — Panoramica Finanziaria e Dashboard: confronto del patrimonio**
- **Area:** Panoramica Finanziaria · **Giro:** 2 · **Priorità:** Media · **Sforzo:** S
- **Descrizione:** «Confronta» copre entrate, uscite e tasso di risparmio ma non il patrimonio netto: va aggiunto il valore alla fine del periodo prima. Poi la revisione a schermo delle pagine della sezione (stato patrimoniale, conto economico, flussi di cassa, crescita, chiusure) con l'elenco di T07.
- **Dipende da:** T03, T07.
- **Origine:** Card 21.
- **Fatto quando:** con «Confronta» attivo anche il patrimonio mostra il periodo prima, e la sezione supera l'elenco «sezione finita».

**Card T20 — Budget proposto dallo storico e revisione di fine mese**
- **Area:** Budget · **Giro:** 2 · **Priorità:** Alta · **Sforzo:** M
- **Descrizione:** «Proponi budget» calcola per ogni categoria la media o la mediana degli ultimi 6 mesi, con l'opzione −5 % o −10 % sulle spese non essenziali; le cifre si accettano tutte o una per una. Il primo del mese arriva un riepilogo del mese passato: categorie sforate e risparmiate, scostamento totale, proposta per il mese nuovo.
- **Dipende da:** niente.
- **Origine:** B1 e B5.
- **Fatto quando:** un budget completo nasce in un clic e si può ritoccare, e la revisione arriva come promemoria e si applica con un clic.

**Card T21 — Budget annuali, per gruppo, per evento, per persona, a buste**
- **Area:** Budget · **Giro:** 2 · **Priorità:** Media · **Sforzo:** L
- **Descrizione:** Le spese che arrivano una o due volte l'anno hanno un budget annuale con il ritmo mensile da accantonare. Un tetto si può dare a un gruppo di spesa o a un evento con la sua durata. In famiglia ogni titolare ha il suo budget oltre a quello comune. Opzione «a buste»: le entrate del mese divise tutte fino a «zero da assegnare».
- **Da decidere:** se il budget a buste serve davvero o resta fuori.
- **Dipende da:** T20.
- **Origine:** B2, B3, B4 e B6.
- **Fatto quando:** una categoria può avere un budget annuale, un gruppo o un evento un tetto, e la pagina filtra per persona.

**Card T22 — Obiettivi collegati a un conto o a un portafoglio; fondo d'emergenza calcolato**
- **Area:** Obiettivi · **Giro:** 2 · **Priorità:** Alta · **Sforzo:** M
- **Descrizione:** Un obiettivo legge l'avanzamento dal saldo di un conto deposito o dal valore di un portafoglio, invece di aggiornarlo a mano. L'obiettivo «emergenza» si calcola da solo: N mesi di spese essenziali (N tra 3 e 12), aggiornato quando le spese cambiano.
- **Dipende da:** niente.
- **Origine:** O1 e O3.
- **Fatto quando:** l'avanzamento si aggiorna con i movimenti, e l'importo del fondo d'emergenza segue le spese reali.

**Card T23 — Obiettivi: ripartizione del risparmio, probabilità, tappe, di famiglia**
- **Area:** Obiettivi · **Giro:** 2 · **Priorità:** Media · **Sforzo:** L
- **Descrizione:** Il risparmio del mese viene diviso tra gli obiettivi per priorità e scadenza, prima l'emergenza. Per un obiettivo finanziato da investimenti, la probabilità di arrivarci entro la data (come già per Pensione e FIRE) e il versamento per arrivare all'80 %. Avvisi al 25, 50, 75 e 100 %, e quando un obiettivo resta fermo 3 mesi. Obiettivi condivisi con la quota di ogni persona.
- **Dipende da:** T22.
- **Origine:** O2, O4, O5 e O6.
- **Fatto quando:** ogni mese c'è una proposta di ripartizione da confermare, l'obiettivo mostra probabilità e versamento consigliato, e le tappe compaiono tra i promemoria.

---

## Giro 3 — Patrimonio

**Card T24 — Debiti: rimborso anticipato e strategia di estinzione**
- **Area:** Debiti · **Giro:** 3 · **Priorità:** Alta · **Sforzo:** M
- **Descrizione:** Per un mutuo o un prestito, cosa succede versando X oggi: rata o durata ridotta, interessi risparmiati, eventuale penale, a confronto con il rendimento atteso investendo gli stessi soldi. Con più debiti e una cifra extra al mese, il confronto tra «prima il tasso più alto» e «prima il saldo più piccolo», con data di fine e interessi risparmiati.
- **Dipende da:** niente.
- **Origine:** D1 e D2.
- **Fatto quando:** entrambe le scelte (rata o durata) mostrano il risparmio netto, e il confronto mostra le due date di estinzione.

**Card T25 — Debiti: surroga, sostenibilità, tasso variabile**
- **Area:** Debiti · **Giro:** 3 · **Priorità:** Media · **Sforzo:** M
- **Descrizione:** Inserita l'offerta di un'altra banca (tasso, spese, durata), il confronto con il mutuo attuale: differenza di rata, di costo totale e mesi per recuperare le spese. Il rapporto tra rate mensili e reddito netto con soglie (sotto il 30 % bene, oltre il 40 % attenzione) e la sua tendenza. Per un tasso variabile, rata e costo con Euribor +1 % e +2 %.
- **Dipende da:** T24.
- **Origine:** D3, D5 e D6.
- **Fatto quando:** l'offerta risulta conveniente o no con il punto di pareggio, la pagina Debiti mostra il rapporto rate/reddito, e gli scenari sono nella pagina del debito.

**Card T26 — Portafoglio, Fase 2: database dei prezzi (★ F92)**
- **Area:** Portafoglio · **Giro:** 3 · **Priorità:** Alta · **Sforzo:** L
- **Descrizione:** Il fondamento di valore nel tempo, rendimenti giornalieri, effetto cambio, Backtest e IPS. Restano: il primo scaricamento delle chiusure da Yahoo (F89), le fonti aperte di riserva e di controllo (F90), i cambi BCE per i titoli non in euro, la cache dei valori giornalieri e TWR/XIRR giornalieri (F47 parte 4).
- **Dipende da:** il lancio dello scaricamento sul tuo PC (Portafoglio → Prezzi → «Scarica da Yahoo»): da qui Yahoo non è raggiungibile.
- **Origine:** F92, F89, F90, F47.
- **Fatto quando:** lo storico è scaricato, i titoli non in euro hanno il cambio del giorno, e i rendimenti giornalieri si aprono senza attesa.

**Card T27 — Registro ordini con prezzi, commissioni e tasse (F45)**
- **Area:** Portafoglio · **Giro:** 3 · **Priorità:** Alta · **Sforzo:** M
- **Descrizione:** Il dettaglio di ogni ordine, uno a uno con la transazione: data e ora, data valuta, mercato, lato, quantità, prezzo, valuta e cambio, commissione (proposta dalle regole del conto titoli), Tobin tax, ritenuta, totale regolato con controllo di quadratura, e il fissato bollato come allegato.
- **Dipende da:** T31 per le aliquote della Tobin tax (prima della verifica restano da scrivere a mano).
- **Origine:** F45.
- **Fatto quando:** un ordine mostra tutte le sue voci e il totale torna al centesimo con il movimento sul conto.

**Card T28 — Costo totale, sovrapposizione tra ETF, «dove metto i prossimi soldi»**
- **Area:** Portafoglio · **Giro:** 3 · **Priorità:** Media · **Sforzo:** M
- **Descrizione:** Una cifra per portafoglio, in euro e in percentuale l'anno: TER dei fondi, commissioni pagate, bollo o IVAFE, con il peso su 10 anni. Dal look-through, quanto due ETF hanno in comune e la vera esposizione alle prime 10 aziende. Dato un importo da investire, come dividerlo per avvicinarsi al modello, solo con acquisti e con le commissioni, da confermare come ordini teorici.
- **Dipende da:** T26 per i prezzi.
- **Origine:** P2, P3 e P4.
- **Fatto quando:** ogni portafoglio mostra il costo annuo, una tabella mostra la sovrapposizione per coppia di fondi, e l'importo diviso diventa ordini con un clic.

**Card T29 — Backtest (F88) e IPS (F85)**
- **Area:** Portafoglio · **Giro:** 3 · **Priorità:** Media · **Sforzo:** L
- **Descrizione:** Backtest, oggi pagina segnaposto: un modello su un periodo passato con versamento iniziale e PAC, ribilanciamento, commissioni, bollo e tasse; valore contro versato e contro un indice. IPS: il documento delle regole d'investimento (obiettivi, orizzonte, rischio accettato, allocazione target, regole di ribilanciamento), che l'app usa per controllare il portafoglio e segnalare gli scostamenti.
- **Da decidere:** questionario del profilo di rischio e un IPS per famiglia o per persona.
- **Dipende da:** T26.
- **Origine:** F88, F85, P7.
- **Fatto quando:** la pagina Backtest non ha più il TBD e mostra un risultato su un modello, e la Panoramica dice se il portafoglio rispetta l'IPS.

**Card T30 — Grafici del catalogo, avvisi di prezzo, titoli da osservare, buoni postali**
- **Area:** Portafoglio · **Giro:** 3 · **Priorità:** Bassa · **Sforzo:** L
- **Descrizione:** I grafici ad alta priorità del catalogo (G37–G41: valore contro versato, heatmap dei rendimenti, drawdown, marcatori di acquisti e vendite, attuale contro target con bande). Avvisi quando un prezzo supera una soglia o scende di oltre X % dal massimo. Una lista di titoli seguiti ma non posseduti. Buoni fruttiferi postali e libretti a valore di rimborso tabellare.
- **Dipende da:** D14 per i grafici che usano plugin; T31 per il bollo dei buoni postali.
- **Origine:** F68, P5, P6, F54.
- **Fatto quando:** i grafici scelti sono nelle pagine del Portafoglio, un avviso compare quando la condizione si verifica, e un buono postale si registra con il suo valore di rimborso.

---

## Giro 4 — Fisco

**Card T31 — F56a: verifica sulle fonti ufficiali**
- **Area:** Fisco · **Giro:** 4 · **Priorità:** Alta · **Sforzo:** M
- **Descrizione:** Prima di qualunque calcolo fiscale nuovo vanno verificati su Agenzia delle Entrate e Normattiva: Tobin tax, bollo titoli, IVAFE «per conto o per rapporto», cumulo dei buoni postali, ETF non armonizzati, costo medio per rapporto. Il risultato è una nota con la regola, la fonte e la data di verifica per ogni punto.
- **Dipende da:** le fonti ufficiali (materiale tuo o ricerca in rete).
- **Origine:** F56a.
- **Fatto quando:** ogni punto ha la regola, il link alla fonte e la data, e i calcoli esistenti che non coincidono sono elencati.

**Card T32 — Zainetto fiscale e riepilogo fiscale del portafoglio**
- **Area:** Fisco · **Giro:** 4 · **Priorità:** Alta · **Sforzo:** L
- **Descrizione:** Le minusvalenze per conto titoli con l'anno di scadenza (si compensano entro 4 anni) e un promemoria a ottobre se una scade a fine anno, con i titoli in guadagno che potrebbero usarla. Un riepilogo annuale per conto titoli: plusvalenze e minusvalenze realizzate, redditi da capitale, ritenute, bollo e IVAFE; per il regime dichiarativo i numeri dei quadri RT, RM e RW. Tutto come stima da confrontare con il prospetto del broker.
- **Dipende da:** T31.
- **Origine:** F56b, P1 e P8.
- **Fatto quando:** il riquadro mostra le minusvalenze per anno di scadenza, il promemoria scatta, e il riepilogo coincide con il prospetto fiscale del broker su un anno di prova.

**Card T33 — «Se vendo oggi» e interessi del mutuo nel 730**
- **Area:** Fisco · **Giro:** 4 · **Priorità:** Media · **Sforzo:** M
- **Descrizione:** Per un titolo o un ordine teorico, prima di confermare: imposta stimata, minusvalenza dello zainetto usata e incasso netto. Gli interessi passivi del mutuo prima casa pagati nell'anno entrano da soli nel riepilogo del 730 (detrazione 19 %, tetto 4.000 €, da verificare con T31).
- **Dipende da:** T31, T32.
- **Origine:** F93, D4.
- **Fatto quando:** l'ordine teorico mostra imposta e netto, e Fisco → 730 mostra gli interessi detraibili dell'anno.

---

## Giro 5 — Sezioni di servizio

**Card T34 — Assicurazioni, Documenti, Istantanee: revisione**
- **Area:** Sezioni di servizio · **Giro:** 5 · **Priorità:** Media · **Sforzo:** M
- **Descrizione:** Revisione a schermo delle tre sezioni con l'elenco di T07: oggi hanno elenco e modulo, senza periodo condiviso, export né modifica nel pop-up. In Documenti, la lettura (OCR) anche dei documenti del broker e degli allegati.
- **Dipende da:** T07.
- **Origine:** badge TBD, F82.
- **Fatto quando:** le tre sezioni superano l'elenco «sezione finita» e il badge TBD è tolto.

**Card T35 — Bollette, Lavoretti, Prestiti tra persone: revisione**
- **Area:** Sezioni di servizio · **Giro:** 5 · **Priorità:** Bassa · **Sforzo:** S
- **Descrizione:** Revisione a schermo delle tre sezioni con l'elenco di T07. Sono pagine singole con elenco e modulo; Bollette ha già consumi, grafico e periodo.
- **Dipende da:** T04, T07.
- **Origine:** badge TBD.
- **Fatto quando:** le tre sezioni superano l'elenco «sezione finita» e il badge TBD è tolto.

**Card T36 — Eventi, Promemoria, Previsioni, Salute dei dati: revisione**
- **Area:** Sezioni di servizio · **Giro:** 5 · **Priorità:** Bassa · **Sforzo:** M
- **Descrizione:** Revisione a schermo delle quattro sezioni con l'elenco di T07. Salute dei dati oggi è una pagina sola: aggiungere un controllo per sezione (conti non riconciliati, prezzi vecchi, budget senza categoria, documenti senza file).
- **Dipende da:** T07, T09.
- **Origine:** badge TBD.
- **Fatto quando:** le quattro sezioni superano l'elenco «sezione finita», il badge TBD è tolto, e Salute dei dati ha almeno un controllo per sezione.

---

## Giro 6 — Piattaforma

**Card T37 — Database cifrato (F84) e dove sta la chiave (D15)**
- **Area:** Sicurezza · **Giro:** 6 · **Priorità:** Alta · **Sforzo:** L
- **Descrizione:** Oggi sono cifrati i backup automatici e il numero delle carte; IBAN, numeri di conto, documenti e note no. Proposta: campi sensibili cifrati dall'app (AES-256-GCM), chiave nel portachiavi del sistema con una copia di sicurezza stampabile; per l'app desktop anche la cartella dati su volume cifrato.
- **Da decidere:** dove sta la chiave, come si recupera se si perde, e l'ordine dei campi da cifrare.
- **Dipende da:** la decisione D15.
- **Origine:** F84, D15.
- **Fatto quando:** nel database e nella cartella dei documenti non ci sono dati personali in chiaro, e il recupero con la copia della chiave è provato.

**Card T38 — Un archivio per utente (F87)**
- **Area:** Archivi · **Giro:** 6 · **Priorità:** Alta · **Sforzo:** L
- **Descrizione:** Ogni utente ha il suo archivio (riusando i database separati dei Clienti); l'archivio di famiglia si condivide se l'amministratore lo assegna a più utenti; il login apre l'archivio dell'utente. Da progettare: migrazione dell'archivio attuale, permessi, promemoria e backup per archivio.
- **Da decidere:** cosa fare dell'archivio attuale (proposta: resta della famiglia).
- **Dipende da:** la tua decisione.
- **Origine:** F87.
- **Fatto quando:** due utenti vedono ciascuno il proprio archivio e, se assegnato, quello di famiglia.

**Card T39 — Archivi: ricerca nel selettore; compressione misurata**
- **Area:** Archivi · **Giro:** 6 · **Priorità:** Bassa · **Sforzo:** S
- **Descrizione:** Con molti archivi il selettore ha un campo di ricerca e mostra per primi quelli usati di recente. La compressione delle pagine, attiva per i browser su un'altra macchina, è stata provata solo su una pagina piccola: va misurata sulle pagine grandi (Categorie, registro).
- **Dipende da:** niente.
- **Origine:** Card 20; analisi di velocità, proposta 9.
- **Fatto quando:** con più di 10 archivi si trova quello giusto scrivendo, e la riduzione di peso sulle pagine grandi è misurata e scritta nel piano.

**Card T40 — Prova con estratti reali e parser dei broker (F4, F55)**
- **Area:** Importa · **Giro:** 6 · **Priorità:** Alta · **Sforzo:** L
- **Descrizione:** I campioni di oggi sono generati: i PDF veri sono il rischio maggiore. Servono estratti reali anonimizzati delle 8 banche e dei broker italiani (Fineco, Directa, Trade Republic, IBKR, Scalable, Revolut) per provare l'import e scrivere un parser per broker, con test sui testi anonimizzati.
- **Dipende da:** i file, che devi fornire tu.
- **Origine:** F4, F55.
- **Fatto quando:** ogni banca e ogni broker ha almeno un file reale che si importa senza correzioni a mano, con il suo test.

**Card T41 — Unire su `main` (D1) e pulizia dei rami**
- **Area:** Repository · **Giro:** 6 · **Priorità:** Alta · **Sforzo:** S
- **Descrizione:** `main` è ancora lo scheletro iniziale: tutto il lavoro è su `test-Cloud` (PR #8, in bozza). Unire la PR e cancellare i rami `Mapping-Excel` e `Dona317-patch-1`, già contenuti in `test-Cloud`. Va fatto dopo T01, perché la storia dei file personali arriverebbe anche su `main`.
- **Dipende da:** una tua richiesta esplicita; T01; T06.
- **Origine:** D1, D2.
- **Fatto quando:** `main` contiene `test-Cloud`, la PR #8 è chiusa e i due rami sono cancellati.

---

## Giro D — Design (in parallelo agli altri giri)

Le card di pulizia decise il 18 nov 2026 (UI-12 in [DESIGN.md](../tecnica/DESIGN.md)): portano le pagine esistenti alle
linee guida di design, in ordine di impatto. Si possono fare tra un giro e l'altro; T42–T44 conviene farle prima delle
revisioni del giro 5. Sono modifiche visive: lint e screenshot con il server demo, i test a fine giro. I numeri di
partenza sono nella sezione 16 di DESIGN.md.

**Card T42 — Colori: il blu solo agli investimenti, niente arancio su KPI e categorie**
- **Area:** Design · **Giro:** D · **Priorità:** Alta · **Sforzo:** S
- **Descrizione:** `--clr-neutral` (oggi blu #1971C2) passa a un grigio-ardesia in tutti e due i temi, così trasferimenti, avvisi «info» e l'icona dei conti non sembrano investimenti (UI-08). I KPI Patrimonio netto e Valore totale del portafoglio passano da arancio a `kpi-neutral` o `kpi-blue`. Categorie con badge neutro e conteggi in testo normale (UI-15).
- **Dipende da:** niente.
- **Origine:** DESIGN.md 2.2, 7.4, 7.5; UI-08, UI-15.
- **Fatto quando:** in Dashboard, Transazioni, Conti e Portafoglio il blu compare solo sugli investimenti e l'arancio solo su azioni e stato attivo, in chiaro e in scuro.

**Card T43 — Telefono: tabelle, Periodo e pulsanti fluttuanti**
- **Area:** Design · **Giro:** D · **Priorità:** Alta · **Sforzo:** M
- **Descrizione:** Sotto i 576px le tabelle mostrano solo data, descrizione e importo e scorrono dentro il riquadro (UI-16); il riquadro «Periodo» non esce dallo schermo; il fondo delle pagine lascia spazio ai pulsanti fluttuanti (+, assistente, torna su), che oggi coprono l'ultima riga e la colonna Importo.
- **Dipende da:** niente; va d'accordo con T10 (menu a hamburger).
- **Origine:** DESIGN.md 6.3, 7.3; UI-16.
- **Fatto quando:** a 375px nessuna pagina del menu ha scorrimento orizzontale della pagina, e l'ultima riga di ogni tabella si legge senza pulsanti sopra.

**Card T44 — Barra e schede: titolo ovunque, massimo 7 schede**
- **Area:** Design · **Giro:** D · **Priorità:** Alta · **Sforzo:** M
- **Descrizione:** Ogni pagina ha titolo e percorso a sinistra nella barra in alto (Transazioni oggi no). Il Portafoglio passa da 13 schede a 7 al massimo, con le altre in «Altro» o in sottosezioni (UI-14); stesso controllo sulle altre pagine con molte schede. I badge «TBD» restano (UI-13).
- **Dipende da:** niente.
- **Origine:** DESIGN.md 6.1; UI-06, UI-14.
- **Fatto quando:** nessuna pagina ha più di 7 schede e tutte mostrano il titolo nella barra.

**Card T45 — Pulsanti e tabelle: un solo arancio pieno, tabelle compatte**
- **Area:** Design · **Giro:** D · **Priorità:** Media · **Sforzo:** S
- **Descrizione:** Dove una vista ha più `btn-primary`, uno solo resta pieno e gli altri diventano `btn-outline` o `btn-ghost` (UI-10). Tutte le tabelle usano la misura compatta (UI-11).
- **Dipende da:** niente.
- **Origine:** DESIGN.md 7.1, 7.3; UI-10, UI-11.
- **Fatto quando:** un conteggio sui template non trova viste con due pulsanti arancio pieni, e nessuna tabella usa la misura larga.

**Card T46 — Testi: maiuscole, spessori, dimensioni, italiano**
- **Area:** Design · **Giro:** D · **Priorità:** Media · **Sforzo:** M
- **Descrizione:** Titoli, pulsanti, schede e menu con la sola prima lettera maiuscola (UI-07), anche nel catalogo inglese; `font-weight` solo 400 e 600 (oggi 55 usi di 700, UI-09); dimensioni del testo solo dalla scala (oggi 15 fuori scala); le etichette inglesi evitabili («Defaults», «Backtest» senza spiegazione) in italiano.
- **Dipende da:** niente.
- **Origine:** DESIGN.md 3, 10; UI-07, UI-09.
- **Fatto quando:** nel CSS e nei template non ci sono 500 o 700 né dimensioni fuori scala (salvo gli 11px del maiuscoletto), e i titoli del menu e delle schede seguono la regola.

**Card T47 — Variabili: spaziature, angoli, larghezze, durate, colori**
- **Area:** Design · **Giro:** D · **Priorità:** Media · **Sforzo:** M
- **Descrizione:** Aggiungere `--space-1…6` e usarle; angoli solo dalle tre variabili più 999px e 50% (oggi 15 valori); larghezze di ridisposizione solo 576, 768, 992, 1200 (oggi 15); durate dalle variabili (oggi 11); i 14 codici colore e le 11 trasparenze di `main.css` in variabili; definire o sostituire `--border` e `--shadow-card-hover`, usate ma non definite.
- **Dipende da:** niente; meglio dopo T42.
- **Origine:** DESIGN.md 4, 5, 6.2, 12.
- **Fatto quando:** lo script di conteggio (sezione 16 di DESIGN.md) dà 0 variabili non definite, 4 larghezze, 5 raggi e nessun codice colore fuori da `theme.css`.

**Card T48 — Stili scritti nei template: da 626 a classi**
- **Area:** Design · **Giro:** D · **Priorità:** Bassa · **Sforzo:** L
- **Descrizione:** Togliere gli `style="…"` dai template, spostandoli in classi di `main.css` o in macro di `partials/`, partendo dai file con più stili (`export/bank_preview.html` 47, `settings/ai.html` 29, `settings/index.html` 29). Si può fare a pezzi, una sezione alla volta, insieme alla sua revisione.
- **Dipende da:** T47 (le variabili da usare nelle classi).
- **Origine:** DESIGN.md 12, 16.
- **Fatto quando:** meno di 50 `style="…"` in tutti i template, solo per valori calcolati (larghezze di barre, colori presi dai dati).
