# 🗺️ MyFinancePlace — Roadmap

> Ordine di sviluppo delle sezioni dell'app. Nella sidebar le voci fuori dall'MVP
> sono marcate con un badge: **`v2`** = fase 2, **`TBD`** = fase 3 / da definire.
> Le pagine restano raggiungibili, ma non sono ancora considerate "finite".

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
| **Transazioni** | Gestione → Transazioni | Inserimento, modifica, categorie, filtri; partita doppia sempre bilanciata |
| **Spese e Tendenze** | Stile di Vita → Spese e Tendenze | Dove vanno i soldi: spese per categoria e andamento nel tempo |
| **Budget** | Stile di Vita → Budget | Budget mensile per categoria, speso vs previsto |
| **Obiettivi** | Stile di Vita → Obiettivi | Obiettivi di risparmio con avanzamento |
| **Previsioni** | Contabilità → Previsioni | Proiezione del saldo futuro da ricorrenze e budget |
| **Dashboard** | Panoramica → Dashboard | Riepilogo: saldo, spese del mese, budget, obiettivi, previsione |

🧱 Di supporto all'MVP (senza badge): **Conti e Carte** (le transazioni ne hanno bisogno), **Impostazioni**.

- [ ] Transazioni
- [ ] Spese e Tendenze
- [ ] Budget
- [ ] Obiettivi
- [ ] Previsioni
- [ ] Dashboard

### Requisiti MVP in dettaglio

#### 1. Dashboard — grafici "snapshot sul totale" (sull'anno)

Quattro grafici in coppia, entrate a sinistra e uscite a destra:

| | Entrate | Uscite |
|---|---|---|
| **Torta** | Ripartizione del totale per categoria di entrata | Ripartizione del totale per categoria di uscita *(esiste già)* |
| **Linee per categoria** | Asse X: 12 mesi dell'anno. Asse Y: € per mese. Una linea per categoria di entrata, che unisce i punti mese per mese | Uguale, una linea per categoria di uscita |

Più due istogrammi di riepilogo:

- [ ] **Totale per mese**: una barra per mese con il netto (entrate − uscite); negativo sotto lo zero
- [ ] **Totale complessivo annuo**: tre barre per entrate annue, uscite annue e netto annuo
- [ ] Torta delle entrate
- [ ] Linee mensili per categoria (entrate)
- [ ] Linee mensili per categoria (uscite)

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

- [ ] Seed delle categorie di base (senza duplicare quelle già presenti)

#### 3. Transazioni — form e lista semplificati

- **Entrata o uscita si capisce dal segno** dell'importo: `+` è un'entrata, `−` è un'uscita. Il campo "tipo" separato sparisce per entrate e uscite; i trasferimenti tra conti restano a parte.
- **Colonne**: Data · Descrizione (causale) · Categoria · Tag · Importo con segno.
- **La controparte diventa un tag**: il campo "Controparte" viene tolto; il suo valore passa nei tag (con migrazione delle transazioni esistenti).
- **Tag da un pool**: scegli da un menu a tendina con ricerca i tag già usati, oppure ne crei uno nuovo scrivendolo (input a "chip").

- [ ] Importo con segno al posto del tipo entrata/uscita
- [ ] Controparte migrata nei tag e campo rimosso
- [ ] Selettore tag con autocompletamento e creazione al volo

---

## 🔵 Fase 2 — Contabilità e rendiconti personali (`v2`)

| Sezione | Sidebar |
|---|---|
| **Panoramica contabile** | Contabilità → Panoramica |
| **Stato Patrimoniale** | Contabilità → Stato Patrimoniale |
| **Conto Economico** | Contabilità → Conto Economico |
| **Flusso di Cassa** | Contabilità → Flusso di Cassa |

- [ ] Panoramica contabile
- [ ] Stato Patrimoniale
- [ ] Conto Economico
- [ ] Flusso di Cassa

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

---

## Come aggiornare

Quando una sezione passa di fase: sposta la riga qui sopra e cambia (o togli) il
badge in `app/templates/base.html` (`nav-badge-next` = `v2`, `nav-badge-tbd` = `TBD`).
