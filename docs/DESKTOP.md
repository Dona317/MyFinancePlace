# App desktop (F16)

MyFinancePlace come programma da installare sul proprio computer: una finestra sull'app, con un **PostgreSQL
tutto suo** (D7), senza installare nient'altro.

## Scaricare

Ogni push su GitHub costruisce l'app per tre sistemi (workflow **Desktop app**). Nella pagina dell'esecuzione, in
fondo, sotto *Artifacts*:

| File | Sistema |
|---|---|
| `MyFinancePlace-windows-x64` | Windows 10/11 a 64 bit |
| `MyFinancePlace-macos-arm64` | Mac con Apple Silicon (M1 o successivi) |
| `MyFinancePlace-linux-x64` | Linux a 64 bit |

Si scarica uno zip: lo si estrae dove si vuole (es. `Documenti\MyFinancePlace`) e si avvia **MyFinancePlace**
(`MyFinancePlace.exe` su Windows, `MyFinancePlace.app` su Mac).

**Windows, con l'installatore** (`MyFinancePlace-Setup-windows-x64` → `MyFinancePlace-Setup.exe`): installa solo per
l'utente, senza permessi di amministratore, in `%LOCALAPPDATA%\Programs\MyFinancePlace`. Mette l'app nel menu Start
(serve anche alle notifiche, che così mostrano nome e icona dell'app) e chiede se **avviarla all'accensione del
computer**; facoltativa l'icona sul desktop. Per aggiornare si rilancia l'installatore: chiude l'app aperta e
sostituisce il programma, i dati restano. Disinstallando (Impostazioni di Windows → App) si tolgono programma, avvio
automatico e collegamenti; i dati in `%APPDATA%\MyFinancePlace` restano.

Il programma non è firmato con un certificato a pagamento, quindi al primo avvio:
- **Windows**: «Windows ha protetto il PC» → *Ulteriori informazioni* → *Esegui comunque*.
- **macOS**: tasto destro su `MyFinancePlace.app` → *Apri* → *Apri*. Se dice che è danneggiata (succede ai file
  scaricati da internet): `xattr -dr com.apple.quarantine MyFinancePlace.app` nel Terminale, poi di nuovo *Apri*.
- **Linux**: la finestra nativa richiede GTK (`python3-gi`); senza, l'app si apre nel browser.

## Primo avvio

1. L'app prepara il database nella cartella dei dati (qualche secondo, solo la prima volta).
2. Chiede di creare l'utente e la password: proteggono i dati dei clienti.
3. Da *Clienti* si creano gli archivi dei clienti (F11).

Gli avvii successivi richiedono circa 2 secondi.

## In background, avvio automatico e notifiche (F14)

- **Windows**: chiudendo la finestra l'app resta aperta in background, con l'icona vicino all'orologio. Clic
  sull'icona (o «Apri MyFinancePlace») riapre la finestra; «Esci» chiude tutto (server e database). Su macOS e Linux
  chiudendo la finestra si ferma l'app, come prima.
- **Avvio all'accensione**: dall'installatore o da *Impostazioni → App desktop*. L'app parte in background (Windows:
  solo l'icona; macOS e Linux: con la finestra).
- **Notifiche del sistema** (*Impostazioni → App desktop*, accese di base): i promemoria del campanello (polizze in
  scadenza, rate, spese ricorrenti, budget, obiettivi) di **tutti gli archivi dei clienti**, con il nome del cliente
  quando ce n'è più di uno. Venti secondi dopo l'avvio arrivano quelli non letti, anche dei giorni in cui l'app era
  chiusa; poi un controllo ogni ora. Ognuno si ripete una volta al giorno finché non lo segni come visto in
  *Notifiche*; se sono più di tre, ne arrivano due più «Altri N promemoria». Clic sulla notifica (Windows): l'app si
  apre su quel cliente e su quella pagina.
- Come: Windows 10/11 con le notifiche native (PowerShell e le API di Windows, niente da installare), macOS con
  `osascript`, Linux con `notify-send`. Le scelte stanno in `desktop.json` nella cartella dei dati.

## Dove sono i dati

| Sistema | Cartella |
|---|---|
| Windows | `%APPDATA%\MyFinancePlace` |
| macOS | `~/Library/Application Support/MyFinancePlace` |
| Linux | `~/.local/share/MyFinancePlace` |

Dentro: `pgdata/` (il database: studio e archivi dei clienti), `instance/` (documenti, backup; un clienti per
cartella in `instance/clients/`), `logs/` (registro dell'app e del database), `secret_key` e `pg_password`
(generati al primo avvio). Aggiornare l'app = sostituire la cartella del programma: i dati restano. Le migrazioni
del database (studio e clienti) si applicano da sole all'avvio.

Opzioni da riga di comando: `--data-dir CARTELLA` (dati altrove, es. su un disco cifrato), `--browser` (nel
browser invece che nella finestra), `--background` (senza finestra: icona e notifiche; è come parte all'accensione),
`--headless` (solo server, stampa l'indirizzo), `--stop` (chiude l'app aperta: usato dall'installatore), `--smoke`
(avvia, controlla e chiude: usato dalla build).

## Come è fatto

- `desktop/main.py`: cartella dati → PostgreSQL locale → migrazioni → server waitress su `127.0.0.1` (porta
  libera) → finestra pywebview, icona e promemoria. Un secondo avvio (o un clic su una notifica, link
  `myfinanceplace://`) chiede all'app aperta di mostrare la finestra: `running.json` nella cartella dei dati contiene
  indirizzo e un codice segreto che solo l'utente può leggere.
- `desktop/notify.py`, `desktop/tray.py`, `desktop/windows.py` (nome e icona delle notifiche, link `myfinanceplace://`,
  scritti per l'utente a ogni avvio), `app/services/autostart.py`, `app/services/system_notifications.py`.
- `desktop/installer.iss`: l'installatore Windows (Inno Setup), costruito, installato, avviato e disinstallato dal
  workflow a ogni push. `desktop/make_icon.py` disegna l'icona (`desktop/assets`).
- `desktop/database.py`: `initdb` al primo avvio (UTF-8, accesso solo con password), avvio su `127.0.0.1` e porta
  libera, arresto pulito. Rifiuta di partire come root.
- `desktop/fetch_postgres.py`: scarica i binari portabili di PostgreSQL 16 (build zonky.io su Maven Central).
- `desktop/myfinanceplace.spec`: ricetta PyInstaller (cartella, non file unico: si avvia più in fretta). L'OCR
  leggero (rapidocr/onnxruntime) è escluso per tenere il pacchetto sotto i 300 MB: le scansioni si leggono con l'AI.

Costruire a mano (sul sistema per cui si costruisce):

```bash
pip install -r requirements.txt -r desktop/requirements-desktop.txt
python -m desktop.fetch_postgres
pyinstaller --noconfirm --distpath desktop/dist --workpath desktop/build desktop/myfinanceplace.spec
desktop/dist/MyFinancePlace/MyFinancePlace --smoke
```

Provare senza costruire: `python -m desktop.main` (dopo `fetch_postgres`).
