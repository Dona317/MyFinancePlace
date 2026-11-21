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

## 2. Le due pagine
- **Gestione PSD2** (Impostazioni → Gestione PSD2, o il pulsante in alto in Collegamenti bancari), per tutta l'app:
  le credenziali di Enable Banking, **tutti i collegamenti di tutti gli archivi** (archivio, banca, scadenza del
  consenso, conti abbinati, movimenti da controllare e in attesa alla banca, letture automatiche del giorno su 4),
  «Collega una banca» con la **scelta dell'archivio**, e il **registro degli accessi** (ogni consenso e ogni download,
  a mano o automatico, con esito e numeri, nell'archivio per cui è stato fatto). Chi non è amministratore vede solo il
  proprio archivio.
- **Collegamenti bancari** (scheda di Conti e Carte): i collegamenti dell'archivio aperto, con i conti da abbinare,
  «Aggiorna ora», «Rinnova consenso», «Scollega», le impostazioni e i movimenti in attesa alla banca.

Ogni collegamento (un consenso) appartiene a **un archivio**: sta nel database di quell'archivio, finisce nel suo
backup, e i movimenti vanno nei suoi conti. Un archivio può avere **più collegamenti**, anche alla stessa banca
(conto personale e conto cointestato con accessi diversi, banca privata e business).

## 3. Inserire le credenziali
- **Dall'app**: Gestione PSD2 → riquadro «Applicazione Enable Banking»: ID e file
  `.pem` (o la chiave incollata). Vanno nel file `enable_banking.json` della cartella dei dati, leggibile solo dal suo
  proprietario, con la chiave cifrata dalla chiave dei dati (`field_crypto`). Valgono per tutti gli archivi dei clienti.
- **Dal server**: `ENABLE_BANKING_APP_ID` e `ENABLE_BANKING_KEY_FILE` (percorso del `.pem`); hanno la precedenza e la
  pagina non le modifica.

## 4. Collegare una banca
«Collega una banca» → paese e banca (elenco di Enable Banking) → **Vai alla banca**: l'utente accede all'home banking
e dà il consenso alla sola lettura, valido fino a 180 giorni (meno se la banca lo limita). Al ritorno l'app:
- salva il collegamento (`bank_connections`, con l'id della sessione cifrato) e i conti che copre
  (`bank_account_links`);
- abbina ogni conto della banca a un conto dell'app **per IBAN** (o numero di conto); quelli senza abbinamento si
  scelgono dalla tabella;
- scarica subito i movimenti degli ultimi 90 giorni.

## 5. Come funziona il download
1. Si chiedono i movimenti da una settimana prima dell'ultimo contabilizzato (così non si perdono le contabilizzazioni
   in ritardo); la prima volta, degli ultimi 90 giorni.
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
- **a mano**, con «Aggiorna ora» (con l'utente presente: l'app manda alla banca gli header `Psu-Ip-Address` e
  `Psu-User-Agent`, quindi non conta tra le letture senza l'utente);
- **da solo**, se «Scarica da solo i movimenti» è acceso: al massimo ogni `BANK_SYNC_HOURS` ore (6 di default), quando
  si apre la dashboard (in un thread) e nel giro orario dell'app desktop, per tutti gli archivi. La PSD2 permette
  **quattro letture al giorno** senza l'utente per ogni conto.

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
`BANK_SYNC_HOURS`, `BANK_SYNC_INLINE` (test: download dentro la richiesta).

## 8. Limiti noti
- Provato solo contro un'API finta: **va provato con la sandbox di Enable Banking e con una banca vera** prima di
  contarci.
- Le carte di credito sono lette solo se la banca le espone come conto PSD2 (in Italia Enable Banking ha esteso
  l'accesso ai conti carta nel 2026).
- Un consenso rinnovato riabbina i conti per IBAN (o per nome se la banca non dà l'IBAN).
