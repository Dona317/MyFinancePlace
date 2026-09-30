# MyFinancePlace

Personal finance management app — from household budgeting to investment portfolios.

## Features

| Module | Description |
|---|---|
| **Dashboard** | KPI cockpit — net worth, income, expenses, savings rate; for the chosen year: expense and income doughnuts by category, each next to its month-by-month lines, and monthly bars with the running totals |
| **Reports** | Spending, income and cash flow for any period and account: split by category (doughnut or bars, click to drill down), transactions by day, summary vs the previous period, CSV |
| **Accounting** | Balance Sheet, Income Statement, Cash Flow Statement |
| **Lifestyle** | Expenses by category, trends, personal goals |
| **Forecast** | Cash-flow forecast: recurring entries + variable spending over a rolling window, six methods compared |
| **Categories** | 33 editable main categories and **subcategories** (e.g. Bollette › Luce, Gas…; one level): a transaction stores the most specific one; dashboard, pies and budgets add subcategories to their main category, reports drill down into them, filters on a main category include its subcategories, the AI and your history suggest them too |
| **Transactions** | Signed amounts (−45,20 expense, 1.200 income), categories (a full editable base set), tags picked from the ones already used (the counterparty is the first tag), recurring entries, AI-suggested categories marked «da confermare (AI)» until confirmed |
| **Portfolio** | Stocks, ETFs, crypto, bonds, savings accounts |
| **Debt** | Mortgages and loans with amortization schedules |
| **Documents** | Archive linked to transactions, with fiscal-year tagging |
| **Snapshots** | Point-in-time financial snapshots for historical comparison |
| **Export** | CSV, JSON, downloadable PDF report, tax export by year, CSV/Excel import with columns recognised from the values (AI on a 10-row sample as backup) |
| **Languages** | Italian or English interface (Settings → Visualizzazione → Lingua) |

## Quick Start

```bash
# 1. Start the PostgreSQL database (only the db service; `docker compose up` alone also starts the app, see Deploy)
docker compose up -d db

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables
cp .env.example .env         # edit SECRET_KEY and DATABASE_URL if needed

# 5. Run the development server
python run.py
```

- Open `http://localhost:5000` in your browser.
- The API swagger documentation: `http://localhost:5000/swagger`

## Bank Statement Import

**Esporta → Importa Estratto Conto Bancario** turns a bank export into transactions:

1. Upload the file downloaded from home banking: Excel (`.xlsx`, `.xls`), `.csv`, `.pdf`, `.txt`,
   Word (`.docx` and 97-2003 `.doc`), LibreOffice (`.ods`, `.odt`) or `.rtf`.
   Scanned PDFs and photos are read by the built-in light OCR (below); the AI is the backup.
2. The bank and the header row are detected automatically (or pick the bank by hand):
   Fineco, Intesa Sanpaolo, UniCredit, BPER Banca, Poste Italiane (BancoPosta), ING, Revolut, N26, or any
   statement with Date / Description / Amount (or Credit/Debit) columns (Banca Sella, Mediolanum, BCC…).
   A bank is recognized by its own column names (case and accents do not matter) or by its name above the header
   or in the filename; the movements themselves are never used for this (a "Ricarica Revolut" line in a Fineco
   statement stays Fineco).
3. Review the preview: each row is auto-categorized, already-imported rows are flagged, and pending movements are excluded.
   Untick rows or change category/type, then confirm.

Bank specifics:

| Bank | Export | Notes |
|---|---|---|
| Fineco | Conto → Movimenti → Excel | `Autorizzato` rows skipped (pending) |
| Intesa Sanpaolo | Lista movimenti → Excel (also the old HTML `.xls` and the PDF) | `Non contabilizzato` rows skipped |
| UniCredit | Elenco movimenti → CSV/Excel (`Data Registrazione`, `Importo (EUR)`) | |
| BPER Banca | Movimenti conto → Excel (`Causale ABI`, signed `Importo`) | the ABI code becomes the detail line |
| Poste Italiane | BancoPosta Lista movimenti (`Addebiti`/`Accrediti (euro)`, `Descrizione operazioni`) | |
| ING | Movimenti conto (`Uscite`/`Entrate`, `Causale`, `Descrizione operazione`) | |
| Revolut | Estratto conto → Excel/CSV | only `COMPLETED` rows (pending, reverted, declined are skipped); a non-zero `Fee` becomes a separate "Commissione Revolut" expense; the row currency is kept |
| N26 | CSV (new `Booking Date`/`Partner Name` and old `Date`/`Payee` layouts) | `Amount (EUR)` is used; `Payment Reference` becomes the detail |

Re-importing the same (or an overlapping) statement is safe: each row gets a fingerprint (`import_ref`) and duplicates are skipped.
Categorization rules live in `app/services/bank_import.py` (`CATEGORY_RULES`).

How each format is read: spreadsheets and document tables are used as-is; PDFs and fixed-width text without a real
table are rebuilt into columns from the header positions (wrapped descriptions are joined); as a last resort,
lines shaped like `date … description … amount` are recognized. See `app/services/statement_readers.py`.
Word 97-2003 `.doc` files are read in pure Python (`olefile`: the text and its tables come from the piece table of the
`WordDocument` stream), so no antiword or LibreOffice is needed; password-protected `.doc` files are refused with a message.

**Importa CSV o Excel con mappatura manuale** (same page) is for files no layout recognizes: pick the file
(`.csv`, `.xlsx`, `.xls`, `.ods`), the app finds the header row (skipping the bank's preamble) and **recognises the
columns from their values** — dates, amounts, separate Dare/Avere columns, type words, the richest text as the
description — and preselects them; you can change them. A wrong choice is not an error: a column that holds no
dates/amounts/text is swapped for the right one with a note, rows that still cannot be read are listed, and the
rows open in the **same editable preview** as bank statements (duplicates, categories from your history). When
the values are not clear and an AI model is set, *Chiedi all'AI quali colonne sono* sends it only the headers and
the first 10 rows, and its answer is checked the same way.

**Report PDF**: *Scarica PDF* downloads the yearly report (key figures, income statement by category, monthly table,
cash flow) generated on the server with `fpdf2` (pure Python); *Stampa dal browser* opens the same report as a page to print.

### Scans and photos: light OCR first, AI as the backup

A scanned PDF or a photo is first read by a **light OCR** (RapidOCR: ONNX models of ~16 MB, CPU only, offline,
about 5 s per page): the recognised words keep their positions, so the same column rebuilding used for text PDFs
reads the table — no language model. On the sample scan it gets 50 of 53 movements exactly right. The preview
says the rows come from OCR and, when an AI model is configured, offers **Rileggi con l'AI**; when the OCR
clearly missed rows (fewer movements than dated lines, e.g. a skewed photo) the app goes straight to the AI
question below. Without the `rapidocr-onnxruntime` package, scans go to the AI question as before.

### AI reading of scans, photos and non-standard documents (optional)

When neither the rule-based reader nor the OCR can read a file — a skewed photo, a document with an unknown layout —
the app **stops and asks**: "Read it with AI?", with the model to use. Nothing is sent to a model without that
confirmation. After reading, the movements open in the **editable preview** (below) before anything is saved.

Set it up in **Impostazioni → Modelli AI** (`/settings/ai`), or with `LLM_PROVIDER` / `LLM_MODEL` in `.env`
(see `.env.example`; the settings page wins over `.env`):

| Provider | Models | Privacy |
|---|---|---|
| Disabled (default) | — | nothing leaves the app |
| **Ollama** (local) | Llama, Qwen, Gemma under 10 GB — see the catalog below | **the document never leaves your computer** |
| **Anthropic** (cloud) | `claude-opus-5` (default), `claude-sonnet-5`, `claude-haiku-4-5` | the document is sent to Anthropic (`ANTHROPIC_API_KEY`) |

Local model catalog (install, remove and pick them from the settings page, or with `scripts/install_models.py`):

| Size | Read scans and photos (vision) | Text documents only |
|---|---|---|
| **Medium** (5–10 GB, 12–16 GB RAM) | `qwen2.5vl:7b` *(recommended)*, `llama3.2-vision:11b`, `gemma3:12b` | `qwen3:8b`, `llama3.1:8b` |
| **Small** (2–4 GB, 8 GB RAM) | `qwen2.5vl:3b`, `gemma3:4b` | `qwen3:4b`, `llama3.2:3b` |
| **Tiny** (< 2 GB) | — (no vision model this small in these families) | `qwen3:1.7b`, `llama3.2:1b`, `gemma3:1b`, `qwen3:0.6b` |

```bash
# 1. Install Ollama: https://ollama.com/download   (Linux: curl -fsSL https://ollama.com/install.sh | sh)
# 2. Download models ahead of time (or click "Installa" in Impostazioni → Modelli AI)
python scripts/install_models.py --list                  # catalog + what is installed
python scripts/install_models.py --recommended           # qwen2.5vl:7b
python scripts/install_models.py --tier piccolo --vision # qwen2.5vl:3b, gemma3:4b
python scripts/install_models.py --tier tiny --dry-run   # just print the `ollama pull` commands
```

How AI results are kept honest: JSON constrained to a schema; invalid rows discarded; **balance check**
(opening balance + movements = closing balance, recalculated live while you edit); AI-read rows tagged `ai`.

### The bank's causale and AI quick classification

- Every imported transaction keeps the bank's **original causale** (`bank_description`: the description plus the
  bank's detail column), exactly as read. You can rewrite the description; the causale stays on record and is
  shown in the list, the edit page (read-only), the duplicates page, the CSV/JSON export and the API.
- **Classifica con AI** gives a quick first classification from the causale: category (always one of your
  categories) and counterparty (e.g. "Esselunga"), with a confidence. Available:
  - in the import preview (suggestions highlighted, uncertain ones in orange, all editable before saving);
  - in Transazioni, for the selected transactions or all those without a category (a review page lists current
    vs suggested; only confident changes are preselected).
- **Your history comes first**: categories you already gave to similar transactions (same merchant words, the
  rarer words weighing more) are suggested without asking any model — "dal tuo storico" — and only the causali
  it cannot place clearly go to the AI. It also categorizes imported rows. On the demo data it places 93% of the
  last six months from the first twelve, with no wrong guesses. Repeated causali (the same shop every week, with
  different dates or card numbers) are sent to the model once; with Claude, batches go out 4 at a time.
- It never makes things worse: a specific category is not replaced by "Altro" or by an unsure suggestion.
- Rows saved with an AI category accepted unchanged get the `categoria-ai` tag, to double-check later.
- It is a text-only task: a small or tiny model is enough and much faster. Choose it in Modelli AI →
  "Modello per classificare" (e.g. `qwen3:1.7b`, `llama3.2:3b`, `claude-haiku-4-5`); empty = the reading model.

### Editable import preview

Every import (rule-based or AI) opens a preview where each row's date, description, amount, type and category
can be edited, rows can be deselected or removed, and missing rows added by hand. Rows already imported are
shown greyed out; rows that **look like** an existing transaction (same amount, date within 3 days, similar
description) are flagged "Possibile duplicato" and deselected until you check them.

### Duplicates, editing and deleting

- **Transazioni → Cerca duplicati** (`/transactions/duplicates`) groups similar transactions (e.g. the same
  statement imported from Excel and from PDF). For each group: keep one and delete the others, mark them as
  "not duplicates" (they won't be proposed again), or edit/delete each one. Sensitivity and date distance are adjustable.
- Every transaction can always be edited or deleted: from the list (also several at once), from the edit page,
  and from the duplicates page.

Fake statements to try it with, in every supported format, are in
[`samples/bank_statements/`](samples/bank_statements/README.md).

After pulling this change run `flask --app run db upgrade` to add the `import_ref` column.

See [`docs/MVP.md`](docs/MVP.md) for the MVP checklist and [`docs/NEXT_STEPS.md`](docs/NEXT_STEPS.md) for the roadmap.

## Size limits

There are none on your data: uploads of any size, statements with any number of rows, descriptions,
categories and counterparties of any length, amounts up to 36 integer digits (`NUMERIC(38, 2)`).
Long documents are read by the AI in parts (every page of a scan; long texts in blocks; Claude gets long
PDFs in blocks of 20 pages) and the results are merged. What remains is only practical: time — a local
model on CPU needs about a minute per scanned page.

## Tests

The test suite runs against a real PostgreSQL database (the models use `ARRAY` columns).
Create an empty test database once, then point `TEST_DATABASE_URL` at it:

```bash
docker compose exec db createdb -U sa myfinanceplace_test   # once
TEST_DATABASE_URL=postgresql://sa:Pa55w0rd@localhost:5332/myfinanceplace_test pytest
```

GitHub Actions (`.github/workflows/tests.yml`) runs on every push and pull request: `ruff check app tests migrations`,
`flask db upgrade` on a fresh PostgreSQL 16 database followed by `flask db check`, then the whole suite.

## Deploy

One command runs everything — PostgreSQL, migrations and the app under gunicorn — on `http://localhost:8000`:

```bash
cp .env.example .env    # optional
docker compose up -d
```

On the first visit the app asks to create the first user (an administrator); more users are added in
*Impostazioni → Account e utenti* and everyone sees the same data.
HTTPS with Caddy or nginx, production settings, backups (`pg_dump` and Esporta → Backup Completo) and updates
are described in [docs/DEPLOY.md](docs/DEPLOY.md).

## Implementation Status

| Module | Status |
|---|---|
| Transactions | ✅ CRUD, REST API, search & filters, bulk delete, duplicate finder |
| Dashboard | ✅ KPIs (net worth = assets − liabilities, investments, debt, debt/income), 12-month cash flow, expenses by category, recent transactions |
| Accounting | ✅ Balance Sheet (any month end, opening cash balance), Income Statement, Cash Flow, net-worth trend |
| Lifestyle | ✅ Category breakdown, trends, month-over-month, savings Goals (contributions, monthly amount needed) |
| Export | ✅ CSV, JSON, tax export, downloadable PDF report (and printable page), CSV/Excel import with column mapping, **full backup (.zip) and restore** |
| Bank import | ✅ Fineco, Intesa Sanpaolo, UniCredit, BPER, BancoPosta, ING, Revolut, N26 and generic bank statements — Excel, CSV, PDF, TXT, Word (.docx/.doc), OpenDocument, RTF — with auto-categorization and duplicate detection |
| Portfolio | ✅ Holdings of any class (also savings accounts, pension funds, property), gain/loss, allocation, bulk price update |
| Debt | ✅ Mortgages, loans, credit cards: French amortization plan, outstanding balance, interest |
| Insurance | ✅ Policies, annual premium, expiry reminders (60 days) |
| Documents | ✅ File archive (any format), filters, link to a transaction, included in the backup |
| Snapshots | ✅ Net worth over time, compare two snapshots or a snapshot with today |
| Auth | ✅ Sign-in with username and password, first administrator on the first visit, users managed by administrators (shared data), `flask users` commands |

### Backup and restore

Esporta → **Backup Completo e Ripristino** downloads one `.zip` with every table and the files of the
document archive. Restoring it replaces all current data (all or nothing); the data being replaced is
first saved under `instance/backups/` (last 10 kept, downloadable from the same page). The older JSON
export of the transactions can be restored too: its transactions are added, skipping those already present.

## Database

PostgreSQL runs in Docker. The `docker-compose.yml` at the project root defines the container.

| | |
|---|---|
| **Host** | `localhost` |
| **Port** | `5332` |
| **Database** | `myfinanceplace` |
| **User** | `sa` |
| **Password** | `Pa55w0rd` |

```powershell
# Start the DB
docker compose up -d db

# Open a psql shell inside the container
.\connect_to_postgres_db.ps1

# Stop the DB
docker compose down
```

The `DATABASE_URL` for Flask-SQLAlchemy:

```bash
postgresql://sa:Pa55w0rd@localhost:5332/myfinanceplace
```

## How to Commit Changes to the Project

1. Before starting a new task, you need to switch to the main branch (located at the bottom left) and pull (download) the latest version of the main branch.
2. Select “main” at the bottom left of the VS Code window; a prompt will appear at the top. Select “+ Create new Branch.”
3. In the “+ Create new Branch” window, enter the branch name (a title representing the task).
4. I navigate to the tree view section (similar to the Git icon), the third one at the top left, and commit the changes by entering a description of the modifications made, e g., “Code Refactoring,” “Update Class ...”
5. When the task is complete, proceed to publish the branch
6. Create the “Pull Request”
7. Request approval for the “Pull Request”
8. Once approved, click “Merge”

## Project Structure

```bash
MyFinancePlace/
├── run.py                  # Entry point
├── config.py               # Environment configurations
├── requirements.txt
├── app/
│   ├── __init__.py         # App factory (create_app)
│   ├── routes/             # One Blueprint per module
│   ├── templates/          # Jinja2 HTML templates
│   └── static/
│       ├── css/
│       │   ├── theme.css   # ← All colors live here
│       │   └── main.css    # Layout and components
│       └── js/
│           ├── charts.js   # Chart.js helpers
│           └── main.js     # UI interactions
```

## Theming

All colors are CSS variables defined in **`app/static/css/theme.css`**.
To retheme the entire app, only edit that one file — no other file needs changing.

## Translations

Italian is the source language; the English catalog is in `app/translations/en/LC_MESSAGES/messages.po`.
Texts are marked with `_()` / `ngettext()` (templates and Python), `_l()` for labels defined at import time and
`N_()` for words that are also stored as data (shown with the `|tr` filter). After changing texts:

```bash
python scripts/translations.py update    # extract and merge the new texts into messages.po
# translate the new (empty) entries in messages.po
python scripts/translations.py compile   # rebuild messages.mo (committed; a test checks it is complete and current)
```

## Tech Stack

- **Backend**: Python / Flask
- **Templates**: Jinja2
- **Charts**: Chart.js 4 (CDN)
- **Icons**: Bootstrap Icons (CDN)
- **Fonts**: Inter (Google Fonts)
- **CSS**: Custom (no frameworks — pure CSS variables)
