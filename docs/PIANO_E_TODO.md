# Piano e TODO — MyFinancePlace

Unico punto di controllo di cosa fare dopo. Complementa (non sostituisce) [ROADMAP](../ROADMAP.md) (stato
delle sezioni), [NEXT_STEPS](NEXT_STEPS.md) (cronologia tecnica) e [ANALISI_COMPETITOR](ANALISI_COMPETITOR.md).

**Ultimo aggiornamento**: 10 ottobre 2026 · **Ramo**: `test-Cloud` (PR #8, in bozza) ·
**MVP**: completo · **Test**: 732, copertura 96,6% · **Migrazioni**: 24

| Stato | Significato |
|---|---|
| ⬜ | da fare |
| 🔄 | in corso |
| ✅ | fatto |
| ⏸ | in attesa di una decisione |
| ❌ | scartato |

---

## 1. Scansione dello stato (7 ott 2026)

> **Versione attuale (10 ott 2026): il ramo `test-Cloud` @ `df54fec`**, con CI verde (test + app desktop
> Windows/macOS/Linux) e test live verdi. Dopo il 7 ottobre ha aggiunto: refactoring «clean code», efficienza
> (meno query, niente CDN), font inclusi e selezionabili, F14 (notifiche di sistema, avvio automatico,
> installatore Windows), F18 (sezioni per utente). `main` resta indietro fino all'unione della PR #8 (D1,
> rimandata a novembre).

- `test-Cloud` ha tutto l'MVP: dati reali, report, import 8 banche + generico, AI locale/Claude, conti e valute,
  budget, obiettivi, portafoglio, debiti, assicurazioni, backup, login, IT/EN, Docker, CI. 17 migrazioni.
- `main` è ancora lo scheletro con numeri finti: **finché la PR #8 non è unita, `main` non rappresenta l'app**.
- `origin/Mapping-Excel` non ha commit che `test-Cloud` non abbia già (0 avanti) → le "misure più compatte"
  vanno recuperate a mano, se servono (vedi D2).
- Nessun file `LICENSE` nel repo.
- I dati sono condivisi tra utenti (nessun `user_id` nei modelli).
- Scoperti documenti disallineati, da correggere (vedi sezione 4):
  - `ANALISI_COMPETITOR.md` mette il Sankey tra le cose mancanti: **è già fatto**; la decisione 1 (partita
    doppia) è **già presa** (scartata).
  - `MVP.md` / `NEXT_STEPS.md`: coerenti con il codice, ma "Da fare: niente" non cita i punti di questo file.

---

## 2. Decisioni aperte (servono a te)

| # | Decisione | Stato | Perché blocca |
|---|---|---|---|
| D1 | Unire la PR [#8](https://github.com/Dona317/MyFinancePlace/pull/8) su `main` (verde, senza conflitti; è in bozza) | ⏸ se ne parla a novembre 2026 | `main` resta finto finché non si unisce; ogni nuovo ramo parte da qui |
| D2 | Applicare le misure compatte di `Mapping-Excel`? (ramo senza commit propri: da rifare a mano) | ⏸ | solo estetica, non blocca |
| D3 | ✅ Forma dell'app: **eseguibile desktop** (deciso il 7 ott 2026) | ✅ | apre F16 (confezionamento); F12 (PWA) cade; F11 (dati per utente) poco utile su un PC personale |
| D4 | ✅ Licenza: **proprietaria**, tutti i diritti riservati (deciso l'8 ott 2026) | ✅ | file `LICENSE` (M2) |
| D5 | ✅ Fisco italiano: **sì, completo** (deciso l'8 ott 2026) | ✅ | F15 entra nel piano |
| D7 | ✅ Database dell'eseguibile: **PostgreSQL incorporato** (deciso l'8 ott 2026) | ✅ | F16 parte; nessuna riscrittura per SQLite |
| D6 | ❌ Partita doppia | ❌ | già scartata (ROADMAP → Scartato) |

Resta aperta solo D1 (novembre). Uso deciso l'8 ott 2026: **l'app la usa una persona sola per gestire più clienti, ognuno con il proprio archivio** (F11).

---

## 3. Backlog funzionalità

Priorità: **A** = alta (poco lavoro, grande effetto, ce l'hanno tutti i concorrenti) · **M** = media · **B** = bassa/dopo.
Sforzo: S (≤ 1 giorno) · M (2–4 giorni) · L (oltre).

### Prossimo giro (candidati naturali)

| ID | Pri | Sforzo | Stato | Funzione | Note |
|---|---|---|---|---|---|
| F1 | A | L | ✅ | **Transazioni suddivise** su più categorie | «Suddividi» nel modulo; tabella `transaction_splits`; ogni somma per categoria conta le parti; API, export e backup inclusi |
| F2 | A | M | ✅ | **Tabella Riepilogo** categoria × mese con heatmap | Report → Riepilogo: sottocategorie, totale, media, Δ% sull'anno prima, netto e tasso di risparmio; ogni cella apre le transazioni; CSV |
| F3 | A | S | ✅ | **Tasso di risparmio** mese per mese + confronto anno precedente | Dashboard: card «Tasso di risparmio mese per mese» con tutti gli anni, l'utente sceglie quali confrontare (interruttore in Impostazioni); riga nel Riepilogo con F2 |

### Dati e qualità

| ID | Pri | Sforzo | Stato | Funzione | Note |
|---|---|---|---|---|---|
| F4 | A | M | ⬜ | **Prova con estratti conto reali anonimizzati** (8 banche) | Campioni oggi generati; PDF a maggior rischio. Serve che tu fornisca i file |
| F5 | M | M | ✅ | **Storico prezzi investimenti** (+ prezzi automatici ETF/cripto) | `holding_prices`: Portafoglio → Storico prezzi (uno o più prezzi incollati, grafico), «Aggiorna prezzi» con data; stati patrimoniali, andamento e istantanee usano il prezzo di allora. Prezzi automatici rimandati a F16 (serve una fonte esterna) |
| F6 | M | M | ✅ | **Import OFX / QIF / CAMT.053** | `structured_statements.py` (solo libreria standard): OFX 1 SGML e 2 XML, QIF con categorie e giroconti, CAMT.053/052 con quadratura dei saldi e movimenti in attesa esclusi; stessa anteprima, categorie e duplicati degli altri estratti; 4 campioni |
| F17 | A | M | ✅ | **Commissioni del broker e operazioni in quote** | Sul conto: fisso + % con minimo e massimo. Nel modulo: quote × prezzo → importo; commissione proposta dalle regole (modificabile) e, confermata, salvata come spesa «Commissioni» collegata; posizione aggiornata (quantità, prezzo medio con commissione, prezzo nello storico). L'operazione è un movimento verso/da l'investimento, non una spesa. Tutto facoltativo |
| F5b | M | S | ✅ | **Prezzi da internet** (Yahoo Finance per ETF/azioni, CoinGecko per cripto, gratis e senza chiave) | Pulsante in «Aggiorna prezzi», attivabile in Impostazioni; manda solo i ticker; finisce nello storico di F5 |

### Budget e analisi

| ID | Pri | Sforzo | Stato | Funzione | Note |
|---|---|---|---|---|---|
| F7 | M | M | ✅ | **Riporto del budget** al mese dopo + accantonamento per spese annuali | Budget → «Riporta»: avanzo o sforamento passano al mese dopo, dal mese in cui lo accendi; «Da accantonare»: per le categorie non mensili (F8) 1/12 degli ultimi 12 mesi, un clic lo imposta come budget con riporto |
| F8 | M | S | ✅ | **Categorie fisse / non mensili / variabili** | Natura in Impostazioni → Categorie (le sottocategorie ereditano); Spese e tendenze: barra fisse/non mensili/variabili e quota comprimibile; pallino nel Riepilogo |
| F9 | M | S | ✅ | **Pagina Abbonamenti** | Previsioni → Abbonamenti: confermati e rilevati, costo mensile/annuo, prossimo addebito, aumenti di prezzo; Conferma, «Non più attivo» / Riattiva; scheda entrate ricorrenti |
| F10a | M | S | ✅ | **Mesi di autonomia** (liquidità ÷ spesa media) | Dashboard → Salute finanziaria: media degli ultimi 12 mesi completi (almeno 3), anche solo spese fisse e non mensili (F8); obiettivo 3/6/9/12 mesi in Impostazioni |
| F10b | B | S | ✅ | **Stabilità delle entrate per fonte** | Previsioni → pannello «Stabilità delle entrate»: per fonte mesi presenti su 12, media, variazione, quota; stabile / variabile / occasionale e quota delle entrate stabili |
| F10c | B | M | ⬜ | Heatmap giornaliera a calendario; analisi libera per tag | |

### Piattaforma e usabilità

| ID | Pri | Sforzo | Stato | Funzione | Note |
|---|---|---|---|---|---|
| F11 | A | L | ✅ | **Studio: più clienti, un archivio per cliente** | Un database «studio» (utenti, elenco clienti) + un database PostgreSQL per cliente, con i suoi documenti e backup; cliente attivo scelto dopo l'accesso e sempre visibile in alto; nuovo / apri / esporta / elimina (con backup prima). I clienti non accedono. Il database di oggi diventa il primo cliente |
| F12 | — | — | ❌ | PWA installabile sul telefono | Scartata con D3 = desktop |
| F16 | A | L | ✅ | **Eseguibile desktop** (D3, D7) | Finestra pywebview sul server locale (waitress), PostgreSQL 16 portabile incluso e avviato dall'app, dati nella cartella utente, migrazioni all'avvio, login con password. Build Windows/macOS/Linux su GitHub Actions con prova di avvio. Vedi [DESKTOP](DESKTOP.md). Da fare poi: icona, firma del codice, installer, aggiornamento automatico |
| F13 | B | M | ✅ | Inserimento rapido da tastiera, annulla/ripeti | Transazioni: riga d'inserimento rapido («n» per andarci, Invio per salvare; categoria e controparte indovinate); barra Annulla/Ripeti (Ctrl+Z / Ctrl+Y) per l'ultima aggiunta o eliminazione, anche multipla, per 30 minuti |
| F14 | B | M | ✅ | **Notifiche di Windows e avvio automatico** (invece delle email) | Promemoria del campanello di tutti i clienti come notifiche del sistema: all'avvio arrivano quelli non letti anche dei giorni passati, poi ogni ora; una volta al giorno finché non letti; clic → l'app su quel cliente. Avvio all'accensione (installatore e Impostazioni → App desktop), in background con l'icona vicino all'orologio. Installatore Windows (Inno Setup) costruito e provato dalla CI. Vedi [DESKTOP](DESKTOP.md) |
| F18 | A | M | ✅ | **Sezioni visibili per utente** | L'amministratore blocca sezioni a un utente (Impostazioni → Account e utenti → Sezioni): spariscono dal menu, le pagine e l'API rispondono «accesso negato», niente promemoria né schede della dashboard che le riguardano. Ogni utente nasconde dal proprio menu ciò che non gli serve (Impostazioni → Il mio menu). Gli interruttori di Impostazioni → Moduli valgono ancora per tutti; gli amministratori vedono sempre tutto |
| F15 | A | L | ✅ | **Fisco italiano** (D5) | Modulo *Fisco* con tre schede. **730**: le spese delle categorie collegate a ogni voce del quadro E (sanitarie, veterinarie, istruzione, università, interessi mutuo, assicurazioni, sport, trasporto, asilo, affitti studenti, funebri, erogazioni, previdenza complementare, colf) con franchigie, massimali per anno (istruzione 800 → 1.000 € dal 2025), detrazione stimata, pagamenti in contanti segnalati, spese con tag «detraibile» da assegnare, CSV. **Plusvalenze**: costo medio ponderato con commissioni, redditi di capitale (ETF, fondi) e diversi, minusvalenze compensate per 4 anni (titoli di Stato 12,5% con peso 48,08%, cripto a parte), 26%/12,5%/cripto 33% dal 2026, per broker (amministrato) o in dichiarazione (riepilogo quadro RT). **Bollo e IVAFE**: conti correnti 34,20 € oltre 5.000 € di giacenza media (calcolata giorno per giorno), conti deposito e titoli 2‰ a fine anno, IVAFE all'estero, IC per le cripto in wallet. Da fare poi: tetto detrazioni per redditi > 75.000 €, quadro RM, pro rata del bollo |
| F19 | A | L | ✅ | **Investimenti** | **Fatto (F19a)**: titolo con ISIN, valuta, borsa, moltiplicatore (derivati) e fonte del prezzo; prezzi letti da soli una volta al giorno (web: alla prima visita del giorno; desktop: per tutti i clienti). **Fatto (F19a-bis)**: ricerca per ISIN e prezzi da cinque siti scelti e ordinati in Impostazioni → Fonti dei prezzi — Yahoo Finance (azioni, ETF, derivati, storico), OpenFIGI (da ISIN a ticker e borsa), justETF (ETF europei, prezzo in euro), Borsa Italiana (BTP e obbligazioni del MOT, prezzo in % del nominale: la quantità di un'obbligazione è il nominale), Morningstar (NAV dei fondi; attiva come le altre, la più esposta ai cambi di pagina); Stooq e CoinGecko restano. Si invia solo l'ISIN, al massimo una richiesta al secondo per sito, ricerche salvate per un mese; se un sito cambia pagina quella fonte dà «la pagina è cambiata» e le altre continuano. Le pagine reali di justETF, Borsa Italiana e Morningstar vanno provate sul computer dell'utente (dalla sandbox di sviluppo sono bloccate): i test usano pagine d'esempio con la stessa struttura. **Fatto (F19b)**: pagina del titolo con le operazioni (acquisto, vendita, dividendo, cedola, commissione, imposta); la posizione si ricalcola dalla posizione iniziale e dalle operazioni a ogni creazione, modifica o cancellazione; guadagno realizzato e non realizzato, dividendi e cedole, rendimento annuo (XIRR). **Fatto (F19c)**: Portafoglio → «Importa dal broker» legge l'estratto di Degiro o un CSV/Excel qualunque (colonne riconosciute dal titolo), mostra un'anteprima con il titolo trovato per ISIN, ticker o nome (o «nuovo titolo»), crea operazioni, commissioni e titoli mancanti; reimportare lo stesso file non crea doppioni; le obbligazioni quotate in % del nominale vengono convertite. Sulla pagina del titolo «Collega movimenti del conto» trasforma in operazioni i movimenti del conto corrente (categoria Investimenti o con ISIN, ticker o nome nella descrizione); all'import dell'estratto conto una causale con l'ISIN di un titolo posseduto va in Investimenti. File d'esempio in `samples/dati_fittizi/broker/`. **Fatto (F19d)**: Portafoglio → «Portafoglio modello»: modelli con parti e pesi obiettivo (totale 100 %) e una tolleranza in punti; un titolo conta in una parte se scelto lì, o per ISIN, ticker o classe; quelli in nessuna parte sono «fuori dal modello». Un modello è attivo: la pagina Ribilanciamento mostra peso attuale, obiettivo e scostamento, e quanto comprare o vendere (in euro e quote) in due modalità: solo con nuovi versamenti (solo acquisti) o completa. Modelli pronti da copiare, come esempi con ETF quotati a Milano: tutto azionario, 80/20, 60/40, 30/70, Permanent Portfolio, All Weather, three-fund. I modelli entrano nel backup. **Fatto (F19e)**: Portafoglio → «Regole e PAC»: regole di scostamento dal modello, calo dal prezzo medio, prezzo sopra o sotto una soglia, peso di un titolo oltre una percentuale; quando scattano compaiono tra i promemoria (e come notifica dell'app desktop), e un avviso nascosto torna solo con un prezzo nuovo. PAC mensili o trimestrali: nel giorno scelto un promemoria porta alla conferma, che divide l'importo secondo il portafoglio modello ai prezzi più recenti (quote intere o frazionarie, modificabili) e registra gli acquisti con le commissioni del conto. Dati demo: modello 80/20 attivo, PAC da 250 € e due regole. F19 completo |
| F20 | A | L | 🔄 | **Funzioni ispirate a Wealthfolio** (gap analysis del 13 ottobre) | **Fatto (F20a)**: Strumenti → «Salute dei dati»: titoli con quantità negativa, valute senza cambi (questi due anche tra i promemoria), prezzi più vecchi di 7 giorni, giroconti con un solo conto, possibili doppioni, movimenti senza categoria, titoli senza ISIN né ticker, conti da riconciliare; ognuno con il link per sistemarlo. **Da fare**: F20b eventi di spesa, F20c rendite, F20d debito legato a un bene, F20e analisi della spesa, F20f intestatario, F20g crescita del patrimonio, F20h TWR e benchmark, F20i pensione/FIRE e obiettivi, F20j frazionamenti e composizione, F20k assistente sui dati |

Esclusi per scelta: collegamento automatico alle banche, budget "a buste", partita doppia.

---

## 4. Manutenzione documenti e igiene

| ID | Stato | Cosa |
|---|---|---|
| M1 | ✅ | Aggiornare `ANALISI_COMPETITOR.md`: Sankey fatto; decisione 1 chiusa (scartata) — aggiornato l'8 ott 2026 con tutte le F fatte |
| M2 | ✅ | `LICENSE` proprietario (D4) |
| M3 | ✅ | Rimandare da `MVP.md` ("Dopo l'MVP") e `NEXT_STEPS.md` ("To do") a questo file, per non avere tre liste |
| M4 | ⬜ | Rendere `.claude/` e `.vscode/` ignorati o committati (oggi non tracciati) |
| M6 | ✅ | Collaudo con input impropri (8 ott 2026): ~6.000 invii ostili su tutti i moduli (testi enormi, XSS, SQL, NUL, numeri e date assurde, id inesistenti) + API JSON + file ostili (binari, XXE, zip bomb, backup corrotti). Corretti: CSV illeggibile → messaggio invece di errore 500; caratteri NUL rifiutati/tolti; richieste da altri siti (CSRF) rifiutate controllando Origin/Referer. Nessun XSS, nessuna risposta lenta. Regressioni in `tests/test_robustness.py` |
| M5 | ⬜ | Ripetere la prova di test e copertura in locale (nel venv del progetto; l'interprete usato in questa scansione non ha pytest) |

---

## 5. Come tenerlo in check

1. **Una voce = un ID** (D*, F*, M*). Nei commit e nelle PR si cita l'ID (`F2: tabella Riepilogo`).
2. **Quando una voce cambia stato**, si aggiorna qui **nello stesso commit** del codice, e si aggiunge la riga
   in [NEXT_STEPS.md](NEXT_STEPS.md) → ✅ Done e, se è una sezione dell'app, in [ROADMAP.md](../ROADMAP.md).
3. **Definition of Done** di una funzione: migrazione (se serve) + test + traduzione EN (`scripts/translations.py`)
   + `scripts/untested_functions.py` pulito + CI verde.
4. **Una decisione presa** si sposta da §2 a ROADMAP → Scartato / NEXT_STEPS, con la data.
5. **Revisione**: a ogni merge su `test-Cloud` si rilegge §2 e §3; si cambia la data in testa.
6. Max 1–2 voci 🔄 alla volta.

## 6. Proposta di ordine (aggiornata l'8 ott 2026)

1. ✅ **F11** studio con più clienti (pagina Clienti, `flask clients list|create|migrate`).
2. ✅ **F16** eseguibile desktop con PostgreSQL incorporato ([DESKTOP](DESKTOP.md)).
3. ✅ **F15** fisco: 730, plusvalenze, bollo e IVAFE.
4. ✅ F14 notifiche di Windows, avvio automatico, installatore.
5. F10c (heatmap a calendario, analisi per tag).
6. D1 (unire su `main`) a novembre 2026.
