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

## 🔜 To do

### 1. Data models for the remaining modules (next big step)

Portfolio, Debt, Insurance, Documents, Snapshots, Goals and login still show only the page layout.
Each needs its own database table, with a model, an Alembic migration, a service and routes:

| Module | Model (main fields) | Notes |
|---|---|---|
| **Portfolio** | `Holding`: name, ticker, asset class (stock/ETF/crypto/bond/savings), quantity, avg. cost, current price | Total value and P&L; optional price updates |
| **Debt** | `Debt`: name, type (mortgage/loan), principal, rate, start date, term (months), installment | Amortization schedule, remaining balance |
| **Insurance** | `InsurancePolicy`: provider, type, premium, frequency, renewal date, coverage | Renewal reminders |
| **Documents** | `Document`: file path, fiscal year, category, linked `transaction_id` | File storage (local folder) |
| **Snapshots** | `Snapshot`: date, net worth, assets, liabilities, JSON detail | Created from the dashboard; the compare page |
| **Goals** | `Goal`: name, target amount, target date, saved amount | Progress bars in Lifestyle → Goals |
| **Auth** | `User` + Flask-Login (already in `requirements.txt`) | Then add `user_id` to every table |

Suggested order: **Portfolio → Debt** (they unlock net worth and the Balance Sheet) → Goals → Snapshots →
Insurance → Documents → Auth.

### 2. Net worth and Balance Sheet

Until Portfolio and Debt exist, net worth is just income minus expenses, and the Balance Sheet stays a
placeholder. Once they exist:
- Net worth = cash balance + portfolio value − outstanding debt
- Balance Sheet: assets (cash, investments) vs liabilities (debts)
- Dashboard "Investments", "Total debt" and "Debt/Income" KPIs (currently 0 / —)

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
- Learn from corrections: remember the category the user picked for a description
- Extract the counterparty (merchant name) from the description
- Test against real exported files (anonymized) from each bank, especially PDFs, whose layouts vary the most
- OCR for scanned PDFs and photos of statements (e.g. Tesseract), currently rejected with a message
- Legacy Word `.doc` files (currently: "save as .docx or PDF")

### 6. Continuous integration

The repo has no CI yet, so the tests only run when you run `pytest` yourself (see the README).
Add a GitHub Actions workflow that starts a PostgreSQL service container, installs `requirements.txt`
and runs `pytest` on every pull request.

### 7. Smaller clean-ups

- Settings are stored in the session: persist them in the database once users exist
- The transaction form crashes (500) on invalid input: add validation (e.g. Flask-WTF forms)
- The category list is hardcoded in several templates: centralize it
