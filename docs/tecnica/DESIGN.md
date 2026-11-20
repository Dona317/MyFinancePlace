# Linee guida di design — MyFinancePlace

Le regole dell'interfaccia, in un posto solo, perché ogni pagina nuova (o rifatta) somigli alle altre.
**Va letto prima di toccare template o CSS.** Quando si prende una decisione di design nuova, si aggiunge al
[registro delle decisioni](#15-registro-delle-decisioni) in fondo e, se serve, si aggiorna la sezione che la riguarda.

Stato: prima versione, 18 nov 2026. Le voci segnate **(da fare)** sono decise ma non ancora applicate al codice:
si sistemano con le card di pulizia **T42–T48** del piano ([CARD_PROSSIME_TASK.md](../piano/CARD_PROSSIME_TASK.md),
giro D), in ordine di impatto (UI-12). Le domande non ancora decise vanno in [Decisioni aperte](#14-decisioni-aperte).

---

## 1. Principi
1. **I dati prima della decorazione.** Cifre, tabelle e grafici sono il contenuto; tutto il resto si fa piccolo.
2. **Una sola azione principale per vista.** Un solo pulsante arancio pieno; gli altri sono leggeri o con bordo.
3. **Le azioni compaiono quando servono.** Quelle sulle righe selezionate si vedono quando c'è una selezione;
   i pannelli (filtri, modifica massiva) si aprono a richiesta e la pagina ricorda se erano aperti.
4. **Coerenza prima della novità.** Prima di inventare un elemento si cerca quello che esiste già (macro e
   partial in `app/templates/partials/`); se manca, si crea riusabile.
5. **Chiaro e scuro, desktop e telefono.** Ogni modifica si guarda nei due temi e a larghezza di telefono.

## 2. Colori
Tutti i colori vengono dalle variabili di `app/static/css/theme.css` (tema chiaro e tema scuro). **Mai codici
colore scritti a mano** nei template o in `main.css`: se serve un colore nuovo si aggiunge una variabile, con il suo
valore per entrambi i temi.

### 2.1 Ruoli
| Ruolo | Variabili | Si usa per |
|---|---|---|
| Primario (arancio) | `--clr-primary`, `-hover`, `-light`, `-muted`, `--clr-on-primary` | **solo** azioni e stato attivo: pulsante principale, link, scheda/voce attiva, interruttori accesi, focus |
| Positivo (verde) | `--clr-positive`, `-bg`, `-text` | entrate, guadagni, contanti, esiti riusciti |
| Negativo (rosso) | `--clr-negative`, `-bg`, `-text` | uscite, perdite, errori, eliminazioni |
| Avviso | `--clr-warning`, `-bg` | da controllare, scadenze vicine |
| Neutro | `--clr-neutral`, `-bg` | informazioni (avvisi «info»), trasferimenti — vedi UI-08 |
| Testi | `--clr-text-primary`, `-secondary`, `-muted`, `-inverse` | gerarchia del testo |
| Superfici e bordi | `--clr-bg-app`, `-card`, `-input`, `-table-alt`, `--clr-border`, `-light` | sfondi, riquadri, campi, righe |
| Menu laterale | `--clr-sidebar-*` | solo il menu laterale |
| Grafici | `--chart-1` … `--chart-8`, `--chart-amber` | serie dei grafici senza un significato proprio |

### 2.2 I colori della finanza (valgono ovunque: KPI, icone, badge, serie dei grafici)
| Cosa | Colore | Classi |
|---|---|---|
| Entrate | verde | `kpi-positive`, `.amount` positivo |
| Uscite | rosso | `kpi-negative`, `.amount` negativo |
| Contanti | verde | `kpi-positive`, `.acc-cash` |
| Investimenti (valore, investito, posizioni) | **blu** (`--chart-3`) | `kpi-blue`, colore grafico `blue` |
| Debiti (debito residuo, debiti totali, serie Debiti) | **viola** (`--chart-5`), **riservato ai debiti** | `kpi-purple`, colore grafico `purple` |
| Trasferimenti / giroconti | neutro, **non blu** (UI-08) | `.tx-transfer`, `.amount-kind.transfer` |
| Patrimonio netto, totali generali | neutro (non arancio) **(da fare)** | `kpi-neutral` |

Il blu appartiene agli investimenti. **(da fare)** `--clr-neutral` oggi è un blu (#1971C2) usato per trasferimenti,
avvisi «info» e l'icona KPI dei conti: va spostato su un grigio-ardesia, così il blu resta solo agli investimenti.

## 3. Tipografia
- Carattere: `--font-body` (Inter); cifre nelle tabelle e negli importi: `--font-mono`.
- Dimensioni: **solo la scala** `--font-size-xs` (12px) · `-sm` (14) · `-md` (16) · `-lg` (18) · `-xl` (20) · `-2xl` (24)
  · `-3xl` (32). Unica eccezione ammessa: le etichette minuscole in maiuscoletto (intestazioni di colonna, etichette
  dei filtri e dei KPI) a 11px. **(da fare)** oggi ci sono 15 dimensioni scritte a mano fuori scala.
- Spessore: **400** normale, **600** per titoli ed evidenze. Niente 500 né 700 **(da fare: 55 usi di 700)**.
- Maiuscole: **solo la prima lettera** in titoli, pulsanti, schede e voci di menu («Elenco transazioni», «Nuova
  transazione», «Conti e carte»); i nomi propri restano maiuscoli. Il maiuscoletto (intestazioni di colonna,
  etichette KPI) lo fa il CSS con `text-transform`, il testo nel template resta normale.

## 4. Spaziature **(da fare)**
Scala unica a passi di 4px, da introdurre come variabili e da usare per margini, padding e distanze:
`--space-1` 4px · `--space-2` 8px · `--space-3` 12px · `--space-4` 16px · `--space-5` 24px · `--space-6` 32px.
Distanza standard tra riquadri: 16px; padding dei riquadri: 16–20px; distanza tra controlli affiancati: 8px.

## 5. Forme, ombre, movimento
- Angoli: `--border-radius` (14px) riquadri · `--border-radius-sm` (8px) campi, pulsanti, pannelli interni ·
  `--border-radius-lg` (20px) finestre · `999px` pillole · `50%` cerchi. **Nessun altro valore** **(da fare: oggi 15)**.
  Un elemento con sfondo proprio sul bordo di un riquadro ne segue gli angoli (niente spigoli che sporgono).
- Ombre: `--shadow-card` riquadri · `--shadow-sm/md/lg` per menu, popup, finestre. Niente ombre colorate.
- Movimento: `--transition` (0,18s) per colori e hover; aperture e chiusure 0,2–0,25s con curva morbida
  (`--sidebar-ease`); niente oltre 0,3s salvo i caricamenti. **Sempre** `prefers-reduced-motion: reduce` che spegne
  le animazioni.

## 6. Impaginazione
### 6.1 Struttura della pagina
- **Menu laterale** a sinistra: icone + nomi o solo icone (pulsante a pannello in alto, scelta ricordata); su
  telefono è nascosto e si apre con ☰ dalla barra in alto.
- **Barra in alto** (60px): a sinistra **sempre** titolo della pagina + percorso (Home / …); a destra le azioni,
  ancorate a destra e sempre nello stesso ordine, che dà il CSS (`.topbar-actions > …` con `order`):
  Periodo → Preset/Viste/Scenari/Orizzonte → Confronta → altre azioni (PDF, CSV, Nuovo…) → Modifica → Gestisci.
  I template usano le classi giuste e non si occupano dell'ordine. **(da fare)** Transazioni oggi non mostra il titolo.
- **Periodo**: un solo selettore in tutta l'app, il riquadro di `partials/period_box.html` (`period_box`,
  `choice_box`, `year_box`). Una pagina che ha bisogno di meno usa lo stesso riquadro con meno controlli.
- **Schede** sotto la barra: sempre **sottolineate** (`partials/tabs.html`, `tab_bar`). Le pillole sono solo per
  filtri e interruttori. **Al massimo 7 schede** per pagina: le altre in una scheda «Altro» o in sottosezioni (UI-14)
  **(da fare: il Portafoglio ne ha 13)**.
- **Funzioni non pronte**: il badge «TBD» nel menu e nelle schede **resta visibile** a tutti (UI-13): dice che la
  sezione funziona ma è da rivedere; si toglie quando la sezione supera l'elenco «sezione finita» del piano (T07).

### 6.2 Larghezze a cui la pagina si ridispone **(da fare: oggi 15 diverse)**
Solo quattro: **576px** (telefono) · **768px** (tablet verticale) · **992px** (il menu laterale diventa a scomparsa)
· **1200px** (desktop largo).

### 6.3 Pulsanti fluttuanti
Il + (nuova transazione o file, tasto «n») in basso a sinistra, l'assistente AI e «torna su/giù» in basso a destra.
Il fondo di ogni pagina lascia lo spazio perché non coprano contenuto (ultima riga, colonna Importo) **(da fare)**.

## 7. Componenti
### 7.1 Pulsanti
| Classe | Quando |
|---|---|
| `btn btn-primary` | l'azione principale della vista — **al massimo uno** (Nuovo conto, Salva, Applica…) |
| `btn btn-outline` | azione secondaria importante |
| `btn btn-ghost` | azioni di servizio (CSV, Controlla registro, Azzera…) |
| `btn btn-danger` / `btn-danger-ghost` | eliminare; sempre con domanda di conferma (`data-confirm` / `mfpConfirm`) |
| `btn-sm`, `btn-icon` | dimensione piccola; solo icona (con `title` e `aria-label`) |

Testo del pulsante: verbo + oggetto, prima lettera maiuscola («Aggiungi posizione»). I pulsanti disattivati si
evitano se si può spiegare cosa manca.

### 7.2 Riquadri e pannelli
- Riquadro: `.card` con `.card-header` (titolo + sottotitolo a sinistra, azioni piccole a destra) e `.card-body`.
- Titolo con trattino lungo solo per «Sezione — sottosezione» nelle impostazioni; altrove titoli semplici.
- Pannelli che si aprono e chiudono: dentro il riquadro a cui servono (non riquadri a sé sopra), stato ricordato
  nel browser (`store`, chiavi `mfp-…`).

### 7.3 Tabelle
- **Compatte di default** ovunque (UI-11). Importi a destra, in `--font-mono`, con segno e colore; date `gg/mm/aaaa`.
- Intestazioni in maiuscoletto 11px; clic per ordinare (freccia sulla colonna in uso); imbuto per filtrare una
  colonna; larghezze trascinabili dove serve.
- Testi lunghi: si tagliano con «…» **solo** se il testo completo resta leggibile al passaggio del mouse (`title`)
  o nella modifica; le categorie hanno una larghezza minima che lascia leggere la parola.
- Sopra le colonne, dentro il riquadro, la **barra della tabella** (modello Transazioni): ricerca compatta (30px,
  parte con Invio, senza pulsante «Cerca»), pillole «Viste» e «Modifica massiva · selezionate/trovate». Sotto, la
  **riga dei filtri**, sempre visibile (UI-17): il tipo come interruttore a pillole, le tendine principali da 28px
  con il nome nel valore vuoto («Tutte le categorie»), l'importo «€ da – a» scritto a mano e la pillola «Altro · N»
  per i filtri meno usati. Un filtro attivo ha il bordo arancio. Le date non sono filtri: le decide il Periodo.
  Il pannello della modifica massiva si apre sotto la barra con controlli da 28px, 4 per riga (2 su tablet, 1 su telefono).
- Le righe si aprono con un clic per la modifica rapida; le azioni di riga (matita, cestino) a destra.
- **Su telefono** (sotto 576px) solo le colonne essenziali (data, descrizione, importo; le altre si nascondono) e
  scorrimento orizzontale dentro il riquadro, mai la pagina tagliata a destra; righe a scheda solo nelle liste brevi
  (UI-16) **(da fare)**.

### 7.4 KPI
Macro `kpi()` di `partials/kpi.html`: etichetta in maiuscoletto, cifra grande, nota sotto, icona nel quadratino.
Il colore (`cls`) segue la tabella 2.2; **l'arancio non si usa per i KPI** **(da fare: Patrimonio netto, Valore
totale del portafoglio)**.

### 7.5 Badge, tag, pillole
- `badge-positive/negative/warning/neutral/muted/primary`: brevi stati e categorie.
- **Categorie** con badge neutro (o il colore del suo gruppo di spesa), **conteggi** in testo normale: niente
  arancio, che resta alle azioni (UI-15) **(da fare)**.
- Tag: `tag-chip` (link al filtro di quel tag).
- Pillole (999px): filtri e interruttori, mai navigazione.

### 7.6 Form
Etichetta sopra il campo; altezza 36px nei form, 28–30px nei pannelli compatti; segnaposto con un esempio reale;
errori sotto il campo, in rosso, con cosa fare. Le stesse parti comuni di `partials/fields.html`.

### 7.7 Spiegazioni (tooltip)
«Tooltip» = l'icona **«i»** con una schedina (macro `info()` di `partials/info.html`), nello stesso rigo del titolo,
mai a capo da sola. Testo: una frase, solo su ciò che non è ovvio; un elenco di tipi va un punto per riga. Il `title`
del browser è un'altra cosa: solo il suggerimento al passaggio del mouse su elementi cliccabili.

### 7.8 Stati vuoti, avvisi, conferme
- Pagina o tabella vuota: `empty_state()` di `partials/empty.html` con titolo, una riga e il pulsante per iniziare.
- Avvisi: `.alert-info/-warning/…` sopra il riquadro a cui si riferiscono; dopo un'azione annullabile la barra
  Annulla/Ripeti (Ctrl+Z / Ctrl+Y).
- Ogni eliminazione chiede conferma e dice quante cose elimina.

## 8. Numeri, valute, date
Sempre all'italiana con i filtri dell'app (`money`, `number`, `it_date`, `pct`…), mai formattati a mano:
`€ 1.234,56`, `−€ 27,09`, `+€ 2.600,00`, `4,01%`, `24/10/2026`. Uscite con il meno e in rosso, entrate con il più
e in verde, trasferimenti con ⇄ e colore neutro. Le valute diverse dall'euro mostrano sotto il controvalore «≈ €».

## 9. Grafici
- Chart.js per i grafici normali (`partials/charts.html`); D3 solo dove Chart.js non basta.
- Colori: prima quelli di significato (2.2), poi `--chart-1…8` per le serie senza significato proprio.
- Legenda cliccabile per nascondere serie; «Deseleziona tutto» quando le serie sono tante; le etichette della
  legenda non si troncano a metà parola.
- Assi e numeri nel formato italiano; niente decimali inutili sugli assi.
- Etichette dirette sulle linee al posto delle legende lunghe; **un solo numero in evidenza** per grafico (l'«oggi» o
  il totale); il confronto (mese scorso, anno scorso, budget) sempre **tratteggiato e grigio**, mai un secondo colore.
- Un clic su una barra, un mese o una categoria apre le transazioni filtrate.
- Al massimo una ciambella per pagina; niente torte.
- **Grafico senza i dati che gli servono** (UI-19): si mostra lo stesso, con uno schizzo grigio al posto delle serie
  e l'icona «i» che dice cosa manca e quando si riempirà («Servono i prezzi giornalieri: arrivano con la Fase 2 del
  Portafoglio»). Niente dati inventati.

### 9.1 Dashboard (UI-18)
Dall'urgente al lento, in fasce:
1. **Come sto** — una riga di 4 numeri: patrimonio netto (con variazione del mese e linea minima), risparmio del mese
   contro la media, mesi coperti dalla liquidità (barra verso l'obiettivo), «Da sistemare».
2. **Questo mese** — ritmo di spesa, ponte del mese (cascata), dove va il denaro (Sankey o treemap), budget più vicini
   al limite, prossimi 30 giorni.
3. **Nel tempo** — patrimonio, valore contro versato, risparmio per anno; chiusa di default, la pagina ricorda la scelta.
4. **Futuro** — saldo dei prossimi 12 mesi, uscite grosse dell'anno; con la «i» (UI-19) finché mancano: patrimonio
   tra 10 anni, pensione e FIRE, obiettivi, debiti, rendite.

Il redesign delle altre schermate sullo stesso modello è in bozza in
[REDESIGN_SCHERMATE.md](../piano/REDESIGN_SCHERMATE.md).

Le opzioni di ogni riquadro (confronto, serie, vista alternativa, export) stanno dietro il suo ⋯; «Gestisci» sceglie
riquadri, ordine e fasce aperte. «Ultime transazioni» non è più in dashboard (ripete il registro).

## 10. Testi
- Italiano; termini inglesi solo se non hanno un uso comune in italiano (ETF, IBAN, PAC, KPI). Niente «Defaults»,
  «Backtest» come etichetta senza spiegazione.
- Tutti i testi con `_()` (catalogo inglese in `app/translations/`).
- Messaggi di errore: cosa è successo e cosa fare, in una frase.

## 11. Accessibilità
Contrasto sufficiente in entrambi i temi; focus visibile su ogni controllo; pulsanti solo icona con `aria-label`;
pannelli con `aria-expanded`/`aria-controls`; niente informazioni affidate solo al colore (segno ±, icona o testo).

## 12. Regole per chi sviluppa
- **Niente `style="…"` nei template** (oggi 626, da ridurre): classi in `main.css`.
- Colori, dimensioni, angoli e durate solo tramite le variabili; nessun codice colore a mano.
- CSS nuovo in una sezione con il suo titolo di commento in `main.css` (in inglese), vicino ai componenti simili.
- Prima di un elemento nuovo si cerca la macro esistente; se manca, la si crea in `partials/`.
- Modifiche solo visive: lint (`ruff check .`) e screenshot; i test si lanciano a fine sessione o su richiesta.

## 13. Checklist per una pagina nuova o rifatta
- [ ] Barra in alto: titolo + percorso a sinistra, azioni a destra con le classi dell'ordine; Periodo con il riquadro comune.
- [ ] Al massimo un pulsante arancio pieno.
- [ ] Colori di significato rispettati (verde, rosso, blu investimenti, viola debiti); arancio solo per azioni.
- [ ] Testi con `_()`, solo prima lettera maiuscola, niente inglese evitabile; «i» dove qualcosa non è chiaro.
- [ ] Nessuno `style="…"`, nessun colore o dimensione fuori variabili.
- [ ] Tabelle compatte, importi a destra con il formato italiano.
- [ ] Stato vuoto con `empty_state()`.
- [ ] Guardata in chiaro e in scuro, a 1440px, 992px e a larghezza di telefono; niente testi tagliati illeggibili,
      niente pulsanti fluttuanti sopra il contenuto.
- [ ] Animazioni spente con «riduci animazioni».

## 14. Decisioni aperte
Nessuna (le A1–A5 del 18 nov sono diventate UI-12…UI-16). Una domanda nuova si scrive qui con la sua proposta.

| # | Domanda | Proposta |
|---|---|---|

## 15. Registro delle decisioni
| ID | Data | Decisione |
|---|---|---|
| UI-01 | 30 set 2026 | Menu laterale: icone + nomi o solo icone, con il pulsante a pannello in alto nel menu; animazione fluida (le icone non si spostano), niente logo né nome dell'app nel menu |
| UI-02 | 1 nov 2026 | «Tooltip» = icona «i» con schedina; testi brevi, solo su ciò che non è chiaro |
| UI-03 | 2 nov 2026 | Colori: contanti verde, debiti viola (riservato), investimenti blu |
| UI-04 | 2 nov 2026 | Transazioni: ricerca, filtri e modifica massiva dentro il riquadro della tabella, con pannelli compatti (proposta B); importo «Da»/«A» scritto a mano |
| UI-05 | 15 nov 2026 | Un solo selettore del periodo (`period_box`), condiviso tra le pagine di analisi |
| UI-06 | 16 nov 2026 | Barra in alto ancorata a destra con ordine fisso; schede sempre sottolineate, pillole solo per filtri e interruttori |
| UI-07 | 18 nov 2026 | Maiuscole: solo la prima lettera in titoli, pulsanti, schede e menu |
| UI-08 | 18 nov 2026 | Il blu è degli investimenti: trasferimenti e informazioni passano a un colore neutro non blu |
| UI-09 | 18 nov 2026 | Due spessori del testo: 400 e 600 |
| UI-10 | 18 nov 2026 | Al massimo un pulsante arancio pieno per vista |
| UI-11 | 18 nov 2026 | Tabelle compatte di default |
| UI-12 | 18 nov 2026 | Il codice vecchio si allinea con card di pulizia nel piano (T42–T48, giro D), in ordine di impatto |
| UI-13 | 18 nov 2026 | Il badge «TBD» resta visibile a tutti finché la sezione non supera l'elenco «sezione finita» |
| UI-14 | 18 nov 2026 | Al massimo 7 schede per pagina, il resto in «Altro» o in sottosezioni |
| UI-15 | 18 nov 2026 | Categorie con badge neutro (o colore del gruppo di spesa), conteggi in testo normale: niente arancio |
| UI-16 | 18 nov 2026 | Tabelle su telefono: colonne essenziali e scorrimento dentro il riquadro; righe a scheda solo nelle liste brevi |
| UI-17 | 18 nov 2026 | Filtri di Transazioni (aggiorna UI-04): una riga compatta sempre visibile — tipo a pillole, Categoria, Conto, Tag, importo «da – a», «Altro» (Verso il conto, Persona, Gruppo, Solo ricorrenti); niente Dal/Al/Mese dove c'è il Periodo; niente pulsante «Cerca»; «Classifica con AI» e «Da confermare» come pulsanti leggeri |
| UI-18 | 18 nov 2026 | Dashboard in fasce: Come sto · Questo mese · Nel tempo (chiusa) · Futuro; grafici nuovi: ritmo di spesa, ponte del mese, prossimi 30 giorni, valore contro versato, budget al limite, treemap; via «Ultime transazioni»; opzioni dietro il ⋯ |
| UI-19 | 18 nov 2026 | Un grafico senza dati si mostra con uno schizzo grigio e la «i» che dice cosa manca e quando arriverà |
| UI-20 | 21 nov 2026 | Dashboard: via le vecchie schede numeriche in alto; «Come sto» sono 4 numeri (patrimonio netto con linea e variazione del mese, risparmio del mese contro la media, mesi coperti dalla liquidità, da sistemare); il loro contenuto va nelle schede Panoramica · Questo mese · Patrimonio · Investimenti, ognuna con la sua «Modifica»; la mappa a riquadri dice dove va il denaro, il Sankey è il riquadro dei flussi |
| UI-21 | 21 nov 2026 | Conti e Carte, Obiettivi, Budget, Promemoria (con Eventi come scheda), Previsioni e Debiti passano allo stile a schede, non a riquadri impilati: proposta in REDESIGN_SCHERMATE.md |
| UI-22 | 21 nov 2026 | Ponte del mese: mostra il mese del periodo in alto (il mese in corso se c'è, se no l'ultimo) e lo scrive; conta solo entrate e spese vere (giroconti, prelievi e riconciliazioni no); in fondo «Risparmi» in verde, oppure, se si è speso più delle entrate, «Presi dai risparmi» in grigio sopra le entrate, così la cascata scende sempre a zero |

## 16. Fotografia di partenza (18 nov 2026)
Da dove si parte, per misurare i progressi della pulizia:
626 `style="…"` in 133 template (record: `export/bank_preview.html` 47, `settings/ai.html` 29, `settings/index.html` 29);
15 dimensioni del testo fuori scala; 15 raggi d'angolo; 15 larghezze di ridisposizione; 11 durate di animazione;
14 codici colore e 11 trasparenze in `main.css` fuori variabili; variabili usate ma non definite: `--border`,
`--shadow-card-hover`; `font-weight` 700 usato 55 volte; `main.css` di 2.491 righe; 166 icone diverse.
