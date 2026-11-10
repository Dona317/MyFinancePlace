# Test live

Prova l'app come la userebbe una persona: server di produzione (gunicorn, login attivo) su un database
**nuovo**, un browser vero (Chromium via Playwright) e un Ollama finto al posto dei modelli AI. Trova i problemi
che i test unitari non vedono: pagine che escono dallo schermo sul telefono, JavaScript che si rompe, flussi a
più passaggi, formati diversi tra server e browser.

Non gira in CI (serve un browser e dura circa 25 minuti): lancialo prima di un rilascio o dopo un refactor.

## Cosa serve

- PostgreSQL raggiungibile, con un utente che può creare database
- Le dipendenze dell'app (`pip install -r requirements.txt`) più Playwright:
  `pip install playwright && playwright install chromium`
- La porta 5000 (app) e la 11434 (Ollama finto) libere, oppure altre due scelte con `LIVE_PORT` e `FAKE_OLLAMA_PORT`
  (così un Ollama vero acceso può restare, e due giri possono andare insieme con database e `LIVE_OUT` diversi)

## Come si lancia

```sh
sh scripts/live/run.sh
```

Esce con 0 se tutto passa. I log di ogni giro, del server e i file scaricati finiscono in `scripts/live/out/`
(ignorata da git). Anche la cartella `instance` dell'app usata dal test sta lì: documenti e backup veri non
vengono toccati.

| Variabile | Default | A cosa serve |
|---|---|---|
| `LIVE_DATABASE_URL` | `postgresql://sa:Pa55w0rd@localhost:5432/mfp_live` | Database del test: **viene cancellato e ricreato** |
| `LIVE_PORT` | `5000` | Porta dell'app durante il giro (gli script la leggono da `LIVE_URL`, impostato da `run.sh`) |
| `FAKE_OLLAMA_PORT` | `11434` | Porta dell'Ollama finto (l'app la riceve in `OLLAMA_URL`) |
| `LIVE_OUT` | `scripts/live/out` | Cartella di log, sessione, file scaricati e `instance` |
| `LIVE_SHOTS` | — | Cartella dove salvare uno screenshot di ogni pagina (per confrontare due versioni) |
| `LIVE_ASSETS` | — | Se la rete blocca i CDN: cartella con `chart.umd.js` (Chart.js 4.4.3) e `bootstrap-icons/` (il pacchetto `font/` di Bootstrap Icons 1.11.3) |
| `LIVE_CHROMIUM` | — | Percorso di un Chromium già installato |

## I cinque giri

| Script | Controlli | Cosa fa |
|---|---|---|
| `login.py` | 10 | Primo amministratore, login, secondo utente, password sbagliata, logout, API protetta; salva la sessione |
| `flows.py` | 87 | Pagine vuote, modelli AI, gli estratti conto di `samples/bank_statements` in ogni formato, lettura AI solo dopo conferma, anteprima modificabile con classificazione AI, transazioni, duplicati, export e import CSV, report, previsioni, interfaccia |
| `wealth.py` | 20 | Portafoglio e prezzi, debiti, polizze, obiettivi, documenti, stato patrimoniale, istantanee, backup e ripristino |
| `features.py` | 65 | Valute e conti, importi con segno, tag, sottocategorie, divisione, giroconti, budget, esercente dalla causale, CSV senza intestazione, dashboard (Sankey, flusso di cassa, interruttori), categorie e regole, inglese, cambio password, natura delle categorie, autonomia, abbonamenti, OFX/CAMT, giro di tutte le pagine in chiaro/scuro su desktop e telefono |
| `securities.py` | 16 | Conti titoli e portafogli: due broker, operazioni dalla pagina del titolo, posizioni per conto, ribilanciamento in ordini |

Gli script girano in quest'ordine sullo stesso database: ognuno parte dai dati lasciati dal precedente.
Si possono rilanciare uno per uno (`python scripts/live/features.py`) con server e Ollama finto già accesi.

I campi a scelta con molte voci sono «combo»: una casella di testo `#f-x` davanti a un `<select id="f-x-select">`
nascosto. Negli script si sceglie con `choose(pg, selettore, valore | label= | index=)` di `common.py`, non con
`select_option`; le conferme dell'app (moduli con `data-confirm`) si accettano con `confirm(pg)`.
