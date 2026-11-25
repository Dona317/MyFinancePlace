# MyFinancePlace — memoria del progetto

## Versione attuale
- **La versione attuale dell'app è il ramo `test-Cloud`** (PR #8, in bozza verso `main`).
  Ultima verifica: 25 nov 2026 — suite 1506 test tutti verdi, copertura 97,50 %, 0 funzioni non testate
  (circa 30 minuti: il limite della CI è 40).
  Il test `test_a_tilted_photo_is_straightened` dipende dal motore OCR locale (qui passa, può fallire altrove).
  Test live nel browser non rifatti dopo il 14 nov (273/273 allora): su Windows non girano (gunicorn, Playwright).
- Pagine da provare a schermo senza la password vera: `python scripts/demo_server.py` (porta 5055, database
  `…_demo` con i dati finti a 3 anni, utente «demo»). Il database locale gira in Docker (`docker compose up -d db`).
- `main` è indietro (lo scheletro iniziale) finché la PR #8 non viene unita: decisione D1, rimandata a
  novembre 2026. **Non unire su `main` senza una richiesta esplicita.**
- Si lavora e si pusha solo su `test-Cloud`. I rami `Mapping-Excel` e `Dona317-patch-1` sono già contenuti
  in `test-Cloud`: vanno cancellati a mano su GitHub.

## Dove sono le cose
- Indice di tutta la documentazione (piano, strategia e business, analisi, tecnica): `docs/README.md`
- Piano, decisioni e TODO: `docs/piano/PIANO_E_TODO.md`
- App desktop (pacchetti, notifiche, avvio automatico, installatore): `docs/tecnica/DESKTOP.md`
- **Linee guida di design** (colori, testi, componenti, checklist, registro decisioni UI): `docs/tecnica/DESIGN.md` —
  da leggere prima di toccare template o CSS; ogni nuova decisione di design va nel suo registro
- Dati demo: `docs/Transaction samples/dati_fittizi/` (investimenti: `docs/Transaction samples/dati_fittizi/investimenti/`, generati da `genera_investimenti.py`)
- Stato dei lavori (SAL) e decisioni aperte: sezione 0 di `docs/piano/PIANO_E_TODO.md` (riaperta dal promemoria delle 13:30)
- **Database dei prezzi** (condiviso da tutti gli archivi, `market.sqlite` nella cartella dati): servizi `market_data`,
  `history_filler` (riempitore giornaliero, tutto il database ogni settimana), `history_links` (justETF, «Incolla il link»),
  `fx_store` (cambi «FX.*»). Database di partenza in `data/market_seed/` (lista `strumenti.csv`, zip spedito con l'app):
  si rigenera con `python scripts/build_market_seed.py` (serve internet; il lavoro intermedio in `data/market_seed/build/`)
- Fonti dei prezzi escluse e perché: Borsa Italiana diretta (API con token nella pagina: serve un'autorizzazione esplicita
  dell'utente), investing.com (403 anti-bot: solo CSV), Morningstar (sfida anti-bot AWS WAF, ritirato il 24 nov), Alpha
  Vantage (scartata dall'utente). I muri anti-bot non si aggirano (F69), con **una sola eccezione voluta dall'utente**:
  la libreria yfinance (F119, 25 nov), seconda fonte dopo la lettura diretta di Yahoo

## Come verificare
- Test: `TEST_DATABASE_URL=postgresql://… python -m pytest -q --cov=app --cov-report=json:cov.json --cov-fail-under=94`,
  poi `python scripts/untested_functions.py cov.json` (deve dare 0)
- Stile: `ruff check .`
- Test live nel browser: `sh scripts/live/run.sh`
- Traduzioni: `python scripts/translations.py update` / `compile` (sorgente in italiano, catalogo EN)

## Convenzioni
- Rispondere all'utente in italiano.
- Commenti e docstring nel codice in inglese; testi dell'interfaccia in italiano con `_()`.
