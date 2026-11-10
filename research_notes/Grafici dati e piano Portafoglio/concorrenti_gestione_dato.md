# Gestione del dato nei concorrenti (stato al 9 novembre 2026)

Metodo e affidabilità. Codice sorgente clonato il 9 nov 2026 (`git clone --depth 1`): Actual Budget (ultimo commit 9 nov 2026, release corrente 26.11.0), Sure (9 nov 2026), ezBookkeeping (9 nov 2026), Firefly III (26 ott 2026) e Wealthfolio (8 nov 2026; il repo ora si chiama `wealthfolio/wealthfolio`). Le issue con più reazioni vengono da `gh api search/issues`. Durante la sessione non si potevano raggiungere questi domini: docs.firefly-iii.org, support.lunchmoney.app, support.ynab.com, gethomebank.org e Reddit. Per GnuCash, Beancount/Fava, hledger, Money Manager Ex, HomeBank, YNAB e Monarch molti dati vengono quindi da conoscenze precedenti (fino a giugno 2026), che **non ho ricontrollato**. Nella matrice li segno con **(K)**. Ciò che ho verificato in questa sessione, nel codice o nella documentazione ufficiale, è segnato **(V)**.

## Domanda 1: come ogni app gestisce ciascuna capacità (matrice e implementazioni migliori)

### Takeaway
Fra le app open source, quelle più complete sul dato importato sono Sure ed ezBookkeeping. Sure ha import PDF via AI con revert, un classificatore Bayes locale, abbinamento automatico dei trasferimenti con tolleranza sul cambio e un server MCP con circa 50 tool. ezBookkeeping importa circa 20 formati (CAMT, MT940, OFX, QIF, IIF, GnuCash, Beancount, Firefly III, Alipay/WeChat), ha preset di import salvati, OCR degli scontrini via LLM (anche Ollama/LM Studio), cambi dalla Banca d'Italia e un server MCP. Actual resta il riferimento per regole auto-apprese, deduplica fuzzy, riconciliazione e undo/redo. **Actual non ha ancora una multi-valuta nativa.**

### Cited Findings

**Actual Budget (local-first + sync server opzionale)**
- Import da file: CSV, QIF, OFX, QFX e CAMT. La mappatura CSV prevede scelta delle colonne, formato data, delimitatore, "Flip amount", split inflow/outflow e "Multiply amount", con anteprima nel dialogo — [Actual docs: importing](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/transactions/importing.md) (V)
- Il parser smista per estensione `.qif/.csv/.tsv/.ofx/.qfx/.xml` (`.xml` = CAMT). Il codice nota che camt.052/054 importano tutte le voci senza filtrare BOOK/PDNG — [parse-file.ts](https://github.com/actualbudget/actual/blob/master/packages/loot-core/src/server/transactions/import/parse-file.ts), [xmlcamt2json.ts](https://github.com/actualbudget/actual/blob/master/packages/loot-core/src/server/transactions/import/xmlcamt2json.ts) (V)
- Deduplica in due passi: (1) `imported_id` (FITID OFX); (2) fuzzy match su stessa cifra, payee simile e data entro ±7 giorni, con i candidati ordinati per distanza di data. Vince sempre la transazione importata, la cui data sovrascrive quella manuale. C'è l'opzione "Reimport deleted transactions" — [importing.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/transactions/importing.md); [sync.ts](https://github.com/actualbudget/actual/blob/master/packages/loot-core/src/server/accounts/sync.ts) (V)
- Regole: condizioni→azioni, eseguite in tre stage (`pre`/`default`/`post`). Dentro uno stage il ranking va dal meno al più specifico ("is" batte "contains"), con regex e `imported payee` distinto da `payee`. **Regole auto-create**: rinominare un payee propone una regola `pre`; categorizzare più volte lo stesso payee crea una regola di categoria — [rules docs](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/budgeting/rules/index.md) (V)
- Rule action templating e formule sono ancora sperimentali (issue di feedback #3606: 21 reazioni, la più votata fra le aperte; #5949: 13) — ricerca issue GitHub `repo:actualbudget/actual is:open` (V)
- Riconciliazione: stati cleared/uncleared, totali cleared e uncleared, strumento con lucchetto che calcola la differenza dal saldo della banca, "Use last synced total" e blocco delle transazioni riconciliate — [reconciliation.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/accounts/reconciliation.md) (V)
- Undo/redo con Ctrl+Z/Ctrl+Shift+Z su qualunque modifica. Nell'app desktop è affidabile; nella web app la cronologia si perde al refresh — [tips-tricks.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/getting-started/tips-tricks.md) (V)
- Crittografia end-to-end opzionale con una seconda password: il server vede solo le modifiche cifrate (CRDT). Se si perde la password i dati non si recuperano — [sync.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/getting-started/sync.md) (V)
- Multi-valuta: la documentazione dice ancora "currency agnostic and does not support multi-currency". Il workaround usa regole template e una nota `#currency:XXX` sul conto. Le release 26.9–26.11 aggiungono valute al "currency picker" (ZAR, NOK, BDT, TZS…), che riguarda la valuta di visualizzazione e non la conversione — [multi-currency.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/budgeting/multi-currency.md); [releases.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/releases.md) (V)
- Tag come hashtag nelle note. Dalla 26.9 si può rinominare un tag aggiornando tutte le note; la 26.11 raggruppa i report custom per tag. La 26.11 introduce anche la "automatic bank syncing" e aggiunge alla documentazione una sezione sulle integrazioni MCP della community (nessun MCP ufficiale) — [releases.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/releases.md) (V)
- I trasferimenti sono coppie collegate, create scegliendo un conto nel campo Payee; modificare un lato aggiorna l'altro. Ci sono anche split, merge di transazioni, bulk edit e filtri, ciascuno con la sua pagina di documentazione — [transfers.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/transactions/transfers.md); [cartella docs/transactions](https://github.com/actualbudget/actual/tree/master/packages/docs/docs/transactions) (V)
- Migrazione: importer nel codice per YNAB4 e nYNAB (ynab5) e per il formato Actual. La documentazione dice "only YNAB4 is officially supported" (testo datato, visto che esiste `ynab5.ts`); la 26.10 aggiunge una barra di progresso all'import da YNAB4 e nYNAB — [importers](https://github.com/actualbudget/actual/tree/master/packages/loot-core/src/server/importers); [migration/index.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/migration/index.md) (V)
- Issue chiuse più votate in tema dati: "Recognise transfers between accounts" #1628 (388 reazioni), "Budget Currency and Category Currencies" #1132 (349), "Add subcategory" #1320 (344), "Upload Attachment support for transactions" #530 (214), "Merge unmatched transactions" #669 (121), "Groups for accounts" #1683 (150), "Import Category" #557 (59) — ricerca GitHub (V). Non ho potuto verificare lo `state_reason` (completed o not planned): l'API delle singole issue era bloccata.

**Sure (fork community di Maybe Finance, Rails, self-hosted)**
- Tipi di import nel codice: transazioni CSV, conti, categorie, merchant, regole, trade, QIF, PDF, Mint, YNAB, Actual, più `sure_import` (round-trip nativo). Esistono sessioni di import con mapping di conti, tipi conto, categorie e tag e con un `preflight`. Le mappature per sorgente si salvano in `import_source_mapping` — [app/models](https://github.com/we-promise/sure/tree/main/app/models); [app/models/import](https://github.com/we-promise/sure/tree/main/app/models/import) (V)
- **Undo dell'import**: `Import#revert`/`revert_later`/`revertable?`, con stati `reverting`/`revert_failed` — [import.rb](https://github.com/we-promise/sure/blob/main/app/models/import.rb) (V)
- **Import PDF con estrazione AI** (`process_with_ai_later`), salvataggio dell'estratto conto come allegato e un "statement vault" con copertura degli estratti — [pdf_import.rb](https://github.com/we-promise/sure/blob/main/app/models/pdf_import.rb); [assistant/function](https://github.com/we-promise/sure/tree/main/app/models/assistant/function) (V)
- Regole: condizioni su conto, importo, categoria, dettagli, merchant, nome, note, tag e tipo. Le azioni sono auto_categorize (LLM), bayes_categorize, auto_detect_merchants, fill_similar_merchants, exclude, set_as_transfer_or_payment, set category/merchant/name/tags, split_transaction e send_email_notification. Ci sono anche RuleGroup, RuleRun (storico delle esecuzioni) e una `safe_regex` — [rule/action_executor](https://github.com/we-promise/sure/tree/main/app/models/rule/action_executor); [rule/condition_filter](https://github.com/we-promise/sure/tree/main/app/models/rule/condition_filter) (V)
- **Classificatore Naive-Bayes locale** "needs no provider — pure Ruby". Si addestra sulle transazioni già categorizzate della famiglia e combina parole, merchant, conto, direzione e una distribuzione log-normale dell'importo; la variante complement NB è configurabile — [bayes_categorizer.rb](https://github.com/we-promise/sure/blob/main/app/models/family/bayes_categorizer.rb) (V)
- Provider LLM: OpenAI (anche endpoint compatibili, con commenti espliciti su Ollama e LM Studio e sui modelli locali a contesto piccolo) e Anthropic. L'uso viene tracciato in `llm_usage` — [provider](https://github.com/we-promise/sure/tree/main/app/models/provider) (V)
- **Abbinamento automatico dei trasferimenti** fra valute diverse con tolleranza sul cambio. Il commento nel codice dice che 30 giorni/10% producevano match casuali, mentre 2 giorni/3% tenevano soprattutto le vere conversioni di valuta. Si possono rifiutare i suggerimenti (`rejected_transfer`) — [auto_transfer_matchable.rb](https://github.com/we-promise/sure/blob/main/app/models/family/auto_transfer_matchable.rb) (V)
- Ricorrenti: `recurring_transaction`, `recurrence_rule`, rifiuto dei match, variazioni di prezzo (`recurring_price_change`, utile per rilevare rincari degli abbonamenti) e bill — [app/models](https://github.com/we-promise/sure/tree/main/app/models) (V)
- **Server MCP** (JSON-RPC `tools/list`/`tools/call`) che espone circa 50 funzioni: transazioni CRUD, regole con `preview_rule`, gestione trasferimenti, bill, import ed upload di estratti conto, ricerca nei file — [mcp_controller.rb](https://github.com/we-promise/sure/blob/main/app/controllers/mcp_controller.rb) (V)
- Multi-utente "family" con budget condivisi (`budget_share`), SSO/OIDC con audit log SSO, export della famiglia (`family_export`, `data_exporter`) e cambi via Frankfurter o altri provider — [app/models](https://github.com/we-promise/sure/tree/main/app/models) (V)
- Issue aperte rilevanti: #2417 "stop silently converting at rate 1.0 when a rate is missing" (5), #389 tag nella lista transazioni (5), #30 template di transazioni (5) — ricerca GitHub (V)

**ezBookkeeping (Go, self-hosted, anche desktop)**
- Convertitori di import: ai, alipay, beancount, camt, csv, custom, excel, feidee, fireflyIII, gnucash, iif, jdcom, mt (MT940), ofx, qif, sgml, wechat — [pkg/converters](https://github.com/mayswind/ezbookkeeping/tree/main/pkg/converters) (V)
- **Preset di import salvati** per utente (modello `ImportPreset` con nome e dati), cioè una mappatura per banca — [import_preset.go](https://github.com/mayswind/ezbookkeeping/blob/main/pkg/models/import_preset.go) (V)
- LLM per il riconoscimento di testo libero e **foto di scontrini** (`RecognizeReceiptImageHandler`). Provider: OpenAI, Anthropic, Google AI, **Ollama, LM Studio** (locali) — [large_language_models.go](https://github.com/mayswind/ezbookkeeping/blob/main/pkg/api/large_language_models.go); [llm/provider](https://github.com/mayswind/ezbookkeeping/tree/main/pkg/llm/provider) (V)
- Fonti dei cambi: BCE, **Banca d'Italia**, Banca del Canada, Banca Nazionale Svizzera, Norges Bank e circa altre 15 banche centrali, più un provider personalizzato dall'utente — [pkg/exchangerates](https://github.com/mayswind/ezbookkeeping/tree/main/pkg/exchangerates) (V)
- Server MCP con tool add/delete transaction, query transactions/accounts/balances/categories/tags/exchange rates, protetto da token e limite per IP — [pkg/mcp](https://github.com/mayswind/ezbookkeeping/tree/main/pkg/mcp) (V)
- Modello dati: tag con gruppi (`transaction_tag_group`), template di transazione, immagini allegate (`transaction_picture_info`), "explorer" (query salvate), 2FA e OAuth2 — [pkg/models](https://github.com/mayswind/ezbookkeeping/tree/main/pkg/models) (V)
- Il `duplicatechecker` è un controllo anti doppio invio (cache in memoria per invio), **non** una deduplica per similarità sulle righe importate — [in_memory_duplicate_checker.go](https://github.com/mayswind/ezbookkeeping/blob/main/pkg/duplicatechecker/in_memory_duplicate_checker.go) (V)
- Issue più votata: #53 "shared/co-owned accounts" (32, aperta), poi #343 creare una categoria al volo (6) — ricerca GitHub (V)

**Firefly III (+ Data Importer, PHP, self-hosted)**
- Modelli: Account/AccountType, TransactionGroup/Journal (split nativi), Tag, Category, Budget, Bill, PiggyBank, Recurrence, Attachment, Location, Note, ObjectGroup, LinkType/TransactionJournalLink, CurrencyExchangeRate, **AuditLogEntry**, UserGroup/UserRole (multi-utente con ruoli), Webhook* — [app/Models](https://github.com/firefly-iii/firefly-iii/tree/main/app/Models) (V)
- Motore di regole con 31 azioni (ConvertToTransfer, SetAmount, LinkToBill, UpdatePiggyBank, DeleteTransaction, Add/RemoveTag, ecc.), rule group ed espressioni — [TransactionRules/Actions](https://github.com/firefly-iii/firefly-iii/tree/main/app/TransactionRules/Actions) (V)
- Trigger dei webhook: ANY, STORE/UPDATE/DESTROY_TRANSACTION, STORE/UPDATE/DESTROY_BUDGET, STORE_UPDATE_BUDGET_LIMIT — [WebhookTrigger.php](https://github.com/firefly-iii/firefly-iii/blob/main/app/Enums/WebhookTrigger.php) (V)
- Issue più votate: #10662 OIDC (37), #5396 SimpleFIN nel Data Importer (28), #5532 prezzi degli asset e cambi (20), #10753 Enable Banking nel Data Importer (16), #4917 template di transazioni (14, aperta) — ricerca GitHub (V)

**Wealthfolio (Tauri/Rust, local-first, portafoglio + spese)**
- Dati salvati localmente, con crittografia opzionale del database e backup protetti da password. "Wealthfolio Connect" a pagamento offre sync fra dispositivi **E2EE**, backup cloud cifrati e sync dei broker — [README](https://github.com/wealthfolio/wealthfolio/blob/main/README.md); [ROADMAP.md](https://github.com/wealthfolio/wealthfolio/blob/main/ROADMAP.md) (V)
- Import CSV avanzato con mappatura dei campi; assistente AI con modello locale o chiave propria anche per importare CSV; **server MCP** (crate `wealthfolio-mcp`); profili separati; regole di categorizzazione per le spese — [README](https://github.com/wealthfolio/wealthfolio/blob/main/README.md); [crates](https://github.com/wealthfolio/wealthfolio/tree/main/crates) (V)
- Issue: #418 convertitori per i CSV dei broker più diffusi (14, aperta), #42 profili di import CSV (9, chiusa), #1211 saldo progressivo del conto (9, chiusa) — ricerca GitHub (V)

**App commerciali (cloud, sincronizzazione bancaria)**
- Lunch Money: l'import CSV/PDF ha "Skip Duplicates" attivo di default, con match **esatto** su data, payee e importo, e "Apply Rules". Limiti: 10.000 righe e 3 MB. Quando l'utente modifica una transazione si creano regole che ricordano la correzione. L'API v2 restituisce `skipped_duplicates` — [Lunch Money import guide](https://support.lunchmoney.app/guides/import-via-csv) (letto solo come snippet di ricerca, pagina non raggiungibile); [v2 migration guide (mirror)](https://lm-v2-api-next-a7fabcab8e9a.herokuapp.com/v2/migration-guide)
- PocketSmith: import di file OFX/QFX/QIF/CSV (OFX raccomandato); categorie e sottocategorie importabili via QIF/CSV; regole che rinominano, categorizzano ed etichettano; multi-valuta con cambi giornalieri e report convertiti nella valuta base — [Importing bank files](https://learn.pocketsmith.com/article/238-importing-bank-files-into-pocketsmith); [Multi-currency](https://learn.pocketsmith.com/article/122-multi-currency-features-available-in-beta) (snippet di ricerca)
- Copilot Money: "recurring filter" per abbinare le transazioni ai ricorrenti; integrazione Amazon (Copilot Labs) che abbina gli ordini alle transazioni; secondo una recensione del 2026 le regole non supportano condizioni composte — [Copilot help: recurrings](https://help.copilot.money/en/articles/3783499-optimizing-recurrings); [Amazon integration](https://intercom.help/copilotmoney/en/articles/5569639-amazon-integration); [review 2026 (fonte terza)](https://budgettools-net.pages.dev/copilot-money-review.html)
- Monarch: esistono solo server MCP non ufficiali (accesso in lettura con credenziali o token). Un utente nel giugno 2026 segnala che con MCP non si fanno export e import CSV. L'aggiornamento di dicembre 2025 dice che l'LLM elabora i dati solo se l'utente usa l'assistente AI — [truthifi 2026 comparison](https://truthifi.com/education/financial-mcp-comparison); [jamiew monarch-money-mcp](https://jamiew.github.io/monarch-money-mcp)
- YNAB: molti server MCP della community; uno (`@tankatronic/ynab-mcp-server`) aggiunge l'import di CSV/OFX/QFX con dry-run e `preview_import`, "which the official YNAB file import does not" per i CSV bancari diretti — [pkgstats tankatronic](https://www.pkgstats.com/pkg:@tankatronic/ynab-mcp-server); [oliverames ynab-mcp-server](https://awesome.ecosyste.ms/projects/github.com%2Foliverames%2Fynab-mcp-server)
- Money Manager Ex: le issue più votate sono "OFX import/export support" #3710 (10), "Online Bank Sync" #2119 (6, aperta), "import transfers in CSV/QIF" #2648, "Avoiding duplicate entries on CSV Import" #6771 e "Automatically recognize payee" #1789 — ricerca GitHub (V)
- Fava: le richieste più votate sono envelope budgeting #909 (26) e la compatibilità con Beancount v3/beangulp #1831/#1860 — ricerca GitHub (V)

### Matrice (righe = capacità, colonne = app)
Legenda: ✔ sì · ◐ parziale/plugin/sperimentale · ✗ no · ? non verificato. (V) = verificato in sessione; (K) = conoscenza pregressa non ricontrollata.

| Capacità | Actual | Firefly III | Sure | ezBook | GnuCash (K) | Beancount/Fava (K) | hledger (K) | Wealthfolio | Monarch (K) | YNAB (K) | Copilot | Lunch Money | PocketSmith | MMEX (K) | HomeBank (K) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Split | ✔V | ✔V | ✔V (azione di regola) | ✔? | ✔ | ✔ (posting) | ✔ | ? | ✔ | ✔ | ✔? | ✔ | ✔ | ✔ | ✔ |
| Gerarchia categorie | gruppi, 1 livello V | piatta + budget | ✔ | 2 livelli | albero conti | albero conti | albero conti | ? | gruppi | gruppi | ? | gruppi | ✔ V(sottocat.) | 2 livelli | 2 livelli |
| Tag/label | hashtag nelle note V | ✔V | ✔V | ✔ con gruppi V | ✗ | tag/link | tag | ? | ✔ | flag | ✔? | ✔ | label V | tag | tag |
| Allegati | ✗ (#530 molto votata) | ✔V | ✔ (estratti PDF) V | foto V | ✔ link | `document:` | ✗ | ? | ✔ | ✗ | ? | ? | ✔? | ✔ | ✗? |
| Campi personalizzati | ✗ | meta V | ? | ✗ | ✗ | metadati liberi | tag:val | ? | ✗ | ✗ | ✗ | ✗? | ✗? | ✔ | ✗ |
| CSV con mappatura salvata | ✔ (per conto) V | ✔ (file di config del Data Importer) | ✔ source mapping V | ✔ preset V | ✔ | importer Python | file `.rules` | ✔ profili V | ✔ | ✗? | ? | 4 colonne | ✔ | ✔ | ✔ |
| OFX/QIF/QFX | ✔V | ? (CSV/CAMT + provider) | QIF V | ✔V | ✔ | plugin | ✗ (via csv) | ✗? | ✗? | ✔ | ✗? | ✗? | ✔V | ✔ | ✔ |
| CAMT.053 / MT940 | CAMT V / ✗ | CAMT (K) | ✗? | ✔/✔ V | ◐ | plugin | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗? | ✗ | ✗ |
| PDF / OCR | ✗ | ✗ | PDF con AI V | scontrino via LLM V | ✗ | ✗ | ✗ | ? | ✗? | ✗ | ✗ | PDF (snippet) | ✗? | ✗ | ✗ |
| Deduplica | id + fuzzy ±7gg V | hash (K) | ? | anti doppio invio V | matcher Bayes | dedup dell'importer | data+importo (K) | ? | provider | id+fuzzy | ? | match esatto | ? | ✔ (#6771) | FITID / campi |
| Anteprima import | ✔V | ✔ | preflight V | ✔? | ✔ | `extract` | `--dry-run` | ✔? | ? | ✔ | ? | ✔? | ? | ✔ | ✔ |
| Undo dell'import | undo generale V | ✗? | **revert V** | ? | ✗ | git | git | ? | ? | ✗? | ? | ? | ✔? | ✗ | ✗ |
| Regole + auto-apprendimento | ✔ ✔ V | ✔ ✗ V | ✔ ◐ V | ? | matcher Bayes | smart_importer (ML) | ✗ | ✔? | ✔ ✔ | ◐ (rinomina payee) | ✔ ◐ | ✔ ✔ | ✔ | ✔ | ✔ |
| Ordine regole / retroattive | stage + rank V | ordine nel gruppo V | gruppi V | — | — | — | ordine nel file | ? | ✔ | — | ? | ✔ | ✔ | ? | ✔ |
| Categorizzazione AI | ✗ nativa | ✗ | LLM cloud/locale + Bayes V | LLM (locale ok) V | Bayes | ML locale | ✗ | LLM locale o BYOK V | cloud | ✗ | cloud | ? | ? | ✗ | ✗ |
| Riconciliazione / cleared | ✔ con lock V | ✔ | ? | ✗? | ✔ | `balance` assertion | assertion | ? | ✗ | ✔ | ✗ | ✗ | ✔? | ✔ | ✔ |
| Multi-valuta / storico cambi | ✗ V | ✔ / ✔ | ✔ (Frankfurter…) V | ✔, 20+ banche centrali, Bankitalia V | ✔ | ✔ prezzi | ✔ P | ✔ V | ✗? | ✗ | ? | ✔ | ✔ giornaliero V | ✔ | ◐ |
| Ricorrenti / rilevamento abbonamenti | schedule ✔ / ✗ | ricorrenze + bill V | ✔ + variazioni prezzo V | template V | scheduled | ✗ | `~` periodiche | ? | ✔ ✔ | ✔ | ✔ ✔ | ✔ | ✔ | ✔ | ✔ |
| Undo/redo, audit log | undo/redo V | audit log V | audit SSO V | ? | undo limitato | git | git | ? | ? | ? | ? | ? | ? | ✗ | ✗ |
| Sync / E2EE | server + E2EE V | server | server | server | file | file + git | file + git | Connect E2EE V | cloud | cloud | cloud | cloud | cloud | file | file |
| Multi-utente / permessi | utenti (#524) | UserGroup/ruoli V | family V | ✗ (#53) | ✗ | ✗ | ✗ | profili V | ✔ | ✔ | ✔? | ✔ | ✔ | ✗ | ✗ |
| API / webhook / MCP | API + CLI / ✗ / community | API / ✔V / community | API / ? / ✔V | API / ✗ / ✔V | bindings | Python | CLI/web | addon / ✗ / ✔V | ✗ / ✗ / community | API / ✗ / community | ✗ | API v2 / ? / ? | API | ✗ | ✗ |
| Migrazione | YNAB4/nYNAB V | ? | Mint/YNAB/Actual V | GnuCash/Firefly/Beancount/IIF V | QIF/OFX | molti tool | csv | ? | Mint | ? | ? | ? | Moneydance (snippet) | QIF | QIF |

### Implementazioni migliori della categoria
- Deduplica: **Actual**, con `imported_id` più match fuzzy (importo uguale, payee simile, ±7 giorni) che preferisce i dati della banca e si abbina all'inserimento manuale fatto prima — [importing.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/transactions/importing.md)
- Regole auto-apprese: **Actual**, con stage pre/default/post e ranking per specificità — [rules](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/budgeting/rules/index.md)
- Categorizzazione locale senza LLM: **Sure**, con un Naive-Bayes multi-fattore (testo, merchant, conto, importo) — [bayes_categorizer.rb](https://github.com/we-promise/sure/blob/main/app/models/family/bayes_categorizer.rb)
- Trasferimenti fra valute diverse: **Sure**, con finestra di 2 giorni e tolleranza del 3% calibrate sui falsi positivi — [auto_transfer_matchable.rb](https://github.com/we-promise/sure/blob/main/app/models/family/auto_transfer_matchable.rb)
- Ampiezza dei formati e OCR locale: **ezBookkeeping** (CAMT, MT940, Ollama/LM Studio, cambi Bankitalia) — [converters](https://github.com/mayswind/ezbookkeeping/tree/main/pkg/converters)
- Undo dell'import: **Sure**, con `Import#revert` — [import.rb](https://github.com/we-promise/sure/blob/main/app/models/import.rb)
- Integrazione e audit: **Firefly III**, con webhook, AuditLogEntry e ruoli di gruppo — [app/Models](https://github.com/firefly-iii/firefly-iii/tree/main/app/Models)
- Privacy del sync: **Actual** E2EE (gratuito, self-hosted) e **Wealthfolio Connect** E2EE (a pagamento) — [sync.md](https://github.com/actualbudget/actual/blob/master/packages/docs/docs/getting-started/sync.md); [ROADMAP](https://github.com/wealthfolio/wealthfolio/blob/main/ROADMAP.md)

### Inferences
- Il connubio "regole + AI" sta convergendo su uno schema comune: regole deterministiche prima, poi ML/LLM come azione di regola (Sure: `bayes_categorize` / `auto_categorize` come action executor). Per MyFinancePlace (AI locale) Sure è il modello architetturale più vicino.
- Nel 2026 MCP è diventato comune negli open source più attivi: ufficiale in Sure, ezBookkeeping e Wealthfolio, solo community per Actual, YNAB e Monarch.
- Fra i concorrenti analizzati solo ezBookkeeping ha un parser MT940 e una fonte di cambi Banca d'Italia. Per l'Italia (CBI/CAMT) è uno spazio poco presidiato.

### Gaps
- Firefly Data Importer (formati, deduplica, file di config), YNAB file import, Lunch Money e HomeBank: i domini erano bloccati, quindi i dettagli sono marcati (K) o letti solo da snippet di ricerca.
- Copilot e Monarch: nessuna documentazione ufficiale su export, deduplica o allegati letta in sessione.
- Lo `state_reason` delle issue chiuse di Actual (#530 allegati, #1132 valute) non è verificabile: l'API delle singole issue era bloccata.
- hledger: la ricerca issue su `simonmichael/hledger` ha restituito 422 (repo non visibile all'API di ricerca).

## Domanda 2: cosa è table stakes e cosa differenzia; richieste principali degli utenti

### Takeaway
Sono ormai standard: import CSV con mappatura salvata più OFX/QIF, deduplica, regole con categorizzazione, split, trasferimenti, tag, ricorrenti, riconciliazione, backup ed export. Differenziano: AI e OCR locali, import PDF, undo/revert dell'import, abbinamento automatico dei trasferimenti, cambi storici da fonti ufficiali, E2EE, MCP e allegati. Nei tracker GitHub le richieste più votate sul dato riguardano il riconoscimento dei trasferimenti, la multi-valuta, le sottocategorie, gli allegati, multi-utente e conti condivisi, i profili di import e i template di transazione.

### Cited Findings
- Actual: le richieste sul dato più votate di sempre sono trasferimenti (388), valute (349), sottocategorie (344), multi-utente #524 (323), allegati (214), gruppi di conti (150), merge delle transazioni (121) — [ricerca issue Actual](https://github.com/actualbudget/actual/issues?q=is%3Aissue+sort%3Areactions-%2B1-desc)
- ezBookkeeping: conti condivisi/cointestati #53 (32), la più votata del progetto — [issue #53](https://github.com/mayswind/ezbookkeeping/issues/53)
- Wealthfolio: profili di import CSV #42 e convertitori per broker #418 — [issue #418](https://github.com/wealthfolio/wealthfolio/issues/418)
- Firefly III: template di transazione #4917 (14) e commissioni sui trasferimenti #5265 (13), entrambe aperte — [issue #4917](https://github.com/firefly-iii/firefly-iii/issues/4917)
- Sure: template #30, tag in lista #389, nessuna conversione silenziosa a 1.0 #2417 — [issue #2417](https://github.com/we-promise/sure/issues/2417)
- MMEX: deduplica CSV #6771, riconoscimento automatico del payee #1789, import dei trasferimenti #2648 — [issue #6771](https://github.com/moneymanagerex/moneymanagerex/issues/6771)

### Inferences
- Table stakes (presenti in 10 o più app su 15): mappatura CSV, deduplica di qualche tipo, regole, split, trasferimenti, ricorrenti, export.
- Differenziatori con richiesta forte e diffusione bassa: allegati (assenti in Actual nonostante 214 reazioni), undo dell'import (solo Sure lo ha esplicito), riconoscimento automatico dei trasferimenti (richiesta n.2 di Actual, implementata bene in Sure), template di transazione (richiesti in Firefly e Sure), conti condivisi.
- Un'app locale per l'Italia può distinguersi con: CAMT.053 e CBI, preset per banca italiana, cambi BCE/Bankitalia storici, revert dell'import, allegati (ricevute) con OCR locale e un MCP locale.

### Gaps
- Le reazioni su Reddit e nei forum (bloccati) e i feature board delle app commerciali (YNAB, Monarch, Copilot) non sono stati quantificati.
- Le reazioni su GitHub misurano la community open source e non sono rappresentative degli utenti delle app commerciali.
