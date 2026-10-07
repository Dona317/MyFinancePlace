# Next Steps — MyFinancePlace

Current status and roadmap. Update this file as items are completed. The MVP checklist is in [MVP.md](MVP.md).

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
- **Accounts and cards** with balance per account and reconciliation; **several currencies** with rates by
  date (ECB download) and totals in a chosen base currency; **monthly budgets** with warnings; **reminders**
  (bell in the top bar); **editable categories** and **categorization rules** written or learned from
  corrections; cash flow from **explicit links** to investments and debts; display preferences applied
- **CI** (GitHub Actions), **Docker** image and compose, **production config** (see `docs/DEPLOY.md`)
- **Interface in Italian or English** (Settings → Visualizzazione → Lingua): Flask-Babel, Italian as the source,
  `app/translations/en` complete; words stored as data (policy types, asset classes…) stay Italian in the database
  and are translated when shown. After changing texts: `python scripts/translations.py update`, translate the new
  entries in `messages.po`, then `python scripts/translations.py compile` (a test fails if the catalog is incomplete)
- **Dashboard by year**: expense and income doughnuts with their month-by-month lines per category, monthly bars
  with the running totals; **Reports** page (spending, income, cash flow by period and account)
- **Transactions**: signed amount in the form (the type follows the sign, transfers have their own box), the
  counterparty shown as the first tag (migration `b7c1d2e3f4a5`), tag picker with the tags already used, AI tag
  «da confermare (AI)» with one-click confirmation; a base set of 33 editable categories
- **Sign-in** (Flask-Login): the first user, an administrator, is created on the first visit; then only
  administrators add users (Impostazioni → Account e utenti); the data is shared; pages redirect to the login,
  the API answers 401; `flask users create|reset-password|list`; users are not part of backups
- **Docker**: the `db` volume now holds the data (`PGDARE` typo fixed) and the image is pinned to `postgres:16`;
  moving an older installation is described in `docs/DEPLOY.md`
- **Balances in the account's currency**: a transaction in another currency counts with what the bank charged
  (`account_amount`, `counter_amount` for the arriving side of a transfer) or, until entered, with the day's rate;
  opening balances and account totals are converted to the base currency; every app function is run by a test
  (`scripts/untested_functions.py` in CI)
- **Performance and lighter AI**: paged transaction list, duplicate candidates found by the database, no eager
  account joins; scans read by a light OCR (RapidOCR, ~16 MB models) with the AI as backup; categories learned
  from the user's history before asking a model; repeated causali asked once
- **Subcategories** (migration `270b797b5daf`): `categories.parent_id`, one level; a starting set added once
  (Casa, Bollette, Trasporto, Ristoranti, Salute, Abbonamenti); grouped lists, roll-up in dashboard/budgets,
  report drill-down, `main_category` in the CSV/JSON export, hierarchy in the AI prompt
- **Mapped import without errors**: `services/column_guess.py` recognises the columns from the values, fixes a
  wrong choice with a note, and can ask the AI on a 10-row sample; the rows open in the editable preview
- **Savings rate month by month** (F3): dashboard line for the year and the year before (same months), the
  year's rate next to the title; months without income are a gap, not 0%
- **Merchant from the causale** (`services/merchant.py`): counterparty and first tag on import, "Compila
  controparti" for saved transactions; checked on every sample statement
- **Full backup (.zip) and restore**, with an automatic copy of the replaced data; the older JSON export of
  the transactions can be re-imported

## 🔜 To do

### 1. Price history

Holdings are valued at their latest price, also in the balance sheet of past months (the app keeps no price
history). Snapshots record the value at that moment; an optional price feed (ETFs, crypto) would make past
balance sheets exact.

### 2. Bank import improvements (MVP point 4, TBD)

- Check the new layouts (UniCredit, BPER, BancoPosta, ING, Revolut, N26) against real anonymized exports: they
  follow the published column names, but the samples in `samples/bank_statements` are generated. Banca Sella,
  Mediolanum and BCC are read by the generic layout until a real export shows distinctive columns
- Files imported as "generic" before a bank got its own layout (e.g. a Revolut CSV) get a different fingerprint
  when imported again, so they are shown as *possible* duplicates (similar amount/date) rather than skipped
- Test against real exported files (anonymized) from each bank, especially PDFs, whose layouts vary the most
- AI reading (done, optional): measure accuracy of `qwen2.5vl:7b` vs Claude on real anonymized scans.
  It runs in a background thread (`app/services/ai_jobs.py`) with a waiting page showing progress per page;
  job state is in memory plus a JSON next to the upload, so it assumes one gunicorn process (the default)

