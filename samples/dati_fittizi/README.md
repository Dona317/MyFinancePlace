# Dati fittizi per provare l'app

Tutto in questa cartella è inventato (persone, importi, numeri di polizza): serve a vedere l'app piena di dati
senza usare i tuoi. Non ci sono programmi da eseguire: sono solo file da caricare dall'app.

| File | Cosa contiene | Dove si carica |
|---|---|---|
| `backup_completo_demo.zip` | 18 mesi di una famiglia tipo: 416 transazioni (stipendio, mutuo, bollette, spesa, ristoranti, abbonamenti, vacanze…), 4 conti (corrente, carta, deposito, contanti), 6 posizioni (ETF, BTP, Bitcoin, fondo pensione, casa), mutuo e prestito auto, 3 polizze, 3 obiettivi, budget mensili, 3 istantanee | **Esporta → Backup completo e ripristino → Ripristina** (spunta la conferma) |
| `backup_completo_3anni.zip` | **Il set completo**: 3 anni (da ottobre 2023), 1100 transazioni su **4 conti collegati da giroconti** — conto corrente, carta di credito saldata ogni mese, conto deposito (risparmio mensile, interessi, prelievo estivo, l'acquisto del BTP), conto titoli. **Investimenti** con acquisti e vendite collegati alla posizione: PAC mensile in ETF VWCE a prezzi variabili, BTP con cedole semestrali, azioni Enel con dividendi e metà vendute in guadagno, Bitcoin, fondo pensione con contributi mensili, la casa; quantità e prezzi medi tornano con le operazioni. **Portafoglio modello** 80/20 attivo (VWCE per le azioni, il BTP per le obbligazioni), un **PAC** mensile da 250 € da confermare il 12 e due **regole** (un titolo sotto del 15 % dal prezzo medio, un titolo oltre il 40 % del portafoglio). Con le funzioni F20: due **titolari** (Marco e Giulia Rossi) con conti, titoli e debiti intestati o cointestati, il **mutuo collegato alla casa**, area e settore dei titoli, il fondo d'emergenza che **segue il conto deposito** e i viaggi dell'anno scorso come **eventi** (Puglia, New York, Londra). Con le funzioni F22: il **tetto deducibile** del fondo pensione, l'**auto** che perde il 15 % l'anno, il conto **Contanti** con i prelievi bancomat, il mercato pagato in contanti e una conta del portafoglio, tre **lavoretti** (uno con ritenuta d'acconto, uno da incassare), **prestiti tra amici** (Luca e Sara) e una cena **divisa** con Luca (la sua parte va in «Anticipi per altri», esclusa dalle analisi), una **classificazione «Rischio»** degli investimenti. **Assicurazioni**: auto, casa, vita, salute, RC capofamiglia (in scadenza: compare nei promemoria) e una polizza disdetta, con i premi tra i movimenti. **Debiti**: mutuo, prestito auto e un finanziamento a tasso zero già estinto. **Documenti** (PDF): contratto del mutuo, polizze, CU, la ricevuta del dentista collegata al pagamento. E poi: aumenti di stipendio, tredicesima e premio, bollette stagionali, spese annuali, abbonamenti con aumenti e uno disdetto, spese suddivise, pagamenti in dollari e sterline, budget, obiettivi (uno raggiunto), istantanee trimestrali, categorie con la loro natura. Arriva fino a fine del mese prima dello scorso | **Esporta → Backup completo e ripristino → Ripristina** |
| `estratti_da_importare/` | Il mese scorso e quello in corso dei 4 conti, ognuno in un formato diverso: CSV (corrente), OFX (carta), CAMT.053 con saldi (deposito), QIF (titoli). Da importare **dopo** il ripristino del backup a 3 anni | **Esporta → Importa estratto conto** (scegli il conto giusto in anteprima) |
| `due_banche/` | **Due estratti conto della stessa coppia, da gennaio 2022 a settembre 2026**, che si scambiano soldi: ogni spostamento tra i due conti è in **tutti e due** i file con lo **stesso importo**, in uscita da uno e in entrata nell'altro. Come nella realtà, a volte la banca lo chiama «giroconto», a volte è un **bonifico generico a se stessi** (SEPA o istantaneo), e arriva lo stesso giorno, di solito 1–3 giorni lavorativi dopo, a volte **fino a 15 giorni dopo**. `unicredit_conto_corrente_…csv` (1595 movimenti): due stipendi con tredicesima, premio e rimborso 730, affitto poi mutuo dal luglio 2023, condominio, bollette (con la crisi energetica 2022), spesa, carburante, ristoranti, abbonamenti, assicurazione e bollo auto, TARI, regali di Natale, acquisti a caso, vendite su Subito e consulenze occasionali, lavatrice rotta, acquisto casa, dentista. `fineco_conto_risparmio_…xlsx` (287 movimenti): il risparmio mensile in arrivo da UniCredit, viaggi estivi e settimana bianca, il matrimonio di giugno 2024 con viaggio di nozze, interessi e imposta di bollo trimestrali; rimanda soldi a UniCredit per l'anticipo della casa, i mobili, il dentista. 63 spostamenti in tutto. Saldi iniziali: UniCredit 4.200 €, Fineco 22.000 € → finali 9.216,15 € e 61.267,93 € | Crea i conti «UniCredit conto corrente» (saldo iniziale 4.200) e «Fineco conto risparmio» (22.000), poi **Esporta → Importa estratto conto** un file alla volta, scegliendo il conto giusto. Nel secondo file l'anteprima segna i movimenti già arrivati dal primo («Collega al giroconto: …», spuntato): importandoli diventano un solo giroconto con i due conti, senza doppioni, in qualunque ordine. Togli la spunta «collega» se un movimento è diverso. **Per provare il riconoscimento con un solo file**: prima dell'import compila **Impostazioni → Titolari e IBAN** con il titolare *Mario Rossi* e gli IBAN *IT27 X020 0801 6000 0010 2345 678* (UniCredit) e *IT06 S030 1503 2000 0001 2345 678* (Fineco): i bonifici a se stessi diventano subito giroconti tra i due conti |
| `broker/` | Operazioni di compravendita esportate da un broker. `degiro_transazioni.csv` è nel formato di Degiro (Attività → Transazioni): acquisti di ETF in euro e azioni Apple in dollari, con il controvalore in euro e i costi, e una vendita. `generico_operazioni.csv` è un formato qualunque (data, segno A/V, titolo, ISIN, quantità, prezzo, commissioni): un BTP quotato in % del nominale, un ETF, azioni Enel comprate e metà vendute | **Portafoglio → Importa dal broker**: i titoli che non hai vengono creati; reimportare lo stesso file non crea doppioni |
| `transazioni_3anni.csv` | Le transazioni del backup a 3 anni | **Esporta → Importa CSV o Excel con mappatura manuale** |
| `transazioni_demo.csv` | Le stesse 416 transazioni, solo le transazioni | **Esporta → Importa CSV o Excel con mappatura manuale** |
| `../bank_statements/` | Estratti conto di esempio di varie banche (Excel, CSV, PDF, Word…) | **Esporta → Importa estratto conto** |
| `i_tuoi_file/` | Vuota: mettici i tuoi file di prova | — |

## Provare in sicurezza

1. **Prima fai un backup dei tuoi dati**: Esporta → *Scarica backup completo*. Il ripristino del file demo
   **sostituisce tutti i dati** (l'app salva comunque una copia di quelli di prima, visibile in *Backup automatici*).
2. Ripristina `backup_completo_demo.zip` e guarda dashboard, stato patrimoniale, previsioni, budget, promemoria.
3. Per tornare ai tuoi dati: ripristina il backup del punto 1 (o la copia in *Backup automatici*).

In alternativa usa un database separato solo per le prove, così i tuoi dati non vengono mai toccati:

```bash
createdb myfinanceplace_demo
DATABASE_URL=postgresql://utente:password@localhost:5432/myfinanceplace_demo flask --app run db upgrade
DATABASE_URL=postgresql://utente:password@localhost:5432/myfinanceplace_demo flask --app run run
```

## Rigenerare i file

Le date finiscono il giorno in cui i file sono stati generati. Per averli aggiornati a oggi serve un database
**vuoto** di appoggio (lo script si rifiuta di usarne uno con dati):

```bash
createdb mfp_demo_gen
DATABASE_URL=postgresql://utente:password@localhost:5432/mfp_demo_gen python samples/dati_fittizi/genera.py
# i due estratti conto con i giroconti (nessun database: scrive solo i file in due_banche/)
python samples/dati_fittizi/genera_due_banche.py
# il set completo a 3 anni (un altro database vuoto)
createdb mfp_demo_3anni
DATABASE_URL=postgresql://utente:password@localhost:5432/mfp_demo_3anni python samples/dati_fittizi/genera_completo.py
```
