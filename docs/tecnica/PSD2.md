# Lettura dei movimenti via PSD2 (F107)

MyFinancePlace può scaricare i movimenti direttamente dalla banca, con il consenso PSD2 dell'utente, tramite
l'aggregatore **Enable Banking** (decisione D16, 21 nov 2026). L'import da file resta: le due vie convivono e i
doppioni vengono riconosciuti.

## 1. Cosa serve: un'applicazione Enable Banking
1. Crea un account su [enablebanking.com](https://enablebanking.com) e apri il **Control panel → Applications**.
2. Crea un'applicazione. Il pannello genera una **coppia di chiavi RSA**: scarica il file `.pem` della chiave
   privata (non si può riscaricare) e annota l'**ID dell'applicazione**.
3. Tra i **redirect URL** dell'applicazione registra l'indirizzo che l'app mostra nella pagina Collegamenti bancari:
   di solito `http://127.0.0.1:<porta>/banking/callback` per l'app desktop, `https://<tuo-dominio>/banking/callback`
   sul server. Con `ENABLE_BANKING_REDIRECT_URL` si fissa un indirizzo diverso (per esempio se il pannello non accetta
   `http://` e serve un indirizzo `https` che rimandi all'app). **Da verificare** alla prima prova: se il pannello
   accetta l'indirizzo locale dell'app desktop, che cambia porta a ogni avvio.
4. Modalità: per leggere **i propri conti** basta la modalità ristretta (*restricted production*): si attiva
   collegando i propri conti dal pannello ed è gratuita (da confermare sul listino di Enable Banking al momento della
   registrazione). Per leggere **i conti dei clienti dello studio** serve la produzione piena, con un contratto
   (prezzi su preventivo): è la parte di D16 ancora da decidere.

## 1-bis. Pagina di ritorno https (serve per Production)
In **Production** Enable Banking accetta solo indirizzi di ritorno **https** (`http://localhost…` viene rifiutato con
«uses unsupported scheme»; la Sandbox invece lo accetta). L'app gira sul computer di chi la usa, quindi serve una
**pagina pubblica statica** che riceve il ritorno dalla banca e, nel browser stesso, rimanda subito all'app locale:
`docs/psd2-ritorno/index.html`. Non ha server né dati: legge `state` (che termina con l'indirizzo dell'app,
`localhost:5000` in base64), accetta solo `localhost`/`127.0.0.1` e va su `http://<quello>/banking/callback?…`.
Il codice della banca vale una volta sola ed è inutile senza la chiave privata dell'app. La stessa pagina va bene per
tutti (anche per gli amici).

Pubblicarla gratis con GitHub Pages (una volta):
1. su GitHub crea un repository **pubblico**, per esempio `mfp-ritorno`;
2. «Add file → Upload files»: carica `docs/psd2-ritorno/index.html` (con questo nome) e fai il commit;
3. Settings → Pages → «Deploy from a branch», branch `main`, cartella `/ (root)`, Save; dopo un paio di minuti la
   pagina è su `https://<utente>.github.io/mfp-ritorno/`;
4. registra quell'indirizzo, identico e con la `/` finale, tra i redirect URL dell'applicazione Production;
5. in Gestione PSD2 scrivilo in «Indirizzo di ritorno https (per Production)» e salva.

Se il ritorno non si carica comunque, in Gestione PSD2 → «Bloccato al ritorno dalla banca?» si incolla l'indirizzo
della pagina su cui si è rimasti (contiene `code=` e `state=`) e il collegamento si completa.

## 1-ter. Il ritorno finisce nel browser (22 nov 2026)
Pensato per l'app desktop, che apre la banca nel browser del sistema (Chrome…), dove l'app non ha una sessione: il
consenso in attesa (`state`) è tenuto **nel database dello studio** (`open_banking.pending`, monouso, dimenticato dopo
un'ora), e `/banking/callback` è **pubblica** (protetta dallo `state` casuale e dal codice della banca, inutile senza la
chiave privata). Al ritorno: apre da sola l'archivio in cui il collegamento era partito, completa il consenso, scarica
i movimenti e mostra una **pagina sua** — «collegata, N conti… Puoi chiudere questa scheda e tornare nell'app» — non le
pagine dell'app. Se qualcosa non va, l'errore della banca è su quella pagina (e nel registro degli accessi); se la
banca non indica conti, la pagina spiega la modalità ristretta.

## 2. Dove si fa cosa
- **Si collega dal conto** (deciso il 22 nov 2026, UI-24): Conti e Carte → un conto → **Modifica** → riquadro
  «Collegamento bancario (PSD2)» → **Collega a Enable Banking**. Il conto dell'app esiste sempre prima del
  collegamento, e il conto della banca diventa proprio quello: nessun movimento finisce su un conto non ancora creato.
  Nello stesso riquadro: stato del consenso, ultimo download, saldo della banca, «Controlla N», «Aggiorna ora»,
  «Rinnova consenso» (quando scade) e «Scollega questo conto».
- **Collegamenti bancari** (scheda di Conti e Carte): **solo gestione** dei collegamenti dell'archivio aperto — conti
  abbinati, «Aggiorna ora», «Rinnova consenso», «Scollega» (ritira il consenso), impostazioni, movimenti in attesa
  alla banca. Da qui non si avvia un collegamento.
- **Gestione PSD2** (Impostazioni → Gestione PSD2): per tutta l'app, le credenziali di Enable Banking, **tutti i
  collegamenti di tutti gli archivi** (archivio, banca, scadenza, conti abbinati, da controllare, in attesa alla
  banca, letture automatiche del giorno su 4) e il **registro degli accessi** (ogni consenso e ogni download, a mano o
  automatico, con esito e numeri, nell'archivio per cui è stato fatto). Chi non è amministratore vede solo il proprio
  archivio.

Ogni collegamento (un consenso) appartiene a **un archivio**: sta nel database di quell'archivio, finisce nel suo
backup, e i movimenti vanno nei suoi conti. Un archivio può avere **più collegamenti**, anche alla stessa banca
(conto personale e conto cointestato con accessi diversi, banca privata e business).

## 3. Inserire le credenziali (e come sono protette)
- **Dall'app**: Gestione PSD2 → riquadro «Applicazione Enable Banking»: ID e file `.pem` (o la chiave incollata).
- **Dove finiscono**: nel **database dello studio** (l'archivio principale), tabella `app_settings`, chiave
  `open_banking.credentials`. Il valore è **cifrato per intero**, ID e chiave privata, con AES-256-GCM e la chiave dei
  dati (`field_crypto`, formato `v1:…`): nel database e nei backup c'è solo testo cifrato. Valgono per tutti gli
  archivi dei clienti. Se cambi la chiave dei dati (Esporta → chiave), si cifrano di nuovo come i numeri delle carte.
- **Mai nel browser**: dopo il salvataggio la pagina mostra solo «Configurata» e l'ID; nessuna pagina e nessuna API
  restituisce la chiave. Ogni chiamata a Enable Banking è firmata **sul server** con un JWT di un'ora, e anche quello
  non passa mai dal browser. Gli id delle sessioni bancarie sono cifrati allo stesso modo.
- **Dal server**: `ENABLE_BANKING_APP_ID` e `ENABLE_BANKING_KEY_FILE` (percorso del `.pem`); hanno la precedenza e la
  pagina non le modifica.
- **Limite noto (D15)**: la chiave dei dati sta nella cartella dei dati (`data.key`), oppure in `MFP_DATA_KEY` sul
  server. Chi copia il database o un backup non legge niente; chi ha l'intero computer acceso con l'app sì. Il
  portachiavi del sistema (D15) è il passo successivo.
- Una versione precedente teneva le credenziali nel file `enable_banking.json`: alla prima lettura passano nel
  database e il file viene cancellato.

## 4. Collegare una banca (dal conto)
Nella pagina di modifica del conto: paese e banca (elenco a tendina di Enable Banking) → **Collega a Enable
Banking**: l'utente accede all'home banking e dà il consenso alla sola lettura, valido fino a 180 giorni (meno se la
banca lo limita). Al ritorno l'app:
- salva il collegamento (`bank_connections`, con l'id della sessione cifrato) e i conti che copre
  (`bank_account_links`);
- se la banca ha autorizzato **un solo conto**, o uno con l'IBAN del conto dell'app, quello diventa il conto da cui
  si è partiti; se ne ha autorizzati **più d'uno** e nessuno si riconosce, una pagina chiede «Quale conto della banca è
  «…»?»;
- gli altri conti del consenso restano **autorizzati ma non letti**: dalla pagina di un altro conto compaiono sotto
  «Già autorizzato dalla banca» e si usano con un clic («È questo conto»), senza tornare in banca; quelli con l'IBAN di
  un conto dell'app già esistente vengono abbinati e letti subito;
- scarica subito i movimenti degli ultimi 90 giorni del conto collegato e torna sulla pagina del conto.

**Prova con la sandbox vera di Enable Banking (22 nov 2026): riuscita.** Applicazione Sandbox, banca «Mock ASPSP»
con i dati di esempio caricati dal pannello (scheda Mock ASPSP → Upload): consenso, ritorno su
`http://localhost:5000/banking/callback` (l'indirizzo `http://localhost` è accettato in sandbox), conto e saldo
letti, movimenti scaricati, rivisti e salvati con i tag `importato` e `psd2`. In sviluppo (`python run.py`) gli archivi
dei clienti si aggiornano a mano: `flask --app run db upgrade` e `flask --app run clients migrate`.

## 5. Come funziona il download
1. Si chiedono i movimenti da una settimana prima dell'ultimo contabilizzato (così non si perdono le contabilizzazioni
   in ritardo); la prima volta, degli ultimi 90 giorni.
   Un conto che non ha mai avuto un movimento contabilizzato riparte da una settimana prima dell'ultimo download
   riuscito, non di nuovo dai 90 giorni; mai più indietro di 90 giorni, mai da una data futura (25 nov 2026).
   **Periodo rifiutato** (`WRONG_TRANSACTIONS_PERIOD`): subito dopo il consenso la banca dà tutto lo storico, poi
   solo un periodo più corto (Intesa Sanpaolo, 22 nov 2026: 90 giorni rifiutati circa 40 minuti dopo il consenso).
   L'app riprova da sola da 89 e poi da 30 giorni prima (`SHORTER_DAYS`).
   **Un conto in errore non ferma gli altri** dello stesso consenso: l'errore resta sul collegamento col nome del
   conto (quando sono più di uno) e gli altri si scaricano.
2. Solo i movimenti **contabilizzati** (`BOOK`) diventano transazioni. Quelli **in attesa** (`PDNG`: pagamenti con
   carta non ancora addebitati, preautorizzazioni di hotel e distributori) si mostrano in «In attesa alla banca» e
   non si salvano: tornano contabilizzati a un download successivo, spesso con un altro id e a volte con un altro
   importo, e salvarli prima creerebbe doppioni.
   Se la banca manda il **codice MCC** dell'esercente (pagamenti con carta), diventa un indizio per la categoria
   (supermercati, carburanti, ristoranti, viaggi, salute…), usato quando la descrizione non basta.
3. Ogni movimento passa dagli stessi passi dell'import da file (`bank_import.enrich`): tipo, categoria, esercente,
   giroconti tra conti propri, prelievi verso Contanti, movimenti simili a quelli già salvati.
4. L'**`import_ref`** è l'id che la banca dà al movimento (`entry_reference` / `transaction_id`): scaricato di nuovo
   viene riconosciuto anche se il testo cambia. Se la banca non lo dà, si usa l'impronta solita (data, importo, testo).
5. Poi, per ogni conto:
   - con **«Salva da solo i movimenti nuovi»** acceso e un conto dell'app scelto, si salvano i movimenti che non
     somigliano a niente di già salvato (tag `psd2`, `importato`);
   - tutti gli altri restano **da controllare**: «Controlla N» li apre nell'anteprima dell'import, dove si modificano
     e si salvano come sempre. Quelli tolti dall'anteprima vengono ricordati e non tornano.
6. Si legge anche il saldo della banca, mostrato accanto al conto.

Il download parte:
- **all'apertura dell'app** (dal 22 nov 2026): la prima pagina di una visita legge in background tutti i collegamenti
  attivi dell'archivio, con l'utente presente (header `Psu-*`: non conta tra le quattro letture al giorno senza
  l'utente); al massimo una volta all'ora per browser, e salta un collegamento letto da meno di 30 minuti. Nel
  registro degli accessi è «Apertura app»;
- **a mano**, con «Aggiorna ora» (con l'utente presente: l'app manda alla banca gli header `Psu-Ip-Address` e
  `Psu-User-Agent`, quindi non conta tra le letture senza l'utente);
- **da solo**, se «Scarica da solo i movimenti» è acceso: **fino a 4 volte al giorno, tutte tra le 8 e le 24** (ora
  del computer), cioè nelle ore in cui l'app si usa. La fascia è divisa in quattro parti, che iniziano alle **8, 12, 16 e
  20**, con una lettura per parte. Parte all'apertura della dashboard (in un thread) e nel giro orario dell'app
  desktop, per tutti gli archivi. Una lettura fatta a mano dentro una fascia la copre. Il registro conta le letture
  automatiche del giorno, che non superano mai 4: la PSD2 ne permette **quattro al giorno** senza l'utente per ogni
  conto. Configurabile con `BANK_SYNC_WINDOW` (default `(8, 24)`) e `BANK_SYNC_PER_DAY` (default 4, mai di più).

## 5-bis. Il conto segue il saldo della banca (22 nov 2026)

A ogni lettura l'app chiede anche il saldo del conto. Se è un saldo **contabile** (`CLBD` o `ITBD`, senza i movimenti
non ancora contabilizzati) nella valuta del conto, lo confronta con il saldo che l'app calcola per lo stesso giorno:

- **la prima volta**, se tutti i movimenti del conto sono arrivati dal collegamento (la storia parte dalla prima
  lettura), la differenza va nel **saldo iniziale** del conto: sono i soldi che c'erano prima della storia letta, e così
  anche i saldi dei giorni passati tornano giusti;
- **le volte dopo** (o se il conto ha movimenti importati in altri modi) la differenza diventa un movimento
  **«Riconciliazione»** in quel giorno, escluso dalle analisi (come la riconciliazione fatta a mano);
- le transazioni non vengono toccate: quelle importate e poi modificate restano come le hai lasciate;
- niente allineamento mentre ci sono movimenti del conto **in attesa** nell'anteprima (il saldo della banca li conta già)
  o quando la banca dà solo un saldo disponibile.

Il messaggio della lettura lo dice: «saldo allineato alla banca (differenza +…)».

## 6. Promemoria
Nella campanella (e nelle notifiche di sistema dell'app desktop): consenso che scade entro 14 giorni o scaduto,
download non riuscito, movimenti da controllare, conto della banca senza conto dell'app.

## 7. Dove sta il codice
| Cosa | Dove |
|---|---|
| Client dell'API (JWT RS256 firmato con `cryptography`, urllib) | `app/services/open_banking/client.py` |
| Credenziali dell'applicazione | `app/services/open_banking/credentials.py` |
| Consenso, download, revisione, giro automatico | `app/services/open_banking/sync.py` |
| Tabelle | `app/models/bank_link.py` (`bank_connections`, `bank_account_links`, `bank_access_log`), migrazione `d8e0f2a4b6c9`; nel backup dell'archivio |
| Pagina | `app/routes/banking.py`, `app/templates/banking/index.html` |
| Test (API finta) | `tests/test_open_banking.py` |

Configurazione: `ENABLE_BANKING_API_URL` (default `https://api.enablebanking.com`), `ENABLE_BANKING_REDIRECT_URL`,
`BANK_SYNC_WINDOW`, `BANK_SYNC_PER_DAY`, `BANK_SYNC_INLINE` (test: download dentro la richiesta).

## 8. Limiti noti
- Provato con la sandbox di Enable Banking (22 nov 2026); **manca la prova con una banca vera** (applicazione
  Production in modalità ristretta, con i propri conti collegati dal pannello).
- L'app desktop parte su una porta che cambia: per l'indirizzo di ritorno serve una porta fissa o
  `ENABLE_BANKING_REDIRECT_URL`.
- Le carte di credito sono lette solo se la banca le espone come conto PSD2 (in Italia Enable Banking ha esteso
  l'accesso ai conti carta nel 2026).
- Un consenso rinnovato riabbina i conti per IBAN (o per nome se la banca non dà l'IBAN).
