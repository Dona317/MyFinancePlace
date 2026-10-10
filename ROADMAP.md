# 🗺️ MyFinancePlace — Roadmap

> Ordine di sviluppo delle sezioni dell'app. Nella sidebar le voci fuori dall'MVP
> sono marcate con un badge: **`v2`** = fase 2, **`TBD`** = fase 3 / da definire.
> Le pagine restano raggiungibili, ma non sono ancora considerate "finite".
>
> **Stato al 1° ottobre 2026**: spuntato ciò che nell'app c'è e funziona (verificato nel codice e dai test).
> L'MVP è completo; la partita doppia è stata scartata (vedi [Scartato](#scartato)).

| Legenda | Significato |
|---|---|
| 🟢 | MVP — priorità attuale |
| 🔵 | Fase 2 — subito dopo l'MVP (badge `v2`) |
| ⚪ | Fase 3 — il resto (badge `TBD`) |
| 🧱 | Infrastruttura necessaria all'MVP (nessun badge) |

---

## 🟢 Fase 1 — MVP

Il ciclo base: registro i movimenti, li confronto con un budget, vedo dove sto andando.

| Sezione | Sidebar | Obiettivo |
|---|---|---|
| **Transazioni** | Gestione → Transazioni | Inserimento, modifica, categorie, filtri |
| **Spese e Tendenze** | Stile di Vita → Spese e Tendenze | Dove vanno i soldi: spese per categoria e andamento nel tempo |
| **Budget** | Stile di Vita → Budget | Budget mensile per categoria, speso vs previsto |
| **Obiettivi** | Stile di Vita → Obiettivi | Obiettivi di risparmio con avanzamento |
| **Previsioni** | Contabilità → Previsioni | Proiezione del saldo futuro da ricorrenze e budget |
| **Dashboard** | Panoramica → Dashboard | Riepilogo: saldo, spese del mese, budget, obiettivi, previsione |

🧱 Di supporto all'MVP (senza badge): **Conti e Carte** (le transazioni ne hanno bisogno), **Impostazioni**.

- [x] Transazioni — inserimento/modifica, categorie e sottocategorie, tag, filtri, ricerca duplicati, import estratti conto
- [x] Spese e Tendenze — spese per categoria (principale), andamento mensile, confronto mese su mese
- [x] Budget — per categoria e per mese, speso vs previsto, avvisi all'80% e al superamento; un budget sulla categoria principale conta anche le sottocategorie
- [x] Obiettivi — obiettivi di risparmio con versamenti e quota mensile necessaria
- [x] Previsioni — ricorrenze + spese variabili su N mesi, sei metodi confrontati sul passato
- [x] Dashboard — KPI, budget del mese, flusso di cassa, grafici qui sotto

### Requisiti MVP in dettaglio

#### 1. Dashboard — grafici "snapshot sul totale" (sull'anno)

Quattro grafici in coppia, entrate a sinistra e uscite a destra:

| | Entrate | Uscite |
|---|---|---|
| **Torta** | Ripartizione del totale per categoria di entrata | Ripartizione del totale per categoria di uscita *(esiste già)* |
| **Linee per categoria** | Asse X: 12 mesi dell'anno. Asse Y: € per mese. Una linea per categoria di entrata, che unisce i punti mese per mese | Uguale, una linea per categoria di uscita |

Più due istogrammi di riepilogo:

- [x] **Totale per mese**: una barra per mese con il netto (entrate − uscite); negativo sotto lo zero (rosso)
- [x] **Totale complessivo annuo**: tre barre per entrate annue, uscite annue e netto annuo
- [x] **In più: diagramma Sankey** "Dove va il denaro": categorie di entrata → entrate totali → categorie di uscita
  e risparmio (o "Dai risparmi" se l'anno chiude in perdita); disegnato dal server, funziona anche offline
- [x] Torta delle entrate
- [x] Linee mensili per categoria (entrate)
- [x] Linee mensili per categoria (uscite)

#### 2. Categorie di base (tutte modificabili)

Da seminare come categorie di default. Si possono rinominare, unire, aggiungere ed eliminare da Impostazioni → Categorie.

| Entrate | Uscite |
|---|---|
| Lavoro ISolutions | Salute |
| Lavoro lezioni private | Ristorante |
| Vendita tra privati | Piccole consumazioni |
| Regali | Spesa |
| Lavoro da freelancer | Cultura |
| Trovati | Shopping (vestiti, cosmetici, …) |
| Altro | Trasporti |
| | Giochi / svago |
| | Viaggi |
| | Gift |
| | Calcetto |
| | Abbonamenti |
| | Elettronica |
| | Macchina |
| | Palestra |
| | Altro |

- [x] Seed delle categorie di base (senza duplicare quelle già presenti) — aggiunte una sola volta le 15 nuove;
  le 7 già presenti con lo stesso nome o quasi (Altro, Salute, Ristorante~Ristoranti, Shopping, Trasporti~Trasporto,
  Viaggi, Abbonamenti) non sono state duplicate

#### 3. Transazioni — form e lista semplificati

- **Entrata o uscita si capisce dal segno** dell'importo: `+` è un'entrata, `−` è un'uscita. Il campo "tipo" separato sparisce per entrate e uscite; i trasferimenti tra conti restano a parte.
- **Colonne**: Data · Descrizione (causale) · Categoria · Tag · Importo con segno.
- **La controparte diventa un tag**: il campo "Controparte" viene tolto; il suo valore passa nei tag (con migrazione delle transazioni esistenti).
- **Tag da un pool**: scegli da un menu a tendina con ricerca i tag già usati, oppure ne crei uno nuovo scrivendolo (input a "chip").

- [x] Importo con segno al posto del tipo entrata/uscita
- [x] Controparte migrata nei tag e campo rimosso (migrazione `b7c1d2e3f4a5`); all'import l'esercente è letto dalla causale
- [x] Selettore tag con autocompletamento e creazione al volo

---

## 🔵 Fase 2 — Contabilità e rendiconti personali (`v2`)

| Sezione | Sidebar |
|---|---|
| **Panoramica contabile** | Contabilità → Panoramica |
| **Stato Patrimoniale** | Contabilità → Stato Patrimoniale |
| **Conto Economico** | Contabilità → Conto Economico |
| **Flusso di Cassa** | Contabilità → Flusso di Cassa |

Le pagine esistono già e funzionano; il badge `v2` resta finché non decidi che sono "finite".

- [x] Panoramica contabile — pagina funzionante, da rifinire
- [x] Stato Patrimoniale — attività, passività, patrimonio netto anche a fine mese passati — da rifinire
- [x] Conto Economico — da rifinire
- [x] Flusso di Cassa — operativo / investimenti / finanziamenti — da rifinire

---

## ⚪ Fase 3 — Il resto (`TBD`)

Ordine interno da definire.

| Sezione | Sidebar |
|---|---|
| Portafoglio | Gestione → Portafoglio |
| Debiti | Gestione → Debiti |
| Assicurazioni | Gestione → Assicurazioni |
| Documenti | Gestione → Documenti |
| Istantanee | Strumenti → Istantanee |
| Esporta | Strumenti → Esporta |

Anche queste pagine sono già funzionanti (portafoglio con plus/minusvalenze, piano di ammortamento dei debiti,
scadenze delle polizze, archivio documenti, istantanee confrontabili, export CSV/JSON/PDF e backup completo):
il badge `TBD` indica la priorità, non che manchino.

---

## Fatto oltre la roadmap

- **Sottocategorie** (Bollette › Luce…) con totali raggruppati per categoria principale
- **Import estratti conto**: 8 banche + formato generico (Excel, CSV, PDF, Word, ODF, RTF); scansioni e foto con OCR
  leggero; colonne riconosciute dai valori nell'import manuale (AI su un campione come riserva)
- **Esercente letto dalla causale** e **categorie suggerite dal tuo storico**, prima di chiedere all'AI
- **Report** (spese, entrate, cash flow per periodo e conto), **login** con utenti gestiti dall'amministratore,
  **saldi nella valuta del conto**, **backup completo**, interfaccia italiano/inglese, Docker

## Scartato

- ~~Transazioni: **partita doppia** sempre bilanciata~~ — idea scartata per non complicare l'app: bastano i giroconti
  tra conti e la riconciliazione col saldo della banca

---

## Come aggiornare

Quando una sezione passa di fase: sposta la riga qui sopra e cambia (o togli) il
badge in `app/templates/base.html` (`nav-badge-next` = `v2`, `nav-badge-tbd` = `TBD`).
