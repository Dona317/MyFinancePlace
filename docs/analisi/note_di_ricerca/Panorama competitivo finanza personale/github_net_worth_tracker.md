# GiuseppeDM98/net-worth-tracker (osservato 2026-11-10)

Segnalato a mano da Donatello come repo da confrontare con MyFinancePlace (T-001).

Metodo: metadati dall'API GitHub (`gh repo view`) e README (`gh api repos/.../readme`). Il codice non è stato letto: le funzioni sotto sono quelle dichiarate nel README.

## Scheda

| Voce | Valore |
|---|---|
| Stelle | 79 |
| Creato | 2025-11-09 |
| Ultimo push | 2026-11-10 |
| Licenza | AGPL-3.0 |
| Linguaggio | TypeScript |
| Stack | Next.js 16, React 19, Tailwind 4, Firebase 12, Vitest 4 |
| Lingua | interfaccia in italiano |
| Pubblico | investitori italiani |

## Cosa dichiara di fare

- **Patrimonio e portafoglio**: asset di tipo azioni, ETF, obbligazioni, cripto, immobili, materie prime, fondi pensione e conti di cassa. Prezzi automatici da Yahoo Finance e Borsa Italiana (ISIN per i BTP). Conversione in EUR con i tassi Frankfurter.
- **Obbligazioni**: cedole pianificate, step-up e premio finale, BTP Valore.
- **Costo medio** con PMC multi-broker, registro operazioni (acquisti, vendite, rettifiche) con conto di regolamento.
- **Previdenza**: fondo pensione valutato a mano dall'estratto conto.
- **Allocazione**: obiettivi per classe, regola automatica Azioni/Obbligazioni (125 − età − tasso × 5), ETF con leva, esposizione per emittente e settore, ribilanciamento. Una «verdict» in una frase per ogni pagina.
- **Consulente di allocazione** guidato, con due agenti AI.
- **Rendimenti**: TWR, Sharpe, CAGR a 12 mesi, drawdown, mappa mensile, confronto con sei portafogli modello (60/40, All Weather, Buffett 90/10, Golden Butterfly, Permanent, 100% ACWI).
- **Capitale e mercato**: quanto del patrimonio viene dai versamenti e quanto dal mercato.
- **Pianificazione**: FIRE, Monte Carlo, assistente AI su Claude.
- **Famiglia**: intestatari per quota di ogni asset.
- **Mobile**: prima schermata composta anche su telefono e tablet.

## Confronto con MyFinancePlace

**Sovrapposizioni**: patrimonio netto, investimenti, previdenza, FIRE, Monte Carlo, AI su Claude, famiglia, interfaccia in italiano, TWR/Sharpe.

**Dove MFP è diverso**: il loro focus è patrimonio e portafoglio; MFP copre anche il conto economico, il budget, le transazioni e l'import di estratti conto bancari (MFP lo fa per layout, qui non è dichiarato). Non dichiarano fisco italiano (730, quadro RW, IVAFE), a differenza di MFP (F15).

**Da guardare**: il pattern «verdict in una frase» sopra ogni pagina; la regola 125 − età − tasso × 5 per l'allocazione; il consulente guidato a schermate con una domanda per volta.

## Rischi per il confronto

- 79 stelle e un solo autore: è un progetto piccolo, ma molto vicino come perimetro.
- Firebase come backend: i dati stanno nel cloud, non in locale. MFP punta su locale e desktop.
