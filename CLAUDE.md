# MyFinancePlace — memoria del progetto

## Versione attuale
- **La versione attuale dell'app è il ramo `test-Cloud`** (PR #8, in bozza verso `main`).
  Ultimo commit verificato: `df54fec` (10 ott 2026), con CI verde (test + app desktop Windows/macOS/Linux) e
  test live verdi.
- `main` è indietro (lo scheletro iniziale) finché la PR #8 non viene unita: decisione D1, rimandata a
  novembre 2026. **Non unire su `main` senza una richiesta esplicita.**
- Si lavora e si pusha solo su `test-Cloud`. I rami `Mapping-Excel` e `Dona317-patch-1` sono già contenuti
  in `test-Cloud`: vanno cancellati a mano su GitHub.

## Dove sono le cose
- Piano, decisioni e TODO: `docs/PIANO_E_TODO.md`
- App desktop (pacchetti, notifiche, avvio automatico, installatore): `docs/DESKTOP.md`
- Dati demo: `samples/dati_fittizi/`

## Come verificare
- Test: `TEST_DATABASE_URL=postgresql://… python -m pytest -q --cov=app --cov-report=json:cov.json --cov-fail-under=94`,
  poi `python scripts/untested_functions.py cov.json` (deve dare 0)
- Stile: `ruff check .`
- Test live nel browser: `sh scripts/live/run.sh`
- Traduzioni: `python scripts/translations.py update` / `compile` (sorgente in italiano, catalogo EN)

## Convenzioni
- Rispondere all'utente in italiano.
- Commenti e docstring nel codice in inglese; testi dell'interfaccia in italiano con `_()`.
