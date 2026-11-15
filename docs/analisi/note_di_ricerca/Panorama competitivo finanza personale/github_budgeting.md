# Open-source budgeting / bookkeeping projects on GitHub: metrics and community signals (observed 2026-11-09)

Method note: all metrics come from the public GitHub search API, queried 2026-11-09 with `gh api search/repositories`, `search/issues` and `search/commits`. Per-repo REST endpoints (releases, contributors) and GraphQL were blocked in this session, and GitHub releases pages timed out in WebFetch. So **contributor counts are missing**, and "last release" is inferred from release-bot or version-bump commits and release PRs. Commit counts come from `search/commits`, which only indexes the default branch, so treat them as activity indicators, not exact totals. "open_issues" from the search API includes open PRs.

## Q1. Metrics per project (stars, forks, release, cadence, license, stack, form factor, sync, AI)

### Takeaway
By stars, Maybe (archived) leads with 54k, then Actual (30.1k) and Firefly III (25.2k). Sure, a Maybe fork that is only 16 months old, already has 11.2k stars and the highest 2026 commit volume of the app-style projects. ezBookkeeping (6.0k), hledger (4.8k), Beancount (6.2k) and Ledger (6.1k) form the second tier. Cashew is effectively dormant and Ivy Wallet is archived. No project in the list is a local desktop app built for Italy. GnuCash, KMyMoney, MMEX and HomeBank are desktop apps, but none of them has AI or support for Italian banks.

### Cited Findings

**Main table.** Stars, forks and open issues+PRs were observed on 2026-11-09. Commits are on the default branch, for 2025 and for 2026 up to 9 Nov.

| Project | Stars | Forks | Open iss+PR | Commits 2025 / 2026 YTD | Last release (inferred) | 2026 cadence | License | Stack | Form factor |
|---|---|---|---|---|---|---|---|---|---|
| maybe-finance/maybe | 54,195 | 5,665 | 0 | n/a | n/a | none (**archived**, last push 2025-07-24) | AGPL-3.0 | Ruby/Rails | self-hosted web |
| actualbudget/actual | 30,103 | 3,265 | 203 | 1,326 / 1,350 | v26.11.0 (02 Nov) | monthly CalVer: 26.5.0 to 26.11.0, one release per month plus patches (26.5.1, 26.5.2, 26.8.1) | MIT | TypeScript (local-first, sync server) | web/PWA plus Electron desktop, self-hosted sync server |
| firefly-iii/firefly-iii | 25,179 | 2,376 | 187 | 2,063 / 2,621 | v6.7.9 (2026-10-11) | about 36 releases in 2026, from v6.4.15 (06 Jan) to v6.7.9 | AGPL-3.0 | PHP/Laravel | self-hosted web, plus a separate Data Importer |
| we-promise/sure | 11,191 | 771 | 858 | 881 / 2,321 | moved to CalVer tags on 2026-11-02 (PR #4539). Earlier tags were v0.6.x/v0.7.x alpha | very frequent alpha pre-releases | AGPL-3.0 | Ruby/Rails, plus a Tauri desktop shell and mobile apps | self-hosted web, desktop (Tauri), Android/iOS builds |
| ghostfolio/ghostfolio | 9,677 | 1,409 | n/a | 1,258 / 1,628 | not checked | active | AGPL-3.0 | TypeScript (Angular/NestJS) | self-hosted web (wealth and portfolio, not budgeting) |
| ellite/Wallos | 8,814 | 463 | 65 | not checked | not checked | active (push 2026-11-07) | GPL-3.0 | PHP | self-hosted web (subscription tracker) |
| akaunting/akaunting | 10,292 | 3,018 | 6 | 185 / 610 | not checked | active | NOASSERTION (BSL-like "Akaunting" license per repo, not verified) | PHP/Laravel | self-hosted web (SMB accounting) |
| beancount/beancount | 6,155 | 486 | 248 | 52 / 41 | not checked | low activity (last push 2026-08-23) | GPL-2.0 | Python/C++ | CLI, plain-text |
| ledger/ledger | 6,067 | 553 | 38 | 218 / 1,861 | not checked | sharp increase in commits in 2026 | NOASSERTION (BSD) | C++ | CLI, plain-text |
| mayswind/ezbookkeeping | 6,039 | 754 | 17 | 971 / 807 | v2.2.0 (2026-10-23) | 11 releases in 2026: 1.3.1 (18 Jan), 1.3.2, 1.4.0, 1.5.0, 1.5.1, 1.6.0, 2.0.0 (20 Jul), 2.0.1, 2.1.0, 2.1.1, 2.2.0 | MIT | Go plus Vue | self-hosted web/PWA, mobile UI, and a new desktop version (commits from Oct-Nov 2026) |
| hledgerorg/hledger (moved from simonmichael/hledger) | 4,815 | 424 | n/a | 1,209 / 2,310 | 1.99.6 (released and announced around 2026-11-01, per the repo docs commits) | active | GPL-3.0 | Haskell | CLI/TUI/web UI, plain-text |
| jameskokoska/Cashew | 4,794 | 862 | 12 | 1 / 1 | not checked | **dormant** (1 commit in 2025, 1 in 2026, last push 2026-03-09) | GPL-3.0 | Dart/Flutter | mobile (Android/iOS/web) |
| Gnucash/gnucash | 4,404 | 1,005 | 46 | 487 / 1,009 | 5.17 (2026-09-26) | quarterly: 5.15 (2026-03-28), 5.16 (2026-06-27), 5.17 (2026-09-26) | GPL (shows as NOASSERTION) | C/C++ GTK | desktop |
| securo-finance/securo | 4,244 | 603 | n/a | 0 / 698 (created 2026-03-08) | not checked | new | AGPL-3.0 | Python | self-hosted web (Docker) |
| ananthakumaran/paisa | 3,235 | 218 | 77 | 22 / 37 | not checked | low | AGPL-3.0 | Go | self-hosted web/desktop, ledger-based |
| Ivy-Apps/ivy-wallet | 3,186 | 1,046 | 69 | 4 / 2 | n/a | **archived** | GPL-3.0 | Kotlin | Android |
| TNT-Likely/BeeCount | 2,763 | 376 | n/a | 416 / 268 (created 2025-09-06) | not checked | active | NOASSERTION | Dart/Flutter | mobile/web, local-first |
| beancount/fava | 2,602 | 423 | 99 | 174 / 201 | not checked | active | MIT | Python | web UI for Beancount |
| moneymanagerex/moneymanagerex | 2,288 | 351 | 434 | 1,259 / 1,013 | 1.9.2 mentioned in a 2026-01-21 commit; exact latest unknown | active | GPL-2.0 | C++/wxWidgets | desktop (Win/macOS/Linux) |
| kevinschaich/mintable | 1,635 | n/a | n/a | not checked | not checked | push 2026-10-29 | MIT | TypeScript | CLI to spreadsheet |
| RIP-Comm/sossoldi | 1,416 | 218 | 31 | 331 / 88 | v1.0.0 (around 2026-08-20) | slowing | MIT | Dart/Flutter | mobile (Italian community) |
| whisper-money/whisper-money | 1,150 | 117 | n/a | 308 / 1,232 (created 2025-11-07) | not checked | active | NOASSERTION | PHP plus React | self-hosted web |
| OpenBudgeteer | 973 | n/a | n/a | not checked | not checked | push 2026-11-05 | AGPL-3.0 | C# | self-hosted web (envelope budgeting) |
| teelur/budget-board | 896 | 70 | n/a | not checked | not checked | active | AGPL-3.0 | C#/React | self-hosted web with bank sync |
| Cloeille/picsou-finance | 663 | 77 | n/a | not checked | not checked | new (created 2026-03-26) | NOASSERTION | Java | self-hosted dashboard (bank, brokerage, crypto) |
| budgetzero/budgetzero | 657 | 50 | 75 | 0 / 0 on default branch (push 2026-11-07 on another branch) | n/a | stagnant on main | AGPL-3.0 | Vue | local-first web |
| KDE/kmymoney (GitHub mirror) | 211 | 51 | 0 | 794 / 547 | not checked | active | GPL (no SPDX on the mirror) | C++/Qt | desktop |

- Repo metrics in the table above — [GitHub search API, repo pages: github.com/actualbudget/actual](https://github.com/actualbudget/actual), [firefly-iii](https://github.com/firefly-iii/firefly-iii), [we-promise/sure](https://github.com/we-promise/sure), [maybe-finance/maybe](https://github.com/maybe-finance/maybe), [ezbookkeeping](https://github.com/mayswind/ezbookkeeping), [Cashew](https://github.com/jameskokoska/Cashew), [ivy-wallet](https://github.com/Ivy-Apps/ivy-wallet), [gnucash](https://github.com/Gnucash/gnucash), [moneymanagerex](https://github.com/moneymanagerex/moneymanagerex), [sossoldi](https://github.com/RIP-Comm/sossoldi), [budgetzero](https://github.com/budgetzero/budgetzero), [akaunting](https://github.com/akaunting/akaunting), [beancount](https://github.com/beancount/beancount), [fava](https://github.com/beancount/fava), [hledger](https://github.com/hledgerorg/hledger), [ledger](https://github.com/ledger/ledger), [securo](https://github.com/securo-finance/securo), [BeeCount](https://github.com/TNT-Likely/BeeCount), [whisper-money](https://github.com/whisper-money/whisper-money), [paisa](https://github.com/ananthakumaran/paisa), [ghostfolio](https://github.com/ghostfolio/ghostfolio), [Wallos](https://github.com/ellite/Wallos), [kmymoney](https://github.com/KDE/kmymoney)
- Actual releases page lists v26.11.0 (02 Nov), 26.10.0 (02 Oct), 26.9.0 (01 Sep), 26.8.1 (07 Aug), 26.8.0 (02 Aug), 26.7.0, 26.6.0, 26.5.2, 26.5.1 and 26.5.0 (03 May). The page shows no year, but the 2026 release PRs confirm it (for example "update release branch (26.11.0)", merged 2026-10-26) — [Actual releases](https://github.com/actualbudget/actual/releases)
- Firefly III release-bot commits in 2026 run from v6.4.15 (2026-01-06) to v6.7.9 (2026-10-11), about 36 tags. Minor versions: 6.5.0 on 23 Feb, 6.6.0 on 19 Apr, 6.7.0 on 14 Sep — [firefly-iii commits](https://github.com/firefly-iii/firefly-iii/commits)
- GnuCash "Release GnuCash 5.15" (2026-03-28), "5.16" (2026-06-27) and "5.17" (2026-09-26) — [gnucash commits](https://github.com/Gnucash/gnucash/commits)
- ezBookkeeping "bump version to 2.2.0" (2026-10-23) and 10 more bumps in 2026. Commits on 2026-10-26 and 2026-11-02 mention a "desktop version" (support for adding multiple transactions, bundled libraries) — [ezbookkeeping commits](https://github.com/mayswind/ezbookkeeping/commits)
- Sure adopted CalVer release tagging on 2026-11-02 — [PR #4539](https://github.com/we-promise/sure/pull/4539), [PR #4704](https://github.com/we-promise/sure/pull/4704). An earlier pre-release, v0.7.2-alpha.3, shipped Android debug APKs and listed "Anthropic native PDF processing for AI imports" — [newreleases.io](https://newreleases.io/project/github/we-promise/sure/release/v0.7.2-alpha.3)
- Sure ships a Tauri desktop shell (`/desktop/src-tauri`), for example PR #4290 (2026-10-17) and "fix(desktop): save attachment downloads" PR #3571 (2026-09-15) — [PR #3571](https://github.com/we-promise/sure/pull/3571)
- Sossoldi "Add changelog for Sossoldi Version 1.0 release" and "Bump version to 1.0.0+105" (2026-08-20). Commit #536 (2026-09-12) is "feat(banking): add provider contracts and Enable Banking foundation" — [sossoldi commits](https://github.com/RIP-Comm/sossoldi/commits)
- hledger 1.99.6 is described as "released and announced" in repo docs commits dated 2026-11-01 — [hledger commits](https://github.com/hledgerorg/hledger/commits)

**Sync, bank connections and AI** (only what was evidenced):
- Actual: GoCardless was being discontinued, so Actual added Enable Banking ([#5505](https://github.com/actualbudget/actual/issues/5505), 23 👍). The "Enable Banking bank sync provider" feedback issue is the most-commented open issue, with 187 comments ([#7799](https://github.com/actualbudget/actual/issues/7799)). SimpleFIN is also supported ([#2272](https://github.com/actualbudget/actual/issues/2272), 203 comments). I found no AI-categorization feature. Actual marks AI-assisted PRs with an "[AI]" title prefix, for example "[AI] Release 26.5.2".
- Firefly III: the Data Importer supports SimpleFIN ([#5396](https://github.com/firefly-iii/firefly-iii/issues/5396)) and Enable Banking ([#10753](https://github.com/firefly-iii/firefly-iii/issues/10753), and [#13005](https://github.com/firefly-iii/firefly-iii/issues/13005) / [#13074](https://github.com/firefly-iii/firefly-iii/issues/13074) in Oct 2026). It also imports CAMT.052 ([#13127](https://github.com/firefly-iii/firefly-iii/issues/13127)). An "LLM integration for auto-categorization" request was closed ([#9753](https://github.com/firefly-iii/firefly-iii/issues/9753)). I found no native AI.
- Sure: many AI PRs were merged in Oct 2026, including an AI assistant sidebar, "Dig in with AI" insights, a native Anthropic provider, a Gemini model, an `LLM_PROVIDER` setting, and AI jobs in their own Sidekiq capsule ([#4239](https://github.com/we-promise/sure/pull/4239), [#4243](https://github.com/we-promise/sure/pull/4243), [#4249](https://github.com/we-promise/sure/pull/4249), [#4237](https://github.com/we-promise/sure/pull/4237)). The search found 84 merged PRs matching AI/LLM/ollama. Sync providers include Enable Banking, SnapTrade (#4404), Wise (#4166) and Trade Republic ([#392](https://github.com/we-promise/sure/issues/392)). It also exposes an MCP endpoint (#4780).
- ezBookkeeping: AI receipt-image recognition with bring-your-own LLM (OpenAI, Anthropic, Google, Ollama, LM Studio, per a third-party directory). It supports MCP. Import formats are CSV, OFX, QFX, QIF, IIF, CAMT.052/053, MT940, and GnuCash/Firefly/Beancount files. It does not connect to banks — [pkg.go.dev listing](https://pkg.go.dev/github.com/wbchn/ezbookkeeping), [SourceForge](https://sourceforge.net/projects/ezbookkeeping/), [openapps.pro (lower reliability)](https://openapps.pro/apps/ezbookkeeping)
- Securo: self-hosted and AGPL-3.0. Optional bank sync uses Pluggy, Enable Banking and SimpleFIN with your own credentials. Imports OFX, QIF, CAMT and CSV. Runs as six Docker containers — [Unraid listing](https://ca.unraid.net/apps/securo-0m6ajr11hc1615), [Railway](https://railway.com/deploy/securo), [OpenAlternative](https://openalternative.co/securo)
- BeeCount describes itself as "Local-first bookkeeping for iOS/Android/Web · Self-hosted cloud + iCloud/WebDAV/S3 sync · AI capture · MCP" — [BeeCount](https://github.com/TNT-Likely/BeeCount)

### Inferences
- The OSS apps that now compete most directly with MyFinancePlace's feature set are **Sure** (web, desktop and mobile, an AI assistant, investments, EU bank sync) and **ezBookkeeping** (MIT, AI receipt OCR, CAMT/MT940 import, a new desktop version, no bank sync). Both moved toward desktop or AI in 2026.
- The popular OSS apps answer bank sync with aggregators (Enable Banking now standard after GoCardless closed new sign-ups). None of them offers bank-specific Italian Excel/PDF parsers.

### Gaps
- Contributor counts: the contributors API was blocked, so I have no numbers.
- Exact latest release tag and date for Sure, MMEX, KMyMoney, Akaunting, Beancount, Fava, Ledger, Securo, BeeCount and Paisa: the releases API was blocked and the pages timed out.
- HomeBank is not on GitHub (it is developed on Launchpad), so I have no metrics for it. Searching found only third-party converters such as dkb2homebank (45 stars).
- I found no maintained OSS "Bluecoins-like" project. Cashew is the closest in UX, and it is dormant.
- KMyMoney's GitHub mirror stars (211) do not reflect its real user base. Development happens on invent.kde.org.

## Q2. Most-upvoted and most-commented issues and feature requests (Actual, Firefly III, Sure, ezBookkeeping)

### Takeaway
In Actual, the historic top requests are budget goals, transfer detection, multi-currency, subcategories, Plaid, multi-user and attachments, and most of them are now closed or implemented. Current debate is about Enable Banking sync, budget automation, formulas and the Sankey chart. Firefly users ask for OIDC, more bank aggregators (Teller, Basiq), QIF/OFX, installments and an import dry run. Sure users ask for future-dated transactions, the Powens aggregator, FX overrides, **loan amortization schedules**, i18n and budget rollover. ezBookkeeping users ask for shared accounts.

### Cited Findings
**Actual (all states, by 👍):**
- [#496](https://github.com/actualbudget/actual/issues/496) Budget goals UI: 504 👍, closed
- [#1628](https://github.com/actualbudget/actual/issues/1628) Bank sync, recognise transfers between accounts: 388 👍
- [#1132](https://github.com/actualbudget/actual/issues/1132) Budget currency and category currencies (multi-currency): 349 👍, 74 comments
- [#1320](https://github.com/actualbudget/actual/issues/1320) Subcategories: 344 👍
- [#898](https://github.com/actualbudget/actual/issues/898) Plaid integration: 328 👍
- [#524](https://github.com/actualbudget/actual/issues/524) Multi-user: 316 👍
- [#530](https://github.com/actualbudget/actual/issues/530) Attachments: 214 👍
- [#2042](https://github.com/actualbudget/actual/issues/2042) 2FA/passkeys: 184 👍
- [#730](https://github.com/actualbudget/actual/issues/730) Custom reports: 163 👍
- [#5606](https://github.com/actualbudget/actual/issues/5606) Native mobile apps for iOS/Android (2025-08-22): 28 👍, closed

**Actual (open, most commented):**
- [#7799](https://github.com/actualbudget/actual/issues/7799) Enable Banking provider feedback: 187 comments
- [#7692](https://github.com/actualbudget/actual/issues/7692) Budget automation UI: 164
- [#5949](https://github.com/actualbudget/actual/issues/5949) Formula card and formula rules: 112 comments, 12 👍
- [#1919](https://github.com/actualbudget/actual/issues/1919) Sankey chart: 97 comments, 11 👍
- [#5191](https://github.com/actualbudget/actual/issues/5191) Currency symbol support: 71
- [#3606](https://github.com/actualbudget/actual/issues/3606) Rule action templating: 67 comments, 12 👍
- [#5950](https://github.com/actualbudget/actual/issues/5950) Frontend plugins: 13 👍

**Firefly III (open, by 👍):**
- [#10662](https://github.com/firefly-iii/firefly-iii/issues/10662) OIDC: 37 👍
- [#8598](https://github.com/firefly-iii/firefly-iii/issues/8598) Teller.io: 15
- [#4917](https://github.com/firefly-iii/firefly-iii/issues/4917) Template transactions: 14
- [#5265](https://github.com/firefly-iii/firefly-iii/issues/5265) Money transfer fees: 13
- [#7790](https://github.com/firefly-iii/firefly-iii/issues/7790) Basiq US importer: 11 👍, 30 comments
- [#10073](https://github.com/firefly-iii/firefly-iii/issues/10073) Credit-card monthly installments: 10
- [#8687](https://github.com/firefly-iii/firefly-iii/issues/8687) Import preview / dry run: 10
- [#9209](https://github.com/firefly-iii/firefly-iii/issues/9209) QIF/QFX import: 10
- [#3718](https://github.com/firefly-iii/firefly-iii/issues/3718) OFX support: 11 comments
- [#13127](https://github.com/firefly-iii/firefly-iii/issues/13127) CAMT.052 ultimate creditor: 16 comments (Oct 2026)
- Historic top (closed): [#5396](https://github.com/firefly-iii/firefly-iii/issues/5396) SimpleFIN (28 👍, 68 comments) and [#5532](https://github.com/firefly-iii/firefly-iii/issues/5532) asset prices and exchange rates (20 👍)
- A security event: [#13087](https://github.com/firefly-iii/firefly-iii/issues/13087) "[PHP] CVE-2026-109618 & CVE-2026-109619" (2026-10-21, 12 👍)

**Sure (by 👍, all states):**
- [#33](https://github.com/we-promise/sure/issues/33) European bank provider: 12 👍, closed
- [#392](https://github.com/we-promise/sure/issues/392) Trade Republic sync: 11 👍, 21 comments
- [#34](https://github.com/we-promise/sure/issues/34) OIDC: 10
- Open:
  - [#1080](https://github.com/we-promise/sure/issues/1080) Future budget/transactions: 7
  - [#3065](https://github.com/we-promise/sure/issues/3065) Powens API: 6
  - [#2417](https://github.com/we-promise/sure/issues/2417) FX rate override, and stop converting silently at 1.0: 5
  - [#1804](https://github.com/we-promise/sure/issues/1804) **Native amortization schedules for loan accounts**: 5
  - [#1362](https://github.com/we-promise/sure/issues/1362) i18n rework: 4 👍, 23 comments
  - [#3544](https://github.com/we-promise/sure/issues/3544) Budget rollover with negative carry: 4
  - [#1696](https://github.com/we-promise/sure/issues/1696) Multiple ledgers: 3
- Most commented open:
  - [#10](https://github.com/we-promise/sure/issues/10) Net worth calculation incorrect: 26
  - [#88](https://github.com/we-promise/sure/issues/88) Confusing totals due to sync: 24
  - [#641](https://github.com/we-promise/sure/issues/641) Mint/YNAB import: 21
  - [#1204](https://github.com/we-promise/sure/issues/1204) Attachments into a vector store for AI: 18

**ezBookkeeping:**
- [#53](https://github.com/mayswind/ezbookkeeping/issues/53) Shared/co-owned accounts: 32 👍, 14 comments
- [#343](https://github.com/mayswind/ezbookkeeping/issues/343) Create a category on the fly: 6 👍
- Low-reaction items: [#675](https://github.com/mayswind/ezbookkeeping/issues/675) inflation adjustment, [#629](https://github.com/mayswind/ezbookkeeping/issues/629) file attachments, [#684](https://github.com/mayswind/ezbookkeeping/issues/684) CSV export bug

### Inferences
- Several recurring themes match MyFinancePlace's strengths: correct multi-currency/FX, loan amortization (Sure #1804), import preview or dry run (Firefly #8687), CAMT/OFX/QIF import and attachments.
- Sure issues #10 and #88 show that sync-driven numbers erode trust. That supports MyFinancePlace's file-import, no-sync stance.

### Gaps
- Actual moves feature requests out of open issues once they are triaged, so open-issue reactions understate demand. I did not check GitHub Discussions.

## Q3. Growth vs stagnation; notable 2025–2026 events

### Takeaway
Growing: Sure, Firefly III, hledger, Ledger (revived), GnuCash (more commits), Ghostfolio, Akaunting, and newcomers Securo, whisper-money and BeeCount. Flat but healthy: Actual, ezBookkeeping, MMEX. Stagnating or dead: Maybe (archived Jul 2025), Ivy Wallet (archived), Cashew (dormant), budgetzero (no default-branch commits), Beancount core (low), Sossoldi (commits fell from 331 to 88).

### Cited Findings
- Maybe is archived, with its last push on 2025-07-24. Sure was created on 2025-07-23 as the community fork and reached 11,191 stars by 2026-11-09. Its default-branch commits grew from 881 (2025, from Jul) to 2,321 (2026 YTD) — [maybe](https://github.com/maybe-finance/maybe), [sure](https://github.com/we-promise/sure)
- Securo was created on 2026-03-08 and reached 4,244 stars, 603 forks and 698 commits by 2026-11-09 — [securo](https://github.com/securo-finance/securo)
- whisper-money was created on 2025-11-07: 1,150 stars, with commits going from 308 to 1,232 — [whisper-money](https://github.com/whisper-money/whisper-money). BeeCount was created on 2025-09-06: 2,763 stars — [BeeCount](https://github.com/TNT-Likely/BeeCount). picsou-finance was created on 2026-03-26: 663 stars — [picsou](https://github.com/Cloeille/picsou-finance)
- Default-branch commits, 2025 to 2026 YTD:
  - Firefly III: 2,063 to 2,621
  - Actual: 1,326 to 1,350
  - GnuCash: 487 to 1,009
  - hledger: 1,209 to 2,310
  - Ledger: 218 to 1,861
  - Akaunting: 185 to 610
  - ezBookkeeping: 971 to 807
  - MMEX: 1,259 to 1,013
  - KMyMoney: 794 to 547
  - Sossoldi: 331 to 88
  - Cashew: 1 to 1
  - Ivy Wallet: 4 to 2 (archived)
  - budgetzero: 0 to 0
  - (all from GitHub search/commits; see the repo links in Q1)
- hledger moved from `simonmichael/hledger` to the `hledgerorg/hledger` org (the old path is no longer searchable) — [hledgerorg/hledger](https://github.com/hledgerorg/hledger)
- GoCardless Bank Account Data was being discontinued, which pushed Actual ([#5505](https://github.com/actualbudget/actual/issues/5505)), Firefly ([#10753](https://github.com/firefly-iii/firefly-iii/issues/10753)) and Sure ([#33](https://github.com/we-promise/sure/issues/33)) to Enable Banking.
- serversideup/financial-freedom (2,951 stars) is archived — GitHub search API, [repo](https://github.com/serversideup/financial-freedom)
- In the topic:personal-finance search, Securo, whisper-money and itr-wala (an Indian tax tool created 2026-07, 885 stars) appeared as new entries — [GitHub topic personal-finance](https://github.com/topics/personal-finance)

### Inferences
- Star growth over time could not be measured (no star-history access). New-project growth is inferred from stars accumulated since creation: Sure averaged about 700 stars/month and Securo about 530 stars/month. Those are the fastest-growing budgeting apps of 2025–2026.
- Sure changed its versioning (CalVer, Nov 2026) and added desktop and mobile builds. It is positioning as a full multi-platform product.

### Gaps
- I could not reach star-history.com or ossinsight, so I have no monthly star series.
- I found no evidence of relicensing or acquisitions in 2025–2026 beyond the Maybe archival and fork. I did not verify whether Maybe's company announced anything new.

## Q4. European/Italian statements, CAMT/OFX, PDF, AI-based import

### Takeaway
CAMT/MT940/OFX import is common: Firefly Data Importer, ezBookkeeping and Securo have it, and GnuCash/KMyMoney/MMEX support OFX/QIF. AI or PDF statement import has so far been seen only in Sure (Anthropic native PDF processing for AI imports) and ezBookkeeping (receipt images). Italian banks show up only as Enable Banking sync bugs, not as dedicated file parsers.

### Cited Findings
- Italian-bank mentions across the main repos (17 issues in total) are all aggregator sync problems:
  - Intesa Sanpaolo loop with GoCardless in Actual ([#4287](https://github.com/actualbudget/actual/issues/4287))
  - Isybank (IT) Enable Banking 422 error in Sure ([#2918](https://github.com/we-promise/sure/issues/2918))
  - Banco BPM 429 errors in Sure ([#3133](https://github.com/we-promise/sure/issues/3133))
  - Enable Banking certificate error in Sure ([#3392](https://github.com/we-promise/sure/issues/3392))
- Firefly CAMT.052 import refinement in Oct 2026 — [#13127](https://github.com/firefly-iii/firefly-iii/issues/13127). OFX is still an open request in the core app — [#3718](https://github.com/firefly-iii/firefly-iii/issues/3718)
- ezBookkeeping imports CSV, OFX, QFX, QIF, IIF, CAMT.052/053 and MT940, and recognizes receipt images with AI — [pkg.go.dev](https://pkg.go.dev/github.com/wbchn/ezbookkeeping), [SourceForge](https://sourceforge.net/projects/ezbookkeeping/)
- Securo imports OFX, QIF, CAMT and CSV — [Unraid listing](https://ca.unraid.net/apps/securo-0m6ajr11hc1615)
- Sure's "Anthropic native PDF processing for AI imports" — [newreleases.io v0.7.2-alpha.3](https://newreleases.io/project/github/we-promise/sure/release/v0.7.2-alpha.3). Its AI runs on cloud LLM providers (Anthropic, OpenAI, Gemini, via `LLM_PROVIDER`) — [PR #4249](https://github.com/we-promise/sure/pull/4249)
- Sossoldi, the Italian-community mobile app, began adding Enable Banking in Sep 2026 — [sossoldi commits](https://github.com/RIP-Comm/sossoldi/commits)

### Inferences
- MyFinancePlace's Italian bank-specific Excel/PDF/OCR parsers plus *local* AI categorization remain unmatched in the OSS set. The nearest are Sure's cloud-LLM PDF import and ezBookkeeping's BYO-LLM, which can include Ollama.

### Gaps
- I did not verify whether Sure's PDF import supports local models (Ollama). The GitHub search for "ollama" in Sure needed a narrower query and returned only general AI PRs.
- I did not check the import formats of Actual (it is known to do OFX/QFX/CAMT/CSV, but that was not verified in this session), GnuCash, KMyMoney or MMEX.
