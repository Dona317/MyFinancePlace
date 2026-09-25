# Fake bank statements

Invented statements (fake holder "MARIO ROSSI", made-up amounts and IBANs) for trying the bank import
by hand: **Esporta → Importa Estratto Conto Bancario**, pick a file, keep "Rilevamento automatico".

| File | Bank / format | Period | What it shows |
|---|---|---|---|
| `fineco_2026-06_2026-07.xlsx` | Fineco `.xlsx` (Entrate/Uscite, Moneymap) | Jun–Jul 2026 | 2 "Autorizzato" movements skipped as pending |
| `fineco_2026-07_2026-09.xlsx` | Fineco `.xlsx` | Jul–Sep 2026 | Overlaps July with the file above: import both, the shared rows are flagged "Già importato" |
| `intesa_sanpaolo_2026-04_2026-09.xlsx` | Intesa Sanpaolo `.xlsx` (signed Importo, own Categoria) | Apr–Sep 2026 | Largest file (~150 rows), one "Non contabilizzato" row |
| `intesa_sanpaolo_legacy_2026-03.xls` | Old Intesa export: HTML table with `.xls` extension (Accrediti/Addebiti) | Mar 2026 | Legacy format |
| `unicredit_2026-08_2026-09.csv` | Generic CSV, `;` separated, Italian numbers, `Importo (EUR)` | Aug–Sep 2026 | Generic detection |
| `revolut_2026-09.csv` | Generic English CSV (Revolut style) | Sep 2026 | English headers |
| `banca_generica_2026-02.xls` | Binary Excel 97-2003 `.xls` with Dare/Avere columns | Feb 2026 | Separate debit/credit columns |
| `fineco_estratto_conto_2026-07_2026-08.pdf` | Fineco-style PDF, **text layout without table borders**, 2 pages | Jul–Aug 2026 | Columns rebuilt from positions (Entrate vs Uscite), wrapped descriptions, repeated header, page footer and final balance skipped |
| `intesa_sanpaolo_lista_movimenti_2026-09.pdf` | Intesa-style PDF with a **bordered table** | Sep 2026 | PDF table extraction |
| `banca_popolare_2026-05.txt` | Fixed-width plain text with Dare/Avere | May 2026 | Text columns rebuilt from character positions |
| `estratto_conto_word_2026-01.docx` | Word document with a table | Jan 2026 | Word tables |
| `estratto_conto_libreoffice_2025-12.ods` | LibreOffice Calc spreadsheet | Dec 2025 | OpenDocument, typed date cells |
| `estratto_conto_2025-11.rtf` | RTF with tab-separated columns | Nov 2025 | Rich Text Format |
| `SCANSIONE_fineco_2026-07_2026-08.pdf` | **Scanned** PDF: page images only, no text layer | Jul–Aug 2026 | Needs the AI reader (`LLM_PROVIDER`); without it, a clear error |
| `FOTO_estratto_conto_intesa_2026-09.jpg` | **Phone photo** (JPEG, slightly rotated) | Sep 2026 | Needs the AI reader |

Suggested demo:

1. `python seed.py` (optional) and start the app.
2. Import `fineco_2026-06_2026-07.xlsx`, then `fineco_2026-07_2026-09.xlsx` to see duplicate detection.
3. Import `intesa_sanpaolo_2026-04_2026-09.xlsx`, then open the Dashboard, Conto Economico and Spese e Tendenze.

To reset the imported data, delete the transactions (`python seed.py` wipes and re-seeds the table).

## Regenerating

```bash
pip install xlwt fpdf2    # only needed for the binary .xls and the PDF samples
python samples/bank_statements/generate.py
```

The generator uses a fixed random seed, so the movements are the same each time.
Tests in `tests/test_bank_import.py` parse every file here, so keep them in sync when changing the importer.
