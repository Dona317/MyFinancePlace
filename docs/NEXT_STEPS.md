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
- **Split transactions** (F1, migration `a1c2e3f4b5d6`): «Suddividi» in the transaction form divides the amount
  across categories (parts must add up, transfers can't be split; `category` keeps the largest part). Every total
  by category counts each part (`totals.LINE_CATEGORY/LINE_VALUE`, `with_lines`, `lines_query`): dashboard,
  income statement, Sankey, Riepilogo, budgets, reports (rows show their share), forecast, dividends; rename/delete
  of a category, the API (`splits`), CSV/JSON export and the full backup carry the parts; rules, AI and the
  history leave a split made by hand alone
- **Summary table** (F2, Report → Riepilogo, `analytics.summary_table`): the year as a category × month table, the
  spreadsheet inside the app — subcategories under their main category, total, monthly average, change on the
  same months of the year before, net and savings rate rows; cells shaded by their share of the row's busiest
  month and linked to their transactions; CSV export
- **Savings rate month by month** (F3): dashboard lines for every year with income, each with its yearly rate;
  chips choose the years compared (by default the year shown and the one before, remembered in the browser);
  months without income are a gap, not 0%
- **Nature of a category** (F8, migration `b2d4f6a8c0e1`): `categories.nature` fixed / not monthly / variable,
  chosen in Settings → Categorie (a subcategory without one takes its main category's; defaults seeded by name).
  Spese e tendenze shows the split of the year's spending and what can be cut; the Riepilogo marks each expense row
- **Months of autonomy** (F10a, `analytics.autonomy`): liquid money ÷ average spending of the last 12 complete
  months (at least 3), also for fixed and not monthly costs only; the target (3/6/9/12 months) is a setting
- **Subscriptions page** (F9, `/subscriptions`, `services/subscriptions.py`): flagged and detected recurring
  series with monthly/yearly cost, next charge, last payment and price change; confirm a detected one, end a
  series on its last payment («Non più attivo», `recurrence_end`) or resume it; recurring income on its own tab
- **OFX / QIF / CAMT.053 import** (F6, `services/structured_statements.py`, standard library only): OFX 1 (SGML)
  and 2 (XML), QIF (day/month order from the file, `L` category kept when it is one of ours, `L[Account]` = transfer),
  CAMT.053/052 (booked entries only, debtor/creditor as counterparty, opening/closing balance check; DOCTYPE/ENTITY
  refused); same preview, categories, merchants and duplicates as the other statements
- **Complete demo dataset** (`samples/dati_fittizi/genera_completo.py`, `tests/test_demo_dataset.py`): three years
  on four accounts linked by transfers (current, credit card paid off monthly, savings, broker), with a portfolio
  built from linked trades (ETF plan, bond coupons, shares bought and half sold, crypto, pension contributions),
  six policies (one expiring soon, one ended) with their premiums, three debts (one repaid), PDF documents and
  quarterly snapshots; restorable backup + the last weeks of each account as CSV / OFX / CAMT.053 / QIF statements.
  It showed that buying an investment with a transfer left the money in the balance sheet's cash as well as in
  the portfolio: `wealth.cash_balance` now takes it out (and a sale brings it back)
- **Budget rollover and set-asides** (F7, migration `c3e5a7b9d1f2`): «Riporta» on an every-month budget carries what
  is left (or overspent) to the next month from the month it was switched on (`budgets.carried`); «Da accantonare»
  lists the not-monthly categories (F8) with 1/12 of their last 12 months, and budgets that quota with rollover
- **Income stability** (F10b, `analytics.income_stability`, Previsioni panel): each income source over the last 12
  complete months — months present, average, coefficient of variation, share — as stable (≥ 10 months, ±15%),
  variable (≥ 6 months) or occasional, with the share of income from stable sources
- **Price history of the holdings** (F5, migration `d4f6b8c0e2a3`, `holding_prices`): Portafoglio → Storico prezzi
  (one price or pasted «date;price» lines, chart, delete), «Aggiorna prezzi» on a chosen date; balance sheets, the
  net worth trend and snapshots value each holding at the latest price known on that date (`wealth.prices_on`)
- **Merchant from the causale** (`services/merchant.py`): counterparty and first tag on import, "Compila
  controparti" for saved transactions; checked on every sample statement
- **Full backup (.zip) and restore**, with an automatic copy of the replaced data; the older JSON export of
  the transactions can be re-imported

## 🔜 To do

What is left, with priorities and decisions, is in **[PIANO_E_TODO.md](PIANO_E_TODO.md)** (one list for the whole
project). Below only the technical notes that belong to an open item there.

### Notes for F4 — bank import with real statements

- Check the new layouts (UniCredit, BPER, BancoPosta, ING, Revolut, N26) against real anonymized exports: they
  follow the published column names, but the samples in `samples/bank_statements` are generated. Banca Sella,
  Mediolanum and BCC are read by the generic layout until a real export shows distinctive columns
- Files imported as "generic" before a bank got its own layout (e.g. a Revolut CSV) get a different fingerprint
  when imported again, so they are shown as *possible* duplicates (similar amount/date) rather than skipped
- Test against real exported files (anonymized) from each bank, especially PDFs, whose layouts vary the most
- AI reading (done, optional): measure accuracy of `qwen2.5vl:7b` vs Claude on real anonymized scans.
  It runs in a background thread (`app/services/ai_jobs.py`) with a waiting page showing progress per page;
  job state is in memory plus a JSON next to the upload, so it assumes one gunicorn process (the default)

