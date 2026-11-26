# Redesign delle schermate principali — bozza (20 nov 2026)

Il piano per portare ogni schermata principale allo stesso modello della dashboard (UI-18): **dall'urgente al lento**,
una domanda chiara per pagina, le opzioni dietro il ⋯, i dati prima della decorazione. Le regole comuni sono in
[DESIGN.md](../tecnica/DESIGN.md); qui c'è cosa cambia pagina per pagina.

**Stato: bozza da discutere.** Le pagine non sono state riviste a schermo una per una: ogni scheda va confermata
guardando la pagina sul server demo prima di scrivere codice. Quando una scheda è decisa, la sua scelta va nel
registro di DESIGN.md (UI-nn) e il lavoro diventa una card del piano.

---

## Piano di riallineamento grafico (26 nov 2026) — il piano in corso

In tre settimane sono state rifatte dashboard, Budget, Promemoria, Conti, Debiti, Obiettivi e Previsioni; le altre
pagine sono rimaste com'erano. Ricognizione del 26 nov:
- in cima alle pagine convivono due modelli: `stat_row` in 6 pagine, le schede `kpi()` in circa 30;
- le schede hanno 5 stili;
- il periodo si sceglie in 6 modi;
- ci sono circa 11 KPI sempre arancio e fino a 5 pulsanti arancio pieni per vista;
- titoli, menu e schede usano nomi diversi;
- in alcune etichette c'è ancora inglese.

Le card T42–T48 sono tutte aperte (674 stili scritti a mano, 57 pesi 700 e 21 pesi 500, 17 larghezze di
ridisposizione, `--clr-neutral` ancora blu). Le decisioni del 26 nov sono **UI-51…UI-54** in DESIGN.md.

**Checklist «pagina allineata»**:
1. barra in alto con titolo uguale al menu e un solo `btn-primary`;
2. periodo solo nel riquadro della barra (UI-52);
3. `stat_row` al posto di `kpi()`, con i colori di significato;
4. schede `tab_bar` in `page-tabs` (UI-53);
5. prima lettera maiuscola, italiano;
6. tabelle compatte, `empty_state()`, «i» per i dati mancanti;
7. nessuno stile scritto a mano nuovo;
8. pagina guardata in chiaro e scuro a 1440, 992 e 375 px;
9. badge TBD tolto (UI-54).

| Giro | Cosa | Stato |
|---|---|---|
| 0 Fondamenta | colori (T42), riga dei numeri unica (`kpi()` disegna una cella della riga), `tab_bar` a due livelli con la riga sotto le schede, variabili (T47: spaziature, raggi, 4 larghezze), pesi 400/600 (T46), `scripts/design_audit.py` come metro | fatto il 26 nov; il periodo «solo mese» va nel giro 5 (Budget) |
| 1 Movimenti | Transazioni + Conti (secondo livello), Ricorrenti, Report e sotto-pagine, Panoramica Finanziaria | da fare |
| 2 Patrimonio | Portafoglio (10 schede → due livelli ≤ 7, «Portafoglio» in italiano, KPI → riga), Fisco | da fare |
| 3 Servizio | Assicurazioni, Bollette, Lavoretti, Prestiti, Documenti, Istantanee, Clienti, Gruppi | da fare |
| 4 Strumenti | Importa ed Esporta, Salute dei dati, Impostazioni | da fare |
| 5 Rifiniture | Dashboard, Previsioni (una riga, «Modifica» al posto di «Personalizza»), Pensione, Promemoria, Budget (periodo), Debiti | da fare |

Trasversali a ogni giro: telefono (T43, UI-16) e stili scritti a mano (T48). Ogni giro si chiude con la checklist,
`scripts/design_audit.py` con i numeri che scendono, commit e push. Obiettivo finale: 0 `kpi(` fuori dalla dashboard,
1 stile di schede, ≤ 1 `btn-primary` per vista, 0 pesi 500/700, 4 larghezze, meno di 50 stili scritti a mano.

---

## Lo schema comune (vale per tutte)

| Parte | Cosa | Regola |
|---|---|---|
| Barra in alto | Titolo e percorso a sinistra; a destra Periodo → viste → Confronta → azioni → Modifica → Gestisci | UI-06, già decisa |
| Riga «come sto» | 3–4 numeri della pagina, mai più di 4, senza grafici grandi | nuova, da UI-18 |
| Contenuto principale | La tabella o il grafico che risponde alla domanda della pagina | uno solo in evidenza |
| Approfondimenti | Grafici e tabelle di analisi, in una fascia chiudibile («Nel tempo», «Dettagli») | ricordata nel browser |
| Opzioni | Dietro il ⋯ del riquadro o in «Gestisci» | UI-18 |
| Schede | Al massimo 7, il resto in «Altro» | UI-14 |
| Vuoto | `empty_state()` con l'azione per iniziare | sezione 7.8 |
| Dati che mancano | Schizzo grigio e «i» con cosa manca | UI-19 |

---

## Schede, non riquadri (21 nov 2026) — Conti e Carte, Obiettivi, Budget, Promemoria con Eventi, Previsioni, Debiti

Richiesta del 21 nov: queste pagine passano allo **stile a schede** della dashboard. Oggi sono pile di riquadri
(Previsioni ne ha 51, Promemoria 20, Budget 13, Debiti 10, Obiettivi 9) con 3–5 schede numeriche in cima. Il modello:

1. **Barra in alto** come sempre (titolo, Periodo dove serve, azioni, «Modifica» dove ci sono blocchi).
2. **Riga «come sto»**: 3–4 numeri compatti al posto delle schede numeriche grandi, come nella dashboard.
3. **Schede sottolineate** (`tab_bar`, ≤ 7): ogni scheda è una domanda; dentro, una tabella o un grafico principale
   e, se serve, pochi blocchi spostabili. Niente riquadri impilati uno sotto l'altro.
4. **Nuovo / Modifica nel pop-up** (T07), export in ogni tabella (T08), vuoti con `empty_state()`, dati che mancano
   con la «i» (UI-19).

| Pagina | Riga «come sto» | Schede |
|---|---|---|
| **Conti e Carte** | liquidità · carte (speso / plafond) · conti da riconciliare · ultimo aggiornamento | **Conti** (tabella compatta per tipo; la Panoramica è stata tolta, UI-30) · **Carte** · **Riconciliazioni** (storico, promemoria T11, candidati T12) · **Collegamenti bancari** (UI-23) |
| **Obiettivi** | totale messo da parte · obiettivi in linea / in ritardo · prossima scadenza | **Obiettivi** (una riga per obiettivo: barra, data prevista, versamento che servirebbe) · **Fondo d'emergenza** · **Versamenti** (storico) · **Suggeriti** |
| **Budget** | speso / previsto del mese · giorni passati · categorie sforate | **Questo mese** (ritmo di spesa + barre con la tacca) · **Categorie** (tabella dei budget, modifica in riga) · **Accantonamenti** · **Storico** (mese per mese) |
| **Promemoria** (con **Eventi**) | uscite previste nei 30 giorni · la più grossa · senza importo · eventi in corso | **Prossimi** (lista per settimana, «Fatto»/«Sposta») · **Calendario** · **Eventi** (oggi pagina a sé: elenco, budget dell'evento, movimenti assegnati) · **Ricorrenti** |
| **Previsioni** | saldo fra 12 mesi · mese più basso · metodo usato | **Prossimi 12 mesi** (saldo con banda, eventi segnati) · **Mese per mese** (tabella) · **Metodi** (confronto ed errori, oggi in vista) · **Pensione e FIRE** (oggi pagina a sé) |
| **Debiti** | debito residuo (viola) · rata mensile · interessi ancora da pagare · data di fine | **Panoramica** (residuo fino all'estinzione, contratto tratteggiato) · **Debiti** (tabella) · **Ammortamento** (quota capitale e interessi per anno) · **Strumenti** (anticipo, valanga contro palla di neve: T24–T25) |

**Eventi dentro Promemoria:** la voce «Eventi» del menu diventa la scheda «Eventi» di Promemoria; il vecchio indirizzo
`/events/` porta lì, la pagina di dettaglio di un evento resta com'è.

**Da decidere:** l'ordine (proposta: Budget → Promemoria con Eventi → Conti e Carte → Debiti → Obiettivi → Previsioni,
dalla più usata) e se in queste pagine serve «Modifica» per spostare i blocchi o bastano le schede fisse.

---

## Le schede, in ordine di uso

### 1. Dashboard — «Come sto, e cosa devo fare?»  ✅ in corso (UI-18)
Fasce: Come sto (KPI, Salute finanziaria, Da sistemare) · Questo mese (ritmo di spesa, bridge del mese, prossimi 30
giorni, budget al limite, Sankey) · Nel tempo (chiusa) · Futuro (chiusa). Restano da fare: le opzioni dietro il ⋯,
la treemap come seconda vista del Sankey, i grafici con la «i».

### 2. Transazioni — «Cosa è successo, e cosa va sistemato?»
- **Già fatto:** riga dei filtri B (UI-17), niente card in cima.
- **Proposta:** sopra la tabella una riga sottile di 3 numeri del periodo (entrate, uscite, netto), cliccabili come
  filtro del tipo; le righe «da sistemare» (senza categoria, da confermare AI) segnate con un pallino e raggiungibili
  con un filtro rapido; colonna Conto mostrabile da «Colonne»; azioni di intestazione ridotte a due visibili
  («Controlla registro», «Classifica con AI»), il resto (CSV, Excel, Compila controparti) dietro un ⋯.
- **Telefono:** data, descrizione, importo; categoria sotto la descrizione (UI-16).

### 3. Conti e Carte — «Quanto ho, e dove?»
- **Riga come sto:** liquidità totale, carte (speso nel mese / plafond), conti da riconciliare.
- **Principale:** i conti come elenco compatto raggruppato per tipo (correnti, risparmio, titoli, debito) con saldo,
  andamento a 3 mesi in linea minima e data dell'ultima riconciliazione; un clic apre il conto.
- **Pagina del conto:** saldo nel tempo (G32) in alto, poi il registro del solo conto con saldo progressivo, poi lo
  storico delle riconciliazioni (T11).
- **Da togliere:** i riquadri grandi uno per conto; i colori per tipo diversi dalla tabella 2.2.

### 4. Report — «Dove sono andati i soldi in questo periodo?»
- **Schede (≤ 7):** Riepilogo · Uscite · Entrate · Ritmo · Anno in sintesi · Salvati (F63).
- **Riepilogo:** in alto il ponte del periodo (G31) e il confronto con il periodo prima (G27 tratteggiato); sotto la
  heatmap categoria × mese (G07) e la tabella.
- **Uscite/Entrate:** treemap categoria → sottocategoria (G29) con la ciambella a due anelli come alternativa nel ⋯.
- **Stessi schemi della dashboard** (T18): blocchi spostabili, periodo condiviso, export in ogni riquadro.

### 5. Panoramica Finanziaria — «Com'è fatto il mio patrimonio?»
- **Riga come sto:** patrimonio netto, attività, passività, variazione dall'inizio dell'anno.
- **Principale:** la cascata della variazione del patrimonio (G51), poi stato patrimoniale e conto economico come
  tabelle compatte affiancate.
- **Approfondimenti (chiusi):** flussi di cassa, crescita impilata (G12), chiusure d'anno.
- **Da decidere:** se fonderla con la scheda «Patrimonio» della dashboard (oggi le due si sovrappongono).

### 6. Budget — «Sto rispettando il piano del mese?»
- **Riga come sto:** speso / previsto, giorni passati, categorie sforate.
- **Principale:** il ritmo di spesa del mese (G26) e sotto le barre per categoria con la tacca «dove dovresti essere»
  (G08), ordinate dalla più vicina al limite.
- **Azioni:** «Proponi budget» dallo storico (T20) come pulsante principale quando non ci sono budget.
- **Approfondimenti:** accantonamenti, riporti, storico mese per mese.

### 7. Obiettivi — «Quando ci arrivo?»
- **Principale:** una riga per obiettivo con barra di avanzamento, data prevista e versamento mensile che servirebbe;
  il fondo d'emergenza sempre per primo (T22).
- **Grafico:** «quando ci arrivo» come linee verso il traguardo; finché gli obiettivi non sono collegati a un conto,
  schizzo grigio con la «i» (UI-19).
- **Vuoto:** proporre i tre obiettivi tipici (emergenza, casa, pensione) con un clic.

### 8. Previsioni — «Dove sarò?»
- **Schede:** Prossimi 12 mesi · Pensione e FIRE · Scenari.
- **Prossimi 12 mesi:** saldo previsto con banda (G16) e marcatori degli eventi (ricorrenti grosse, scadenze).
- **Pensione:** ventaglio Monte Carlo riempito (G59) con la linea «quanto serve» (G60).
- **Metodi e confronti** (oggi in vista) dietro il ⋯ «Come è calcolato».

### 9. Scadenzario / Promemoria — «Cosa arriva?»
- **Principale:** elenco dei prossimi 30 giorni raggruppato per settimana, con importo e conto; il calendario come
  seconda vista.
- **Riga come sto:** uscite previste nei 30 giorni, la più grossa, quante senza importo.
- **Azioni di riga:** «Fatto», «Sposta», «Apri».

### 10. Portafoglio — «Come vanno i miei investimenti?»
- **Il problema principale:** 13 schede (UI-14 ne vuole 7). Proposta: **Panoramica · Posizioni · Rendimenti ·
  Composizione · Rendite · Operazioni · Altro** (in «Altro»: modelli, ribilanciamento, PAC, regole, look-through,
  import dai broker, storico).
- **Panoramica:** valore, versato, guadagno e rendimento in riga; valore contro versato (G37); allocazione contro
  obiettivo con bande (G41); i movimenti recenti.
- **Rendimenti:** TWR contro benchmark (G21); heatmap mensile (G38) e calo dal massimo (G39) con la «i» finché
  mancano i prezzi giornalieri (T26).
- **Colore:** tutto in blu per gli investimenti (UI-03), il viola solo se c'è leva/debito.

### 11. Debiti — «Quando finisco, e conviene anticipare?»
- **Riga come sto:** debito residuo (viola), rata mensile totale, interessi ancora da pagare, data di fine.
- **Principale:** debito residuo nel tempo fino all'estinzione (G35), con il contratto tratteggiato.
- **Strumenti** (T24–T25): «Se verso X in più» e valanga contro palla di neve, come riquadri con il risultato in una
  riga e il dettaglio a richiesta.
- **Quota capitale e interessi per anno** (G36) negli approfondimenti.

### 12. Fisco — «Quanto devo, e cosa posso detrarre?»
- **Schede:** 730 e detrazioni · Investimenti (plusvalenze, zainetto, bollo, IVAFE) · Lavoretti · Tetti deducibili.
- **Riga come sto:** detrazioni dell'anno, minusvalenze da usare con la scadenza, bollo e IVAFE stimati.
- **Avviso fisso** (piccolo, con «i»): i calcoli sono stime finché non c'è la verifica sulle fonti ufficiali (T31).

### 13. Sezioni di servizio — Assicurazioni, Bollette, Lavoretti, Prestiti tra persone, Documenti, Istantanee
Uno **schema unico** per tutte: riga di 3 numeri, tabella compatta con «Nuovo» nel pop-up (T07), un solo grafico
proprio (Bollette: €/mese e €/unità; Assicurazioni: premi per tipo; Lavoretti: soglia annua; Prestiti: chi deve
cosa). Export in ogni tabella (T08). Revisione con T34–T35.

### 14. Importa / Esporta — «Come porto dentro i miei dati?»
- **Principale:** una sola zona di trascinamento per tutti i file, che riconosce banca e formato; sotto gli ultimi
  import con «Annulla questo import» (T16).
- **Mappatura manuale:** solo quando il riconoscimento non basta; anteprima compatta (oggi `bank_preview.html` ha 47
  stili scritti a mano: priorità per T48).
- **Esporta e backup** in una scheda a parte.

### 15. Salute dei dati — «Di cosa mi devo fidare?»
- **Principale:** i controlli come elenco con il numero e il link «Sistema», i problemi in alto; tutto verde = una
  riga «Tutto in ordine». Gli stessi controlli alimentano «Da sistemare» della dashboard.

### 16. Impostazioni — «Come voglio che funzioni?»
- **Struttura:** colonna sinistra con le sezioni (Generale, Dashboard, Categorie e regole, Conti, AI, Dati, Utenti),
  a destra una sezione per volta; ricerca delle impostazioni in alto.
- **Pulizia:** `settings/index.html` e `settings/ai.html` hanno 29 stili scritti a mano ciascuno (T48).

---

## Ordine proposto
| Giro | Schermate | Perché prima |
|---|---|---|
| R1 | Dashboard (finire), Transazioni, Conti e Carte | le più usate ogni giorno |
| R2 | Budget, Scadenzario, Report | il mese in corso |
| R3 | Portafoglio (7 schede), Debiti, Panoramica Finanziaria | patrimonio; dipende in parte da T26 |
| R4 | Obiettivi, Previsioni, Fisco | il futuro; Fisco dopo T31 |
| R5 | Sezioni di servizio, Importa/Esporta, Salute dei dati, Impostazioni | pagine di servizio |

Ogni giro: revisione a schermo sul server demo → decisioni nel registro di DESIGN.md → card → codice → screenshot.

## Da decidere
1. La riga «come sto» in cima a ogni pagina: sì ovunque, o solo dove ci sono numeri da riassumere?
2. Portafoglio: le 7 schede proposte vanno bene?
3. Panoramica Finanziaria: resta pagina a sé o diventa la scheda «Patrimonio» della dashboard?
4. Impostazioni a colonna con le sezioni: sì?
5. L'ordine dei giri R1–R5.
