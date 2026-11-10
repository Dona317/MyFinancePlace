# Fattibilità tecnica dei nuovi tipi di grafico in MyFinancePlace (Chart.js 4.4.3 locale + Sankey SVG lato server) — 9 nov 2026

Metodo: lettura del codice del repo (`app/static/js/charts.js`, `app/services/sankey.py`, `app/services/pdf_report.py`, `desktop/`), metadati dal registro npm (`npm view … version time license`), **pacchetti scaricati con `npm pack` e misurati** (byte del file minificato e gzip -9), **prova reale in Chromium headless** (`/usr/bin/google-chrome --headless=new`) caricando il `chart.umd.min.js` 4.4.3 *vendorizzato dal repo* con ogni plugin UMD, e prova di fpdf2 2.8.8 (la versione in `requirements.txt`) con un SVG incorporato nel PDF. Stelle GitHub lette dalla pagina del repo (l'API GitHub e i siti di documentazione chartjs.org, echarts.apache.org, py-pdf.github.io non erano raggiungibili da questa sessione). File di prova in `/tmp/claude-0/-home-user-MyFinancePlace/a89515a7-8215-543d-b4de-d98a64af303e/scratchpad/browser/t.html` e `…/scratchpad/browser/t2.html`.

## 1. Stato attuale dello stack grafico (punto di partenza)

### Takeaway
Un solo file vendorizzato (`chart.umd.min.js` v4.4.3, 205.363 byte), tre fabbriche (`makeLineChart`, `makeBarChart`, `makeDoughnutChart`) con colori letti da variabili CSS e ricostruzione al cambio tema; Sankey e calendario-heatmap sono generati dal server in SVG/HTML; il PDF (fpdf2) oggi **non contiene grafici**. Ogni nuovo plugin è quindi un file UMD in più da copiare in `app/static/vendor/` e da includere in `partials/charts.html`.

### Cited Findings
- Chart.js vendorizzato: `app/static/vendor/chart.umd.min.js`, intestazione «Chart.js v4.4.3 … Released under the MIT License», 205.363 byte; incluso da `app/templates/partials/charts.html:2` — file del repo.
- `app/static` pesa in tutto 636 KB (`du -sh app/static`) ed è copiato per intero nell'eseguibile PyInstaller (`desktop/myfinanceplace.spec:16-18`: `datas = [(… "app" / "static"), "app/static")…]`) — file del repo.
- Tema: `readTheme()` legge `--clr-*`, `--chart-1..8`, `--inc-*`, `--exp-*`; all'evento `mfp:themechange` ogni grafico registrato viene distrutto e ricostruito (`charts.js:9-46`, `:196-203`) — file del repo. Qualunque plugin che prende i colori dalle opzioni si integra in questo meccanismo senza lavoro extra.
- Legenda HTML personalizzata (`htmlLegend`, `charts.js:121-166`) che chiama `generateLabels` del grafico: va verificata/adattata per i tipi nuovi (treemap, matrix, sankey non hanno legenda per dataset).
- Sankey lato server: `app/services/sankey.py` calcola nodi e bande (path SVG cubici, max 7 categorie per lato + «Altre», «Risparmio»/«Dai risparmi»), il template disegna `<svg role="img" aria-label=…>` (`dashboard/index.html:262-263`) — file del repo.
- PDF: `app/services/pdf_report.py` usa fpdf2 «pure Python, no system libraries»; solo testo e tabelle, nessun grafico (grep su chart/svg/image vuoto) — file del repo.
- Desktop: pywebview con `webview.settings["ALLOW_DOWNLOADS"] = True` («Downloads (CSV, PDF, backups) … each one asks where to save it») — `desktop/main.py:225-226`.
- Accessibilità: dei 39 `<canvas>` nei template solo 2 hanno `aria-label`/`role` (grep su `app/templates`) — file del repo.

### Inferences
- Con 636 KB di statici, anche +400 KB di plugin sono un aumento visibile in percentuale ma irrilevante rispetto al peso dell'exe (che contiene PostgreSQL portabile e i modelli ONNX dell'OCR — `docs/DESKTOP.md:152`, `requirements.txt` rapidocr-onnxruntime).

### Gaps
- Non ho misurato la dimensione totale dell'exe/zip desktop (servirebbe una build); il confronto è quindi solo relativo agli statici.

## 2. Plugin Chart.js: compatibilità con 4.4.x, manutenzione, licenza, peso

### Takeaway
Tutti i plugin candidati sono MIT, dichiarano compatibilità con Chart.js 4 e **funzionano davvero con il 4.4.3 vendorizzato** (provati uno per uno in Chromium: treemap, choropleth con world-atlas, matrix, candlestick, ohlc, annotation, zoom, boxplot, violin, sankey → tutti disegnano ed esportano PNG). I più curati sono quelli di kurkle (treemap, matrix, sankey: rilasci set. 2026) e i plugin ufficiali annotation/zoom (ultimo rilascio fine 2024); il punto debole è **chartjs-chart-financial** (0.2.1, marzo 2024, ancora «0.x»).

### Cited Findings
Tabella (versione = `npm view <pkg> version`; data = `time[<versione>]`; peso = file UMD minificato misurato; stelle = pagina GitHub del repo, 9 nov 2026):

| Pacchetto | Versione | Rilascio | Licenza | peerDependency chart.js | min.js (byte) | gzip | Stelle | Prova con 4.4.3 |
|---|---|---|---|---|---|---|---|---|
| chart.js (riferimento) | 4.6.1 | 2026-10-22 | MIT | — | 210.082 | 70.902 | — | il repo usa 4.4.3 |
| chartjs-chart-treemap (kurkle) | 4.2.2 | 2026-09-06 | MIT | >=3.0.0 (README: v3.8+, v4+) | 16.114 | 6.593 | 155 | OK |
| chartjs-chart-geo (sgratzl) | 4.3.6 | 2025-10-04 | MIT | ^4.1.0 | 84.882 (include d3-geo, topojson-client) | 29.713 | 397 | OK (choropleth mondo) |
| chartjs-chart-matrix (kurkle) | 3.1.0 | 2026-09-12 | MIT | >=3.0.0 | 3.671 | 1.688 | 247 | OK |
| chartjs-chart-financial (chartjs) | 0.2.1 | 2024-03-23 | MIT | ^4.0.0 | 12.411 | 3.450 | 811 | OK (candlestick, ohlc; serve un adattatore date) |
| chartjs-plugin-annotation (chartjs) | 3.1.0 | 2024-10-16 | MIT | >=4.0.0 | 38.359 | 12.556 | 625 | OK (linea + box) |
| chartjs-plugin-zoom (chartjs) | 2.2.0 | 2024-11-26 | MIT | >=3.2.0; dipende da hammerjs ^2.0.8 | 15.203 | 5.642 | 623 | OK, anche **senza** hammer.js caricato |
| hammerjs (per pinch/touch del zoom) | 2.0.8 | 2016-04-22 | MIT | — | 20.765 | 7.366 | — | — |
| @sgratzl/chartjs-chart-boxplot | 4.4.5 | 2025-10-04 | MIT | ^4.1.1 | 18.637 | 5.706 | 136 | OK (boxplot, violin) |
| chartjs-chart-sankey (kurkle) | 0.19.1 | 2026-09-12 | MIT | >=3.3.0 | 19.040 | 7.177 | 186 | OK |
| chartjs-chart-venn (upsetjs) | 4.3.7 | 2025-10-11 | MIT | ^4.1.0 | 39.427 | 11.713 | n.d. | non provato |
| chartjs-plugin-datalabels | 2.2.0 | 2022-12-10 | MIT | >=3.0.0 | 12.937 | 5.269 | n.d. | non provato |
| chartjs-adapter-luxon + luxon 3.7.2 | 1.3.1 / 3.7.2 | 2023-02-02 / 2025-09-05 | MIT | >=3.0.0 | 1.836 + 81.694 | 882 + 24.194 | — | OK (usato per financial) |
| chartjs-adapter-date-fns (bundle con date-fns) | 3.0.0 | 2022-12-11 | MIT | >=2.8.0 | 50.650 | 11.726 | — | non provato |
| chartjs-chart-sunburst | — | — | — | — | npm 404 «not in this registry» | — | — | inesistente |

Fonti: registro npm (`npm view`, `npm pack`); stelle — [treemap](https://github.com/kurkle/chartjs-chart-treemap), [geo](https://github.com/sgratzl/chartjs-chart-geo), [matrix](https://github.com/kurkle/chartjs-chart-matrix), [financial](https://github.com/chartjs/chartjs-chart-financial), [annotation](https://github.com/chartjs/chartjs-plugin-annotation), [zoom](https://github.com/chartjs/chartjs-plugin-zoom), [boxplot](https://github.com/sgratzl/chartjs-chart-boxplot), [sankey](https://github.com/kurkle/chartjs-chart-sankey).
- Annotation: tipi line, box, point, label, polygon, ellipse e «doughnut label» al centro della ciambella; tabella compatibilità «Chart.js 4.0.0 and later → versione corrente»; va registrato, non funziona come plugin inline — [GitHub chartjs-plugin-annotation](https://github.com/chartjs/chartjs-plugin-annotation).
- Zoom: il README del ramo principale dice che i gesti usano «the browser's native Pointer Events — no extra dependency is required» — [GitHub chartjs-plugin-zoom](https://github.com/chartjs/chartjs-plugin-zoom); **ma** il pacchetto pubblicato 2.2.0 ha ancora `dependencies: hammerjs ^2.0.8`, il suo README dice «Hammer.js is used for gesture recognition» e il bundle UMD fa `require("hammerjs")` (misurato nel tarball). Quindi il cambio a Pointer Events non è ancora in una release npm. Nel browser il plugin si registra e funziona anche senza hammer (prova `t2.html`: «zoom without hammer: OK»); hammer serve per pinch/pan touch.
- Financial: README con cronologia fino a Chart.js 4.0.0; nessuna release GitHub pubblicata; serve un adattatore date (esempi con chartjs-adapter-luxon; alternative Moment, date-fns) — [GitHub chartjs-chart-financial](https://github.com/chartjs/chartjs-chart-financial).
- Geo: due tipi `choropleth` e `bubbleMap`, scala `projection` con le proiezioni d3-geo (es. `equalEarth`, `naturalEarth1` presenti nel bundle), dati da `ChartGeo.topojson.feature()`; world-atlas citato come sorgente — [GitHub chartjs-chart-geo](https://github.com/sgratzl/chartjs-chart-geo).
- Sankey kurkle: «works with Chart.js v3.3+, v4+» — [GitHub chartjs-chart-sankey](https://github.com/kurkle/chartjs-chart-sankey).
- Boxplot: aggiunge `boxplot` e `violin` — [GitHub chartjs-chart-boxplot](https://github.com/sgratzl/chartjs-chart-boxplot).
- In Node (senza DOM) `chartjs-chart-financial` e `chartjs-plugin-zoom` falliscono al `require` («Cannot read properties of undefined (reading 'helpers')», «window is not defined»): sono bundle pensati per il browser; nel browser con `<script>` funzionano (prova Chromium). Irrilevante per l'app, rilevante se si volessero testare in Node/jsdom.

### Inferences
- Un aggiornamento del vendor da 4.4.3 a 4.6.1 (+4,7 KB) non è necessario per nessun plugin: tutte le peerDependency sono soddisfatte da 4.4.3.
- Il gruppo «kurkle» (treemap, matrix, sankey) è mantenuto dallo stesso maintainer di Chart.js e ha rilasci nel 2026: rischio basso. Financial è il più a rischio di abbandono: per candlestick conviene isolarlo in una sola pagina.
- Pacchetto completo consigliato (treemap + matrix + annotation + zoom + boxplot + sankey + financial + adattatore luxon) ≈ **207 KB** minificati; con geo + countries-110m ≈ **400 KB**. Con l'adattatore date-fns in bundle al posto di luxon ≈ 174 KB senza mappa.

### Gaps
- Stelle di venn/datalabels e data dell'ultimo commit dei repo non lette (API GitHub bloccata, la pagina GitHub non mostra date).
- Le prove sono di rendering e registrazione, non di interazione (tooltip, wheel, drag) né di convivenza con `htmlLegend`.

## 3. Tipo per tipo: miglior implementazione nello stack

### Takeaway
Quasi tutto si fa con Chart.js: **nativi** waterfall (barre fluttuanti), fan chart Monte Carlo (fill tra dataset), scatter/bubble, area impilata, gauge (ciambella a 180°), linea prezzo con marcatori; **plugin piccoli** per treemap, heatmap/correlazione, annotazioni, zoom, box plot, candlestick; **mappa** con chartjs-chart-geo (+108 KB di TopoJSON). Unici buchi veri di Chart.js: **sunburst** (nessun plugin; ripiego = ciambella a più anelli) e un calendario-heatmap «pronto» (ma l'app ne ha già uno lato server).

### Cited Findings
(prove in Chromium con il Chart.js 4.4.3 del repo — `scratchpad/browser/t.html`; tutte «OK» con `toBase64Image()`)
| Grafico | Implementazione consigliata | Prova | Sforzo stimato |
|---|---|---|---|
| Waterfall (crescita patrimonio, ponte entrate→risparmio) | Nativo: `type:'bar'` con dati `[base, cima]` (barre fluttuanti) | OK | Basso: nuova opzione in `buildBarChart` + tooltip con la differenza |
| Fan chart Monte Carlo (percentili 10/25/50/75/90) | Nativo: dataset linea con `fill:'-1'` tra percentili (l'app già usa `fill:"-1"` per le bande, `charts.js:243`) | OK | Basso: già quasi presente in `forecast/retirement.html` |
| Area impilata (patrimonio per classe) | Nativo: `fill:'origin'/'-1'` + `scales.y.stacked` | OK | Basso |
| Scatter/bubble rischio-rendimento | Nativo `bubble`/`scatter` | OK | Basso-medio (nuova fabbrica) |
| Gauge (tasso di risparmio, avanzamento obiettivo) | Nativo: ciambella `rotation:-90, circumference:180, cutout:'75%'`; testo al centro con annotation «doughnut label» o HTML sovrapposto | OK | Basso |
| Treemap (allocazione, spese per categoria/sottocategoria) | chartjs-chart-treemap 4.2.2 (`tree`, `key`, `groups`) | OK | Medio: colori/etichette, legenda HTML da disattivare |
| Sunburst (categoria → sottocategoria; classe → regione) | Nessun plugin Chart.js (npm 404). Ripiego: doughnut con 2 dataset concentrici (nativo) oppure ECharts `sunburst` | ECharts OK | Medio (ripiego) / alto se si introduce ECharts |
| Mappa esposizione per paese | chartjs-chart-geo 4.3.6 `choropleth` + world-atlas `countries-110m.json` | OK (177 paesi disegnati) | Medio-alto: mappatura ISO ↔ id numerico, nomi IT, scala colori per tema |
| Heatmap rendimenti mensili / correlazione | chartjs-chart-matrix 3.1.0 (celle x,y,v); in alternativa la tabella-heatmap CSS già usata in Riepilogo (`reports/summary.html:16`) | OK | Basso-medio |
| Calendar heatmap | Già presente lato server (`reports/rhythm.html`, celle `level-N`); matrix può farlo ma non serve | — | Nullo (riuso) |
| Box plot (dispersione rendimenti, spese mensili per categoria) | @sgratzl/chartjs-chart-boxplot 4.4.5 (anche violin; calcola quartili dai dati grezzi) | OK | Basso-medio |
| Candlestick/OHLC | chartjs-chart-financial 0.2.1 + adattatore date (luxon) | OK | Medio; l'app ha solo prezzi di chiusura (`HoldingPrice`: data, prezzo) → candlestick poco utile senza O/H/L |
| Linea prezzo con marcatori acquisto/vendita | Nativo: dataset `scatter` sovrapposto con `pointStyle` (triangolo) per le operazioni; oppure annotation `point`/`label` | linea+annotation OK | Basso-medio |
| Annotazioni (benchmark, bande obiettivo, eventi) | chartjs-plugin-annotation 3.1.0 (line, box, label) | OK | Basso; un'opzione `opts.annotations` nelle fabbriche |
| Zoom/pan | chartjs-plugin-zoom 2.2.0 (wheel, drag, pan); hammerjs solo per touch | OK | Basso-medio (pulsante «reimposta zoom»; con categorie conviene asse `time`) |
| Sankey | Tenere il server SVG (vedi §5) | kurkle OK | — |
| Export PNG | Nativo `chart.toBase64Image()` (provato) | OK | Basso (pulsante + `<a download>`) |
| Export CSV | Dati già in pagina (labels/datasets) → Blob CSV lato client, o rotta server (l'app ha già CSV, `export.py`) | non provato | Basso |
| Venn (sovrapposizione ETF) | chartjs-chart-venn 4.3.7 (39 KB) | non provato | Medio; la sovrapposizione ETF richiede dati di look-through che l'app non ha (inventario §4) |

- Fonti: prove locali; codice del repo citato in tabella; inventario `research_notes/Grafici dati e piano Portafoglio/myfinanceplace_inventario.md` §2 e §4 (prezzi salvati solo come chiusura in euro, nessun TER/look-through).

### Inferences
- Le «vittorie a costo zero» (nessun file nuovo) sono waterfall, fan chart, area impilata, bubble, gauge, marcatori di operazioni: si possono fare subito estendendo `charts.js`.
- Il prossimo gradino (≈ 60 KB: annotation + zoom + matrix + treemap) copre benchmark/bande, zoom sui grafici lunghi, heatmap e treemap.

### Gaps
- Nessuna prova di leggibilità/estetica dei render (solo esito tecnico); nessuna prova di performance con molti punti (es. 10 anni di prezzi giornalieri).

## 4. Mappa del mondo: dati TopoJSON, licenza, nomi italiani

### Takeaway
`world-atlas@2.0.2` `countries-110m.json` pesa **107.761 byte (38.495 gzip)**, licenza ISC (Mike Bostock), dati Natural Earth 4.1.0 (dominio pubblico); 177 geometrie con `id` = codice ISO 3166-1 **numerico** come stringa e `properties.name` in **inglese** (3 senza id). Per i nomi italiani: i18n-iso-countries (`langs/it.json` 6.139 byte, 250 paesi, MIT) lato client, oppure Babel/CLDR lato server (già dipendenza tramite Flask-Babel).

### Cited Findings
- File misurati nel tarball world-atlas 2.0.2 (rilascio 2019-09-05, ultimo): `countries-110m.json` 107.761 B, `land-110m.json` 55.207 B, `countries-50m.json` 756.420 B — `npm pack world-atlas`.
- Licenza: «Copyright 2013-2019 Michael Bostock. Permission to use, copy, modify, and/or distribute…» (ISC) — `LICENSE` del pacchetto; il README: «a convenient redistribution of Natural Earth's vector data, version 4.1.0 as TopoJSON», «derived from the Natural Earth's Admin 0 country boundaries, 1:110m» — README di [world-atlas](https://github.com/topojson/world-atlas).
- Contenuto: 177 geometrie; esempio `{'id': '242', 'properties': {'name': 'Fiji'}}`; id 380 = «Italy», 276 = «Germany», 840 = «United States of America»; 3 geometrie senza `id` — analisi locale del file.
- i18n-iso-countries 7.14.0 (MIT, 2025-02-17): `langs/it.json` 6.139 B con 250 paesi (es. DE «Germania», US «Stati Uniti d'America», GB «Regno Unito»); `codes.json` 10.253 B con la conversione alpha-2/alpha-3/numerico — `npm pack i18n-iso-countries` e lettura locale.
- chartjs-chart-geo include già topojson-client e d3-geo nel bundle UMD (84.882 B) — misurato.
- La mappa resa con 177 paesi e proiezione `equalEarth` in Chromium: OK (PNG 81 KB) — prova `t.html`.

### Inferences
- Il modello `Holding` ha `regione` testuale, non un codice paese ISO (inventario §4): la mappa richiede prima un campo paese (ISO alpha-2) o una tabella di look-through per paese; senza, la mappa non ha dati.
- I nomi italiani conviene darli dal server con Babel (`Locale('it').territories['DE']`), passando al client un dizionario numerico→nome solo per i paesi presenti: zero file in più. Babel non dà i codici numerici: serve una piccola tabella alpha-2↔numerico (≈250 righe) nel codice.
- 110m basta per un riquadro di dashboard; i micro-stati (es. Singapore, Lussemburgo, Malta) a 1:110m possono mancare o essere minuscoli: un elenco/tabella accanto alla mappa li copre (inferenza da scala 1:110m, non verificata paese per paese).

### Gaps
- Non ho verificato quali paesi manchino esattamente nel 110m (Lussemburgo, Singapore, Hong Kong ecc.), né eseguito Babel (non installato nel sandbox).

## 5. Sankey: chartjs-chart-sankey vs SVG lato server

### Takeaway
Tenere l'SVG lato server: è già fatto, testato, accessibile (`role="img"` + `aria-label`), cliccabile, e soprattutto **riusabile così com'è nel PDF** (fpdf2 incorpora SVG). chartjs-chart-sankey 0.19.1 (19 KB, MIT, rilascio set. 2026) funziona con il 4.4.3 ma porterebbe solo tooltip/animazioni e un layout automatico multi-colonna, utile solo se si volessero Sankey a più livelli (categoria → sottocategoria → conto).

### Cited Findings
- Sankey server: `app/services/sankey.py` (72 righe) produce `nodes`, `bands` con path SVG, larghezza 1000×420; template con `role="img"` e `aria-label` «Entrate …, uscite …» (`dashboard/index.html:262-263`) — file del repo.
- chartjs-chart-sankey 0.19.1: provato con 4.4.3, OK — prova `t.html`; compatibilità «v3.3+, v4+» — [GitHub](https://github.com/kurkle/chartjs-chart-sankey).
- fpdf2 2.8.8 incorpora un SVG con `<rect>`, `<path>` cubici con `fill-opacity` e `<text>` via `pdf.image(BytesIO(svg))` — prova locale (`scratchpad/pdf_svg_test2.py`, testo estratto con pdftotext). **Attenzione**: il testo «€» dentro l'SVG fa fallire fpdf2 con i font core (`KeyError: '€'`, anche con `core_fonts_encoding = "windows-1252"` che l'app usa in `pdf_report.py`); funziona registrando un TTF (`add_font('DejaVu', …)` e `font-family="DejaVu"` nell'SVG) — prova `pdf_svg_test4.py`.
- I font vendorizzati dell'app sono solo `.woff2` (Inter, IBM Plex Sans, Atkinson Hyperlegible Next) — `app/static/vendor/fonts/`; fpdf2 vuole TTF/OTF.

### Inferences
- Per mettere il Sankey (o altri grafici SVG) nel PDF serve aggiungere un TTF (es. Inter in .ttf, licenza OFL come gli attuali) al pacchetto, oppure scrivere «EUR» negli SVG destinati al PDF.

### Gaps
- Non ho provato l'SVG reale del Sankey dell'app nel PDF (la prova usa un SVG equivalente scritto a mano).

## 6. Restare su Chart.js o aggiungere ECharts (o altro)?

### Takeaway
**Restare su Chart.js + plugin.** ECharts 6.1.0 (Apache-2.0, 67,7k stelle) copre nativamente treemap/sunburst/mappa/sankey/calendario e ha SSR in SVG, ma il bundle completo è 1.121.883 B (quasi il doppio di tutti gli statici attuali), una build ridotta ai soli tipi mancanti pesa comunque 648.943 B, e introdurrebbe un secondo sistema di temi/legende/tooltip. Plotly (4,8 MB) è fuori scala; uPlot (51 KB) è ottimo per serie lunghe ma non aggiunge tipi; D3 (281 KB) solo se si vogliono SVG su misura (che l'app già fa in Python).

### Cited Findings
- ECharts 6.1.0, rilascio 2026-05-19, Apache-2.0, dipendenze zrender 6.1.0 + tslib — `npm view echarts`; 67,7k stelle — [GitHub apache/echarts](https://github.com/apache/echarts).
- Pesi misurati (dist del pacchetto): `echarts.min.js` 1.121.883 B (367.915 gzip); `echarts.common.min.js` 715.020 B (239.503 gzip); `echarts.simple.min.js` 500.315 B (168.869 gzip) — `npm pack echarts`.
- `echarts.common` include solo line, bar, pie, scatter + componenti (grid, tooltip, legend, dataZoom, markLine/markArea, aria…) — **niente** treemap, sunburst, sankey, map, heatmap/calendar (`index.common.js` del pacchetto). Per quei tipi serve il bundle completo o una build propria.
- Build propria con esbuild 0.24 (TreemapChart, SunburstChart, HeatmapChart, SankeyChart, MapChart + Tooltip, Calendar, VisualMap, Aria, Geo + renderer SVG e Canvas): **648.943 B minificati, 220.146 gzip** — misura locale (`scratchpad/ec_entry.js`).
- ECharts 5+/6 non contiene mappe: il pacchetto non ha cartella `map` (solo `asset/logo.png`), serve fornire un GeoJSON — ispezione del tarball.
- ECharts ha `i18n/langIT.js`, 38 temi in `theme/` (incluso `dark.js`), opzione `darkMode`, componente `aria` — ispezione del tarball. Prove in Chromium: sunburst e calendario-heatmap resi in SVG con `renderToSVGString()` (`ssr:true`), treemap su canvas: OK (`t2.html`); con `aria:{enabled:true}` la stringa SVG SSR **non** conteneva `aria-label` (l'etichetta ARIA va sul contenitore DOM).
- L'SSR di ECharts gira in JavaScript (browser o Node): in Python non c'è un motore JS, quindi l'exe non può generare SVG ECharts lato server senza aggiungere Node — inferenza dalla struttura del pacchetto (`ssr/client` è solo l'idratazione lato client, 3.634 B) e dalla prova in Node.
- Plotly.js 4.2.0 (MIT, 2026-10-29): `plotly.min.js` 4.841.490 B (1.478.230 gzip); `plotly-basic.min.js` 1.202.920 B — `npm pack`.
- uPlot 1.6.32 (MIT, 2025-03-14): `uPlot.iife.min.js` 51.081 B (22.009 gzip) — `npm pack`.
- D3 7.9.2 (ISC, 2026-11-03): `d3.min.js` 280.622 B (92.088 gzip) — `npm pack`.

### Inferences
- L'unico tipo che Chart.js non fa bene è il sunburst: non giustifica 650 KB–1,1 MB e un secondo stack (temi, `htmlLegend`, drill-down `onClickIndex`, tooltip in stile app). Se in futuro servissero sunburst e Sankey multi-livello insieme, ECharts in **build ridotta** caricata solo in quelle pagine è l'opzione meno invasiva.
- Coerenza: tutti i grafici oggi passano da `charts.js` (tema, palette entrate/uscite, legenda HTML, clic → transazioni); i plugin Chart.js ereditano gratis `Chart.defaults` (font, tooltip scuro) e la ricostruzione al cambio tema, ECharts no.
- Peso nell'exe: Chart.js + tutti i plugin consigliati ≈ +400 KB con la mappa, contro +650 KB/1,1 MB di ECharts; in entrambi i casi trascurabile rispetto a PostgreSQL+ONNX, quindi il criterio decisivo è la coerenza, non i byte.

### Gaps
- Nessuna misura di rendimento di ECharts vs Chart.js con molti dati; nessuna verifica della documentazione ufficiale ECharts (sito non raggiungibile).

## 7. PDF: grafici lato server vs lato client

### Takeaway
Per i report PDF la strada coerente con lo stack è **SVG generato in Python** (come `sankey.py`) e incorporato con `fpdf2.image()` — vettoriale, senza browser, senza nuove dipendenze, ma con un TTF per «€». I grafici Chart.js sono canvas nel browser: per il PDF si potrebbe inviare `toBase64Image()` al server (PNG raster), ma solo da una pagina aperta, non per PDF generati senza interfaccia (es. bilancio dell'anno).

### Cited Findings
- fpdf2 2.8.8 ha un modulo `svg.py` e `FPDF.image()` instrada gli SVG a `_vector_image` (paths, gradienti, testo con `text-anchor`, classi CSS) — codice del pacchetto (`fpdf/fpdf.py:5315-5605`, `fpdf/svg.py`).
- Prova: SVG con rettangoli, banda cubica semitrasparente e testo → PDF valido con testo estraibile; con «€» serve un TTF registrato (vedi §5) — prove locali.
- `toBase64Image()` funziona con tutti i tipi provati (PNG da 6–130 KB a 400×300) — prova `t.html`.
- Oggi il PDF non ha grafici e i report si generano sul server (`pdf_report.py`, `annual_review.py`, rotte in `export.py`) — file del repo.

### Inferences
- Server-side SVG: + vettoriale, identico in web/desktop/PDF, testabile con pytest (la copertura ≥94% del progetto lo richiede), accessibile come `<svg role="img">`; − ogni tipo va scritto a mano in Python (barre, linee, ciambella sono semplici; treemap squarified e mappa no).
- Client-side PNG: + riusa i grafici esistenti; − raster, dipende dal browser aperto, flusso più fragile in pywebview, non utilizzabile per PDF generati in background.
- Compromesso: SVG Python solo per i 3–4 grafici del PDF (barre mensili, ciambella categorie, linea patrimonio, Sankey già pronto), Chart.js per tutto l'interattivo.

### Gaps
- Non ho verificato in pywebview (Windows/macOS) che un `<a download>` con data URL PNG o Blob CSV apra il dialogo di salvataggio come per le rotte server (`ALLOW_DOWNLOADS` è documentato per CSV/PDF/backup serviti da Flask, `desktop/main.py:225`).

## 8. Accessibilità e modalità scura

### Takeaway
Chart.js disegna su canvas: l'accessibilità va aggiunta a mano (`role="img"`, `aria-label`, contenuto di riserva); oggi 37 canvas su 39 ne sono privi. I plugin non cambiano questo quadro; la scura funziona già per costruzione (ricostruzione al cambio tema), purché ogni nuovo tipo prenda i colori da `Theme`.

### Cited Findings
- Chart.js: l'accessibilità «has to be added with ARIA attributes on the canvas element» (`role="img"` + `aria-label`), il testo tra i tag canvas fa da alternativa; senza, il contenuto non è accessibile agli screen reader — [docs Chart.js accessibility (sorgente GitHub)](https://github.com/chartjs/Chart.js/blob/master/docs/general/accessibility.md).
- Repo: 2 canvas su 39 con `aria-label`/`role` (grep); Sankey SVG con `role="img"` e `aria-label` (`dashboard/index.html:262`).
- ECharts: componente `aria` incluso anche nel bundle `simple`/`common` (`index.simple.js`, `index.common.js`); nella prova SSR l'SVG non conteneva `aria-label` — ispezione/prova locale.

### Inferences
- Pattern consigliato: le fabbriche di `charts.js` impostano `role="img"` e un `aria-label` riassuntivo (es. totale e voce maggiore) e, per heatmap/treemap/mappa, una tabella `<details>` con i dati (che serve anche da export CSV).
- Scale di colore continue (geo `color`, matrix): vanno derivate dai token del tema (chiaro/scuro) invece delle interpolazioni d3 di default; per la heatmap divergente (rendimenti ±) usare `--clr-positive`/`--clr-negative` con alfa.
- Treemap/heatmap usano testo sopra celle colorate: il contrasto va controllato in entrambi i temi (non verificato).

### Gaps
- Nessun audit WCAG eseguito sui render; non verificata la navigazione da tastiera dei plugin (canvas: assente per costruzione).
