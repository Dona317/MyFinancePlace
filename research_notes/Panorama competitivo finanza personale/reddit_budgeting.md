# Reddit on personal-finance budgeting apps (2025–2026)

> **ACCESS LIMITATION. Read this first.** This session could not reach Reddit at all:
> - WebSearch refuses `reddit.com` as a domain ("not accessible to our user agent").
> - Direct HTTPS to `www.reddit.com` and `old.reddit.com` (including `.json` endpoints) was refused by the session's egress proxy (CONNECT 403).
> - WebFetch could not resolve any mirror or aggregator host tried: `reddit.sentinel-team.org`, `libreddit.winscloud.net`, `getfinny.app`, `redditsearchapi.z13.web.core.windows.net`, `gummysearch.com`. All failed with ENOTFOUND, which here means the host is outside the session's allowed network.
>
> As a result, **no Reddit thread was opened and no quote below has been checked against its page.** Everything here comes from search-engine result snippets and summaries of them. Short quoted fragments are the search tool's rendering of page text and may be trimmed or paraphrased. Upvote and comment counts could not be seen. Treat this file as a **lead list plus secondary signal**, not as verified Reddit evidence. Getting the requested deliverable (verbatim, dated quotes with permalinks and engagement) needs one of two things: allow `reddit.com`/`old.reddit.com`, or a Redlib mirror host, in the session's network settings; or a human pastes the threads in.

## 1. Which apps people use, recommend and switch between (YNAB, Monarch, Copilot, Actual, etc.)

### Takeaway
Secondary sources agree the default Reddit recommendations are YNAB for hands-on zero-based budgeting and Monarch for the Mint-like "sync everything, see dashboards" crowd. Copilot is the Apple-only, design-led option, Tiller and spreadsheets serve the DIY crowd, and Actual Budget is the self-hosted or free YNAB clone. Mint refugees mostly landed in Monarch, with Tiller and spreadsheets for power users. YNAB-to-Monarch moves sometimes reverse, because Monarch's budget "isn't tied to real money".

### Cited Findings
- r/ynab thread "YNAB pricing history 2016–2025" (posted 7 Feb 2025). The poster was at a renewal date, and commenters weighed whether YNAB was still worth paying for. Engagement not visible. Original ID `1ik8su5`, so the permalink is https://www.reddit.com/r/ynab/comments/1ik8su5/ (seen via a Libreddit mirror in search results) — [mirror](https://libreddit.winscloud.net/r/ynab/comments/1ik8su5/ynab_pricing_history_2016_2025)
- r/ynab, July 2024 (just outside the window, useful context). A user notes YNAB "increased their prices significantly (like 20%) only two years ago… Now they're rolling out another increase" — [mirror](https://reddit.birdcat.cafe/r/ynab/comments/1dtlg6t/i_truely_do_not_understand_peoples_obsession_with)
- r/ynab thread titled "My YNAB hot take: the price is perfectly reasonable" (ID `1f3hy2s`, ~Aug/Sep 2024). It shows a vocal pro-price camp exists — [mirror](https://lr.in.psf.lt/r/ynab/comments/1f3hy2s/my_ynab_hot_take_the_price_is_perfectly_reasonable)
- YNAB price history: $83.99 to $98.99/yr announced Nov 2021 (+18%, one month's notice). Later increases followed. The source is a competitor's blog — [Pocket Clear](https://pocketclear.app/blog/ynab-price-increases-history.html)
- Alternatives r/ynab users name in pricing threads: Aspire (free Google Sheets template), described as "a good alternative to just using basic spreadsheets, but has a bit of a learning curve too", and PocketSmith. Several users say they found no comparable zero-based alternative — [search summary of r/ynab mirrors](https://lr.us.psf.lt/r/ynab/comments/qkf8fl/jumping_ship_due_to_ynab_price_increase)
- r/ynab has about 205,000 members — [NerdWallet](https://www.nerdwallet.com/finance/learn/ynab-app-review)
- Switching back from Monarch to YNAB. The blogger's main complaint is that Monarch budget targets aren't tied to real money, though they credit Monarch's syncing and investment tracking. This is a blog, not Reddit — [azzysays](https://www.azzysays.com/post/i-tried-monarch-money-and-went-back-to-ynab)
- Tiller is "especially popular with Mint refugees who had built complex custom spreadsheets". The same review quotes a Reddit user who found it "a little too much DIY" and mentions there is no mobile app. The Reddit quote is secondhand and has no link — [FinCompareLab Tiller review](https://www.fincomparelab.com/reviews/tiller-money-review/)
- A 2026 r/selfhosted user (via a snapshot site) moved from Firefly III to Actual Budget because "Actual Budget is closer to Mint or YNAB, a budgeting program first and foremost". Snapshot host unreachable, and the original post ID is unknown (possibly `1rca9ar` or `1r937vj`, Feb 2026) — [snapshot](https://reddit.sentinel-team.org/posts/1rca9ar/snapshots/2026-02-23T11%3A13%3A15.091724Z)
- Aggregator summaries of Reddit: "Monarch Money delivers" for people willing to pay; Goodbudget for beginners; one Reddit quote praises the free EveryDollar version; Copilot is "the most beautifully designed budgeting app with AI-powered categorization" (Apple only). This is a promotional blog — [getfinny.app](https://getfinny.app/blog/best-budget-apps-reddit-recommends-2026)
- UK: Emma is named as the app most often recommended on UK personal-finance forums. The claim comes from a competitor and is unverified against Reddit. Snoop, Money Dashboard, Plum and in-bank budgeting in Monzo are also cited — [earmarkIQ](https://earmarkiq.app/blog/best-budgeting-apps-uk); [Finder](https://www.finder.com/uk/budgeting/emma-review)

### Inferences
- The market splits into two camps: method-first apps (YNAB, Actual) and visibility-first apps (Monarch, Copilot, Empower). MyFinancePlace offers budget, reports and forecasts, so it has to decide which camp it speaks to. Users who moved from Monarch back to YNAB show that a "budget not tied to real money" approach loses the disciplined users.
- Mint refugees who don't want subscriptions tend to end up in spreadsheets or Tiller. That group matches a local app with file import.

### Gaps
- No verbatim, dated r/mintuit, r/MonarchMoney, r/personalfinance or r/budget quotes could be retrieved (blocked).
- No upvote or comment counts for any thread.
- I couldn't check Lunch Money, PocketSmith, Simplifi, Rocket Money or Empower sentiment on Reddit.

## 2. Pain points: pricing, bank sync, privacy, manual entry, categorization, multi-currency, couples, desktop/offline, AI

### Takeaway
The recurring complaints in secondary sources are subscription price creep (YNAB's repeated increases, and Monarch adding a $199.99 Plus tier above the $99.99 Core) and sync reliability. Sync breakage is "the most common complaint" about aggregator apps. Europe has a structural sync problem: GoCardless (ex-Nordigen) stopped accepting new Bank Account Data sign-ups in July 2025, which removed the free EU bank-sync route for Actual, Firefly III and others. Privacy concerns centre on handing bank credentials to aggregators and on cloud LLMs seeing transactions.

### Cited Findings
- GoCardless: "From July 2025 onwards, GoCardless has stopped accepting new Bank Account Data accounts… if you are an existing user, your account should continue to work." — [Actual Budget docs](https://actualbudget.org/docs/advanced/bank-sync/gocardless/)
- Sync: "sync reliability is the most common complaint about Monarch — and about most aggregator-based budgeting apps in general". Connections break when the provider "stops trusting the saved login session". One user reported only 3 re-authentications in 9 months — [envelopebudgeting.com](https://envelopebudgeting.com/articles/monarch-money-review)
- Monarch has a Trustpilot rating of about 2.2/5, with negative reviews mostly about connections and sync. Cancellations reportedly cluster around price rather than quality. Secondary source — [search summary of Monarch 2026 reviews](https://usetweed.com/blog/monarch-money-review/)
- Monarch pricing in 2026: Core is still $99.99/yr ($14.99/mo), plus a new Plus tier at ~$199.99/yr — [NerdWallet](https://www.nerdwallet.com/finance/learn/best-budget-apps?advid=2); [usetweed](https://usetweed.com/blog/monarch-money-review/)
- A Monarch Black Friday 2025 deal at $50/yr. A commenter says they "try to cancel their annual plan and select 'too expensive' and they get 50% off on renewal". That shows price sensitivity and retention-discount gaming (Slickdeals, not Reddit) — [Slickdeals](https://slickdeals.net/f/18895087-monarch-black-friday-code-50-yr)
- Couples: YNAB "changes between partners don't sync in real-time (can cause conflicts)" — [Beancount forum](https://beancount.io/forum/t/copilot-vs-monarch-vs-ynab-which-premium-budget-app-is-worth-it/98)
- Copilot sync is "a bit spotty for things like your Amazon account but no problem with credit card/bank accounts". This is from Blind, not Reddit — [Blind](https://teamblind.com/post/co-pilot-vs-monarch-vs-ynab-and-why-uhixrv6o)
- Tiller: bank syncing stops when the subscription lapses, but data already in the sheet remains. Price is reported as $79/yr (Tiller, Fortune) versus $99/yr elsewhere, which is conflicting — [FinancialAha](https://www.financialaha.com/articles/the-best-personal-finance-spreadsheets-for-2026-free-paid/); [Fortune](https://fortune.com/2020/11/08/personal-finance-budget-pps-tiller-spreadsheet)
- AI and privacy: Monarch has said it uses "a mix of third-party large language models and in-house models" for its AI Assistant, insights, receipt scanning and categorization, so transaction text can leave the user's control — [finclash](https://finclash.com/best-ai-budgeting-apps/)
- Statement upload instead of a bank login is being marketed as the privacy answer. Example: RetroBudget, "Your statements are processed and then deleted" (developer claim) — [App Store](https://apps.apple.com/us/app/-/id6743363764)
- Local LLM categorization through Ollama, with low temperature "for consistent, deterministic categorization", exists as hobby projects — [local-llms-analyse-finance writeup](https://converter.brightcoding.dev/blog/local-llms-analyse-finance-your-private-ai-budget-assistant); [Medium](https://padulaguruge.medium.com/analyzing-personal-finances-locally-with-ai-using-llms-and-python-panel-for-secure-expense-eb0f3831517c)

### Inferences
- GoCardless closing in July 2025 is a strong tailwind for MyFinancePlace's "manual/file import, no bank sync" approach in the EU. The free sync option for new self-hosters is gone, so good CSV, OFX or PDF import becomes the main path rather than a fallback.
- AI categorization done locally, without sending transactions to third-party LLMs, sets the product apart from Monarch and Copilot, which use cloud models.
- Couples and shared budgets are a known weak spot even for YNAB.

### Gaps
- No direct Reddit quotes on Plaid or SimpleFIN breakage, data selling, manual entry burden, multi-currency pain or the lack of desktop/offline apps. All searches returned only blogs.
- I couldn't confirm whether Reddit sees AI features as useful or a gimmick. No Reddit thread was reachable.

## 3. Most requested features and willingness to pay (one-time vs subscription, price points)

### Takeaway
The price points cited are YNAB at ~$99/yr (after earlier rises from $83.99), Monarch Core at $99.99/yr with Plus at $199.99, and Tiller at $79–99/yr. Free or one-time options keep coming up: Aspire and other free sheet templates, one-time-purchase templates, and Actual Budget (free, self-hosted). Monarch users accepting $50/yr discounts and cancelling to get 50% off point to a soft ceiling below $100/yr for many people. I found no Reddit-sourced figure for an acceptable one-time price.

### Cited Findings
- YNAB at $98.99/yr since 2021, with later increases discussed in r/ynab in 2024–2025 — [Pocket Clear](https://pocketclear.app/blog/ynab-price-increases-history.html); [r/ynab mirror, Feb 2025](https://libreddit.winscloud.net/r/ynab/comments/1ik8su5/ynab_pricing_history_2016_2025)
- Monarch at $99.99/yr or $14.99/mo, with Plus at ~$199.99/yr — [NerdWallet](https://www.nerdwallet.com/finance/learn/best-budget-apps?advid=2)
- Monarch Black Friday at $50/yr, and cancel-for-50%-off behaviour — [Slickdeals](https://slickdeals.net/f/18895087-monarch-black-friday-code-50-yr)
- One-time-purchase spreadsheet templates and free templates (Aspire, Mad Fientist) as subscription-free options — [FinancialAha](https://www.financialaha.com/articles/the-best-personal-finance-spreadsheets-for-2026-free-paid/)
- Feature gaps named for Emma: salary allocation, price-creep detection, a contextual AI advisor, partner finances. The source is a competitor — [earmarkIQ](https://earmarkiq.app/blog/best-budgeting-apps-uk)

### Inferences
- A one-time price, or a low annual price well under $99, would undercut the anchor that YNAB and Monarch set. "No subscription, no lapse-kills-sync" fits a local app naturally.

### Gaps
- I couldn't retrieve a Reddit "most requested features" list or Reddit statements of an acceptable one-time price (blocked).

## 4. Self-hosted view: Actual vs Firefly III vs Sure vs ezBookkeeping

### Takeaway
The consensus in secondary sources, consistent with the one Reddit snippet I saw, is that Actual is a budgeting-first YNAB clone: easy, SQLite, envelope budgeting, weaker multi-currency. Firefly III is a full accounting system: powerful, strong multi-currency and rules, but a steep learning curve, a separate data importer, a MySQL/Postgres database, no official mobile app, and heavier on RAM. Sure, the community fork of Maybe Finance, is the new entrant and is mentioned in 2026 multi-currency threads alongside Firefly and Actual, but has no detailed reviews yet. ezBookkeeping is lightweight (it runs on a Raspberry Pi) but lacks budgeting.

### Cited Findings
- A 2026 r/selfhosted multi-currency request thread got replies naming "Firefly III, Actual, and Sure" as the contenders (snapshot, unreachable) — [snapshot](https://reddit.sentinel-team.org/posts/1r937vj/snapshots/2026-02-20T00%3A40%3A39.803757Z)
- A user moved from Firefly to Actual because Actual is "a budgeting program first and foremost" (2026, snapshot) — [snapshot](https://reddit.sentinel-team.org/posts/1rca9ar/snapshots/2026-02-23T11%3A13%3A15.091724Z)
- Earlier r/selfhosted threads (2024, outside the window): "Does the world need another selfhosted budgeting app?" and "Personal finances app discussion" — [mirror 1](https://redlib.hyperreal.coffee/r/selfhosted/comments/1cvp5uz/does_the_world_need_another_selfhosted_budgeting); [mirror 2](https://redlib.hyperreal.coffee/r/selfhosted/comments/1adnffd/personal_finances_app_discussion/kk2shka/?context=3)
- Firefly III needs a separate data importer service, has a steep learning curve and no official mobile app. One author's setup pushed a Hetzner CX22 to ~70% RAM. Actual uses SQLite, while Firefly needs MySQL/Postgres. Actual's zero-based method "changed habits" more than Firefly's after-the-fact charts (one person's opinion) — [selfhostable.dev](https://selfhostable.dev/blog/firefly-iii-vs-actual-budget-self-hosted-finance/)
- Fit: Firefly suits people with 50+ daily transactions who want automation, and Actual suits people who check weekly and batch-import — [selfhosted-sh](https://selfhosted-sh.pages.dev/actual-budget-vs-firefly-iii)
- Multi-currency: Firefly has "first-class multi-currency support with exchange rate handling", and Actual's is "more basic". Sources conflict on whether Actual supports it at all — [talos.tools](https://talos.tools/compare/firefly-iii-vs-actual-budget); contradicted in part by [ezBookkeeping comparison (vendor)](https://ezbookkeeping.mayswind.net/comparison/)
- Bank sync: Actual supports SimpleFIN (US/CA) and GoCardless (EU, now closed to new sign-ups) — [Actual docs](https://actualbudget.org/docs/advanced/bank-sync/gocardless/)
- ezBookkeeping has ~5.9k GitHub stars against Firefly's ~25k but is growing faster in percentage terms. It is notably missing budgeting and is light enough for a Raspberry Pi — [OpenAlternative](https://openalternative.co/compare/ezbookkeeping/vs/firefly-iii)
- Sure (sure.am) is listed among Firefly alternatives together with Actual, ezBookkeeping and Maybe — [OpenAlternative](https://openalternative.co/alternatives/firefly-iii)

### Inferences
- Self-hosters don't have a tool that is easy like Actual and also multi-currency and reporting-strong like Firefly, without running a server. A local desktop app (no Docker, no DB server) that offers budgets plus forecasts plus good import could fill that gap.

### Gaps
- No verbatim r/selfhosted, r/actualbudget or r/FireflyIII complaint quotes with dates or engagement (blocked). No user sentiment found on Sure or ezBookkeeping.
