# MyFinancePlace

Personal finance management app — from household budgeting to investment portfolios.

## Features

| Module | Description |
|---|---|
| **Dashboard** | KPI cockpit — net worth, income, expenses, savings rate |
| **Accounting** | Balance Sheet, Income Statement, Cash Flow Statement |
| **Lifestyle** | Expenses by category, trends, personal goals |
| **Transactions** | Full CRUD with tags, categories, counterparties, recurring entries |
| **Portfolio** | Stocks, ETFs, crypto, bonds, savings accounts |
| **Debt** | Mortgages and loans with amortization schedules |
| **Documents** | Archive linked to transactions, with fiscal-year tagging |
| **Snapshots** | Point-in-time financial snapshots for historical comparison |
| **Export** | CSV, JSON, PDF, tax export by year, Excel import |

## Quick Start

```bash
# 1. Start the PostgreSQL database
docker compose up -d

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
   Word (`.docx`), LibreOffice (`.ods`, `.odt`) or `.rtf`.
   PDFs must be the original text PDFs from home banking — scanned images would need OCR and are rejected with a message.
2. The bank and the header row are detected automatically (or pick the bank by hand):
   Fineco, Intesa Sanpaolo, or any statement with Date / Description / Amount (or Credit/Debit) columns.
3. Review the preview: each row is auto-categorized, already-imported rows are flagged, and pending movements are excluded.
   Untick rows or change category/type, then confirm.

Re-importing the same (or an overlapping) statement is safe: each row gets a fingerprint (`import_ref`) and duplicates are skipped.
Categorization rules live in `app/services/bank_import.py` (`CATEGORY_RULES`).

How each format is read: spreadsheets and document tables are used as-is; PDFs and fixed-width text without a real
table are rebuilt into columns from the header positions (wrapped descriptions are joined); as a last resort,
lines shaped like `date … description … amount` are recognized. See `app/services/statement_readers.py`.

### AI reading of scans, photos and non-standard documents (optional)

When the rule-based reader cannot read a file — a scanned PDF, a phone photo, a document with an unknown layout —
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

See [`docs/NEXT_STEPS.md`](docs/NEXT_STEPS.md) for the roadmap.

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

## Implementation Status

| Module | Status |
|---|---|
| Transactions | ✅ CRUD, REST API, search & filters, bulk delete, duplicate finder |
| Dashboard | ✅ KPIs, 12-month cash flow, expenses by category, recent transactions |
| Accounting | ✅ Income Statement, Cash Flow · ⏳ Balance Sheet (needs Portfolio/Debt models) |
| Lifestyle | ✅ Category breakdown, trends, month-over-month · ⏳ Goals |
| Export | ✅ CSV, JSON, tax export, printable report, CSV import |
| Bank import | ✅ Fineco, Intesa Sanpaolo and generic bank statements — Excel, CSV, PDF, TXT, Word, OpenDocument, RTF — with auto-categorization and duplicate detection |
| Portfolio, Debt, Insurance, Documents, Snapshots, Auth | ⏳ UI only — models not implemented yet |

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
docker compose up -d

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

## Tech Stack

- **Backend**: Python / Flask
- **Templates**: Jinja2
- **Charts**: Chart.js 4 (CDN)
- **Icons**: Bootstrap Icons (CDN)
- **Fonts**: Inter (Google Fonts)
- **CSS**: Custom (no frameworks — pure CSS variables)
