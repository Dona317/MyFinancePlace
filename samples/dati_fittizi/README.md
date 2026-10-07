# Dati fittizi per provare l'app

Tutto in questa cartella è inventato (persone, importi, numeri di polizza): serve a vedere l'app piena di dati
senza usare i tuoi. Non ci sono programmi da eseguire: sono solo file da caricare dall'app.

| File | Cosa contiene | Dove si carica |
|---|---|---|
| `backup_completo_demo.zip` | 18 mesi di una famiglia tipo: 416 transazioni (stipendio, mutuo, bollette, spesa, ristoranti, abbonamenti, vacanze…), 4 conti (corrente, carta, deposito, contanti), 6 posizioni (ETF, BTP, Bitcoin, fondo pensione, casa), mutuo e prestito auto, 3 polizze, 3 obiettivi, budget mensili, 3 istantanee | **Esporta → Backup completo e ripristino → Ripristina** (spunta la conferma) |
| `backup_completo_3anni.zip` | **Il set completo**: 3 anni (da ottobre 2023) su **4 conti collegati da giroconti** — conto corrente, carta di credito saldata ogni mese dal corrente, conto deposito (risparmio mensile, interessi, prelievo estivo), conto titoli (PAC mensile in ETF, dividendi). Aumenti di stipendio, tredicesima e premio, bollette stagionali, spese annuali (assicurazione auto, bollo, TARI), abbonamenti con aumenti di prezzo e uno disdetto, spese suddivise, un pagamento in dollari, mutuo e prestito, budget, obiettivi, istantanee ogni 6 mesi. Arriva fino a fine del mese prima dello scorso | **Esporta → Backup completo e ripristino → Ripristina** |
| `estratti_da_importare/` | Il mese scorso e quello in corso dei 4 conti, ognuno in un formato diverso: CSV (corrente), OFX (carta), CAMT.053 con saldi (deposito), QIF (titoli). Da importare **dopo** il ripristino del backup a 3 anni | **Esporta → Importa estratto conto** (scegli il conto giusto in anteprima) |
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
# il set completo a 3 anni (un altro database vuoto)
createdb mfp_demo_3anni
DATABASE_URL=postgresql://utente:password@localhost:5432/mfp_demo_3anni python samples/dati_fittizi/genera_completo.py
```
