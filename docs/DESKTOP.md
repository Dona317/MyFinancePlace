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

Il programma non è firmato con un certificato a pagamento, quindi al primo avvio:
- **Windows**: «Windows ha protetto il PC» → *Ulteriori informazioni* → *Esegui comunque*.
- **macOS**: tasto destro su `MyFinancePlace.app` → *Apri* → *Apri*. Se dice che è danneggiata (succede ai file
  scaricati da internet): `xattr -dr com.apple.quarantine MyFinancePlace.app` nel Terminale, poi di nuovo *Apri*.
- **Linux**: la finestra nativa richiede GTK (`python3-gi`); senza, l'app si apre nel browser.

## Primo avvio

1. L'app prepara il database nella cartella dei dati (qualche secondo, solo la prima volta).
2. Chiede di creare l'utente e la password: proteggono i dati dei clienti.
3. Da *Clienti* si creano gli archivi dei clienti (F11).

Gli avvii successivi richiedono circa 2 secondi. Chiudendo la finestra si fermano server e database.

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
browser invece che nella finestra), `--headless` (solo server, stampa l'indirizzo), `--smoke` (avvia, controlla e
chiude: usato dalla build).

## Come è fatto

- `desktop/main.py`: cartella dati → PostgreSQL locale → migrazioni → server waitress su `127.0.0.1` (porta
  libera) → finestra pywebview. Un secondo avvio mentre l'app è aperta riapre la stessa.
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
