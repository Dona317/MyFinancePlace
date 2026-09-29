# Next Steps — MyFinancePlace

Current status and roadmap. Update this file as items are completed.

## ✅ Done

- **Transactions**: CRUD, REST API, search and filters
- **Dashboard**: real KPIs, 12-month cash flow, expenses by category, recent transactions
- **Accounting**: Income Statement and Cash Flow computed from transactions
- **Lifestyle**: category breakdown, trends, month-over-month comparison
- **Export**: CSV, JSON, tax export by year, downloadable PDF report (fpdf2) and printable page,
  CSV/Excel/.ods import with column mapping
- **Bank statement import**: Fineco, Intesa Sanpaolo, UniCredit, BPER, Poste Italiane (BancoPosta), ING, Revolut,
  N26 and generic bank files — Excel, CSV, PDF, TXT, Word (.docx and 97-2003 .doc), OpenDocument, RTF — with
  auto-categorization, a review step and duplicate detection
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

### 5. Bank import improvements

- Check the new layouts (UniCredit, BPER, BancoPosta, ING, Revolut, N26) against real anonymized exports: they
  follow the published column names, but the samples in `samples/bank_statements` are generated. Banca Sella,
  Mediolanum and BCC are read by the generic layout until a real export shows distinctive columns
- Files imported as "generic" before a bank got its own layout (e.g. a Revolut CSV) get a different fingerprint
  when imported again, so they are shown as *possible* duplicates (similar amount/date) rather than skipped
- Non-EUR rows (Revolut) keep their currency, but the preview totals and reports add them as if they were EUR
  until multi-currency (track C, step 6)
- User-editable categorization rules (e.g. a "Rules" page in Settings) instead of the hardcoded `CATEGORY_RULES`
- Learn from corrections: remember the category the user picked for a counterparty, and pass past examples
  to the AI classifier as few-shot hints (the `categoria-ai` tag marks rows to learn from once reviewed)
- Extract the counterparty (merchant name) from the description
- Test against real exported files (anonymized) from each bank, especially PDFs, whose layouts vary the most
- AI reading (done, optional): measure accuracy of `qwen2.5vl:7b` vs Claude on real anonymized scans.
  It runs in a background thread (`app/services/ai_jobs.py`) with a waiting page showing progress per page;
  job state is in memory plus a JSON next to the upload, so it assumes one gunicorn process (the default)

### 6. Continuous integration

The repo has no CI yet, so the tests only run when you run `pytest` yourself (see the README).
Add a GitHub Actions workflow that starts a PostgreSQL service container, installs `requirements.txt`
and runs `pytest` on every pull request.

### 7. Smaller clean-ups

- The transaction form crashes (500) on invalid input: add validation (e.g. Flask-WTF forms)
- The category list is hardcoded in several templates: centralize it
