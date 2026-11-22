# Documentazione di MyFinancePlace

Tutto ciò che non è codice, in un posto solo. Il punto di partenza è il **piano**: cosa fare, in che ordine,
le decisioni prese e quelle aperte.

## [piano/](piano/) — cosa fare e quando
| File | Cosa contiene |
|---|---|
| [PIANO_E_TODO.md](piano/PIANO_E_TODO.md) | **Il documento principale.** Sezione 0: stato dei lavori (SAL), fasi confermate, decisioni aperte (Dn). Poi le funzionalità numerate (Fn) con priorità, stato e dettagli |
| [CARD_PROSSIME_TASK.md](piano/CARD_PROSSIME_TASK.md) | Le Card delle prossime task (F106, 16 nov 2026; giro D di design del 18 nov): una per task, in ordine, pronte da copiare |
| [REDESIGN_SCHERMATE.md](piano/REDESIGN_SCHERMATE.md) | Bozza del redesign delle schermate principali: lo schema comune e cosa cambia pagina per pagina, in giri R1–R5 |
| [ROADMAP.md](piano/ROADMAP.md) | Ordine di sviluppo delle sezioni dell'app e cosa sta fuori dall'MVP |
| [MVP.md](piano/MVP.md) | Cosa deve fare la prima versione completa, voce per voce |
| [NEXT_STEPS.md](piano/NEXT_STEPS.md) | Stato e prossimi passi (storico, in inglese) |
| [ROADMAP_WORKFLOW.md](piano/ROADMAP_WORKFLOW.md) | Come si costruiscono le voci rimaste: ordine, dipendenze, chi fa cosa (in inglese) |

## [strategia_e_business/](strategia_e_business/) — posizionamento e mercato
| File | Cosa contiene |
|---|---|
| [ANALISI_COMPETITOR.md](strategia_e_business/ANALISI_COMPETITOR.md) | Concorrenti a confronto con l'MVP (ottobre 2026) |
| Analisi Strategica.xlsx | Missione, mappa e matrice strategica, posizionamento, note su design e funzionalità |
| Analisi Funzionalita vs MVP.xlsx | Funzionalità dei concorrenti contro l'MVP, nuovi concorrenti, analisi da aggiungere |
| Market_Mapping_Personal_Finance.xlsx | Mappa del mercato della finanza personale, «cosa rubare», posizionamento |
| Panorama Competitivo Nov 2026.xlsx | Panorama competitivo di novembre 2026: GitHub, temi di Reddit, Italia ed Europa, opportunità e minacce |
| Buchi e Piano Portafoglio Nov 2026.xlsx | Cosa manca al Portafoglio e il suo piano: catalogo e librerie dei grafici, dashboard, ribilanciamento, registro ordini, decisioni aperte |

## [analisi/](analisi/) — ricerche e rapporti
| File | Cosa contiene |
|---|---|
| [Panorama competitivo finanza personale.md](analisi/Panorama%20competitivo%20finanza%20personale.md) | Chi sono i concorrenti oggi (Wealthfolio in testa) e dove resta spazio: il fisco italiano |
| [Grafici dati e piano Portafoglio.md](analisi/Grafici%20dati%20e%20piano%20Portafoglio.md) | Grafici e gestione del dato dei concorrenti; piano del Portafoglio (portafogli, conti titoli, ribilanciamento) |
| [Grafici da riportare.md](analisi/Grafici%20da%20riportare.md) | Il catalogo dei grafici da portare nell'app (G01…), con priorità e fattibilità |
| [note_di_ricerca/](analisi/note_di_ricerca/) | Le note di base di ogni rapporto (fonti, concorrenti, fonti dei prezzi EOD, inventario dell'app), una cartella per rapporto |

## [tecnica/](tecnica/) — come si sviluppa, si installa, si distribuisce
| File | Cosa contiene |
|---|---|
| [DESIGN.md](tecnica/DESIGN.md) | Linee guida di design: principi, colori, testi, componenti, checklist per le pagine nuove, registro delle decisioni UI |
| [GUIDA_SVILUPPO.md](tecnica/GUIDA_SVILUPPO.md) | Guida per lo sviluppo: architettura, convenzioni, come aggiungere una funzionalità (in inglese) |
| [DEPLOY.md](tecnica/DEPLOY.md) | L'app come servizio: Docker, HTTPS, backup, aggiornamenti (in inglese) |
| [PSD2.md](tecnica/PSD2.md) | La lettura dei movimenti via PSD2 con Enable Banking: come registrare l'applicazione, collegare una banca, come funziona la sync |
| [DESKTOP.md](tecnica/DESKTOP.md) | L'app desktop: pacchetti, notifiche, avvio automatico, installatore, pubblicare una versione |

## Fuori da questa cartella
- [README.md](../README.md) e [CLAUDE.md](../CLAUDE.md) nella radice: presentazione del progetto e memoria per l'assistente.
- I README accanto al codice che descrivono: `docs/Transaction samples/dati_fittizi/` (dati demo), `docs/Transaction samples/bank_statements/`
  (estratti di prova), `scripts/live/` (test nel browser), `migrations/`.
