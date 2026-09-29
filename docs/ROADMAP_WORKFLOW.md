# Workflow — remaining features, bugs and infrastructure

How the remaining items of the review are built, in which order and by whom, so they can be worked on
unattended without stepping on each other. Status is updated as each item is merged into `test-Cloud`.

## Tracks

Three tracks run in parallel. Each works on its own branch (a git worktree for the two background agents),
its own test database and its own dev-server port, and only touches the files listed for it.
Everything is merged into `test-Cloud` (PR #8) after the full test suite passes on the merged result.

| Track | Who | Branch | Test DB | Port | Owns |
|---|---|---|---|---|---|
| **A — Infrastructure** | background agent | `track/infra` | `mfp_test_infra` | 5001 | `.github/`, `Dockerfile`, `docker-compose.yml`, `wsgi.py`, `gunicorn.conf.py`, `config.py` (production part), logging, `docs/DEPLOY.md` |
| **B — Import & export formats** | background agent | `track/formats` | `mfp_test_formats` | 5002 | new bank layouts in `app/services/bank_import.py` (layout table only), `statement_readers.py`, CSV/Excel manual mapping, real PDF report, legacy `.doc`, their samples and tests |
| **C — Core data model** | main session | `test-Cloud` | `mfp_test` | 5000 | everything with a migration or shared UI: categories, rules, accounts, currencies, budgets, notifications, the 🔵 bugs, background AI jobs, then i18n |

Why this split: track C changes the database schema; migrations must form a single chain, so they are
written by one track only, in sequence. Tracks A and B add files or touch isolated functions and never
add migrations. i18n comes last because it touches every template.

## Order inside track C

Each step = model + migration + service + routes/templates + tests, then a commit on `test-Cloud`.

1. **Bug — disabled modules still reachable**: a `before_request` guard per blueprint returns 404 when the
   module is off in Settings.
2. **Bug — transaction form 500 on bad input**: one validation path (the `form_*` helpers) for the HTML
   form, with field-level messages; the REST API keeps its schema validation.
3. **Categories, centralized and editable** — table `categories` (name, kind income/expense, color, icon);
   every template reads them from one service; Settings → Categorie to add/rename/merge (renaming updates
   the transactions).
4. **Categorization rules editable and learned** — table `category_rules` (pattern, field, category,
   priority, source manual/learned); the hard-coded `CATEGORY_RULES` become seed rules; correcting a
   category offers "ricorda per questa controparte"; the AI classifier gets past examples as hints.
5. **Accounts and cards** — table `accounts` (name, kind current/card/savings/cash, currency, opening
   balance, IBAN tail); `transactions.account_id`; import asks the account; balance per account;
   reconciliation: enter the statement balance at a date, see the difference.
6. **Multi-currency** — table `exchange_rates` (date, currency, rate to EUR), manual entry plus an optional
   ECB download; every total converts through the base currency; the transaction shows original amount.
7. **Monthly budgets per category** — table `budgets` (category, month or recurring, amount); page with
   spent vs budget bars; dashboard warning when a category passes 80% / 100%.
8. **Notifications and reminders** — one service collecting due items: policy expiries, upcoming recurring
   transactions, debt installments, budget overruns, goals behind schedule; bell in the top bar with a
   count; a page listing them; dismissible.
9. **Settings applied: currency, locale, date format** — the `money`, `number` and `it_date` filters read
   the saved preferences.
10. **Cash flow classified by explicit links** — `transactions.holding_id` / `transactions.debt_id`
    (optional); investing/financing come from the links, the category keywords remain as a fallback.
11. **Long AI reading in the background** — a job table + a worker thread; the upload returns at once and the
    page polls a progress endpoint; the result opens the usual preview.
12. **i18n** — Flask-Babel, Italian as the source, English translation, language in Settings.

## Definition of done (every item, every track)

- Unit and route tests for the new behavior; the whole suite passes (`pytest`), `ruff check app tests` clean.
- A new migration applies on a fresh database and `flask db check` reports no pending changes (track C).
- The page works in light and dark mode, desktop and phone (no horizontal overflow, no JS errors).
- No new size limits; forms keep what was typed on error; Italian numbers accepted.
- `README.md` / `docs/NEXT_STEPS.md` updated.

## Status

| Item | Track | Status |
|---|---|---|
| Real Portfolio, Debt, Insurance, Documents, Snapshots, Goals, Balance Sheet | C | ✅ `ea58fbe` |
| Full backup and restore | C | ✅ `ea58fbe` |
| Settings saved in the database (bug) | C | ✅ `ea58fbe` |
| CI, Docker, production config | A | ⏳ |
| More banks, Excel manual mapping, real PDF, `.doc` | B | ⏳ |
| Steps C1–C12 | C | ⏳ |
