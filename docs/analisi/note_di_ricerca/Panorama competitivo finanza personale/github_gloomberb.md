# gloom-sh/gloomberb, «Gloom» (osservato 2026-11-10)

Segnalato a mano da Donatello come repo da confrontare con MyFinancePlace (T-001).

Metodo: metadati dall'API GitHub (`gh repo view`) e README (`gh api repos/.../readme`). Il codice non è stato letto: le funzioni sotto sono quelle dichiarate nel README.

## Scheda

| Voce | Valore |
|---|---|
| Stelle | 2.696 |
| Creato | 2026-03-25 |
| Ultimo push | 2026-11-10 |
| Licenza | MIT |
| Linguaggio | TypeScript (esecuzione su Bun) |
| Sponsor | Adjacent (dichiarato nel README) |
| Forme | terminale (macOS, Linux, Windows), app desktop (macOS, Windows), browser |

## Cosa dichiara di fare

- Quotazioni, grafici, bilanci, filing, opzioni, notizie e portafoglio in un unico spazio da tastiera.
- Comandi tipo `DES AAPL` (scheda società) e `GP NVDA` (grafico). `Ctrl+P` per la barra dei comandi.
- Grafici come immagini nei terminali compatibili con Kitty (Ghostty, Kitty, WezTerm), testo altrove.
- Estendibile: il README parla di funzioni e comandi, con un catalogo sul sito.

## Confronto con MyFinancePlace

**Sovrapposizioni**: solo in parte. Entrambi hanno un portafoglio con quotazioni e grafici.

**Differenze**: Gloom è un terminale per i mercati (dati di borsa, bilanci, opzioni), non un'app di budget o di patrimonio. Non dichiara conti, spese, budget, previdenza, fisco o debiti. MFP non ha opzioni né filing.

**Da guardare**: la barra dei comandi con `Ctrl+P` e le scorciatoie da tastiera; il modello di distribuzione (un comando di installazione, app desktop, versione nel browser). Sono idee per l'interfaccia, non per le funzioni.

## Perché è nelle note

Concorrente per il pubblico degli investitori che vogliono controllare il mercato da tastiera. Non è un concorrente per il budget. Va tenuto separato dai tracker di patrimonio nel confronto.
