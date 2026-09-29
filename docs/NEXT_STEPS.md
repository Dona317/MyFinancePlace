# Next Steps — MyFinancePlace

Current status and roadmap. Update this file as items are completed.

## ✅ Done

- **Transactions**: CRUD, REST API, search and filters
- **Dashboard**: real KPIs, 12-month cash flow, expenses by category, recent transactions
- **Accounting**: Income Statement and Cash Flow computed from transactions
- **Lifestyle**: category breakdown, trends, month-over-month comparison
- **Export**: CSV, JSON, tax export by year, printable report, CSV import with column mapping
- **Bank statement import**: Fineco, Intesa Sanpaolo and generic bank files — Excel, CSV, PDF, TXT, Word,
  OpenDocument, RTF — with auto-categorization, a review step and duplicate detection
- **AI reading of scans, photos and non-standard statements** (optional, always after user confirmation):
  local Llama/Qwen/Gemma models via Ollama (catalog, install/remove page, CLI script) or Claude,
  schema-validated JSON and a live balance check
- **Editable import preview** (every field, add/remove rows) and **duplicate finder**
- **Bank causale kept on record** and **AI quick classification** (category + counterparty, reviewed by the user)
- **Forecast** (Contabilità → Previsioni): recurring transactions projected on their dates plus variable
  spending per category from a rolling window of N months, with six methods (moving, weighted and exponential
  average, median, linear trend, seasonal) compared on the past; unflagged recurring series are suggested
- **Portfolio, Debt, Insurance, Documents, Snapshots, Goals** with their own tables: holdings of any class
  (savings accounts, pension funds and property too) with gain/loss and bulk price update; debts with a French
  amortization plan; policies with expiry reminders; a document archive linked to transactions; savings goals
  with contributions; snapshots of the net worth and their comparison
- **Balance Sheet** and real **net worth** (opening balance + transactions + holdings − debts), also at past
  month ends; dashboard Investments, Total debt and Debt/Income KPIs
- **Full backup (.zip) and restore**, with an automatic copy of the replaced data; the older JSON export of
  the transactions can be re-imported

## 🔜 To do

### 1. Login

`User` + Flask-Login (already in `requirements.txt`), then `user_id` on every table. Until then anyone who
can reach the server sees all the data: run it only on your own computer or local network.

### 2. Price history

Holdings are valued at their latest price, also in the balance sheet of past months (the app keeps no price
history). Snapshots record the value at that moment; an optional price feed (ETFs, crypto) would make past
balance sheets exact.

### 3. Cash flow classification

Cash flow sorts `transfer` transactions by category name: anything like "Investimenti" counts as investing,
and "mutuo" or "prestito" counts as loans. Replace this with explicit links: a transfer tied to a
portfolio holding (investing) or to a debt (financing).

### 4. PDF report and manual CSV mapping

- "PDF" means printing the report page from the browser. For a real downloadable PDF, add a library such as
  WeasyPrint and render `export/report.html` server-side.
- The manual column-mapping import still accepts CSV only. Bank statements in Excel are already supported by
  the bank import; extending manual mapping to `.xlsx` would reuse `bank_import.read_table()`.

### 5. Bank import improvements

- Add more banks (UniCredit, BPER, Poste, Revolut…) as dedicated layouts in `app/services/bank_import.py`
- User-editable categorization rules (e.g. a "Rules" page in Settings) instead of the hardcoded `CATEGORY_RULES`
- Learn from corrections: remember the category the user picked for a counterparty, and pass past examples
  to the AI classifier as few-shot hints (the `categoria-ai` tag marks rows to learn from once reviewed)
- Extract the counterparty (merchant name) from the description
- Test against real exported files (anonymized) from each bank, especially PDFs, whose layouts vary the most
- AI reading (done, optional): measure accuracy of `qwen2.5vl:7b` vs Claude on real anonymized scans, and
  move long local-model runs to a background job with a progress bar (today the upload request waits)
- Legacy Word `.doc` files (currently: "save as .docx or PDF")

### 6. Continuous integration

The repo has no CI yet, so the tests only run when you run `pytest` yourself (see the README).
Add a GitHub Actions workflow that starts a PostgreSQL service container, installs `requirements.txt`
and runs `pytest` on every pull request.

### 7. Smaller clean-ups

- The transaction form crashes (500) on invalid input: add validation (e.g. Flask-WTF forms)
- The category list is hardcoded in several templates: centralize it
