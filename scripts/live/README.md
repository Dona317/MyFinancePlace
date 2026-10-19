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
- La porta 5000 (app) e la 11434 (Ollama finto) libere: un Ollama vero acceso va fermato

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
| `LIVE_SHOTS` | — | Cartella dove salvare uno screenshot di ogni pagina (per confrontare due versioni) |
| `LIVE_ASSETS` | — | Se la rete blocca i CDN: cartella con `chart.umd.js` (Chart.js 4.4.3) e `bootstrap-icons/` (il pacchetto `font/` di Bootstrap Icons 1.11.3) |
| `LIVE_CHROMIUM` | — | Percorso di un Chromium già installato |

## I quattro giri

| Script | Controlli | Cosa fa |
|---|---|---|
| `login.py` | 10 | Primo amministratore, login, secondo utente, password sbagliata, logout, API protetta; salva la sessione |
| `flows.py` | 87 | Pagine vuote, modelli AI, gli estratti conto di `samples/bank_statements` in ogni formato, lettura AI solo dopo conferma, anteprima modificabile con classificazione AI, transazioni, duplicati, export e import CSV, report, previsioni, interfaccia |
| `wealth.py` | 20 | Portafoglio e prezzi, debiti, polizze, obiettivi, documenti, stato patrimoniale, istantanee, backup e ripristino |
| `features.py` | 48 | Valute e conti, importi con segno, tag, sottocategorie, giroconti, budget, esercente dalla causale, CSV senza intestazione, dashboard (Sankey, netto, interruttori), categorie e regole, inglese, cambio password, giro di tutte le pagine in chiaro/scuro su desktop e telefono |

Gli script girano in quest'ordine sullo stesso database: ognuno parte dai dati lasciati dal precedente.
Si possono rilanciare uno per uno (`python scripts/live/features.py`) con server e Ollama finto già accesi.
